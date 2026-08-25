"""JarvisVoiceListener — Titan-Grade Speech-to-Text (STT) & Continuous Wake-Word Detection.

Features:
- Multi-Layer Audio Recording: sounddevice stream -> native OS arecord/ffmpeg/parec fallback
- Multi-Tier Bilingual STT: High-speed Google Speech API (az-AZ / en-US) -> Offline faster-whisper (tiny/base)
- Continuous Wake-Word Daemon: "Hey Jarvis", "Jarvis", "Salam Jarvis", "Cənab Jarvis", "Friday"
- Automatic silence & noise suppression with instant audio transcription
"""
from __future__ import annotations

import io
import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Any

import numpy as np

logger = logging.getLogger(__name__)

_WHISPER_MODEL = None
_WHISPER_LOCK = threading.Lock()


def get_shared_whisper_model(model_size: str = "tiny"):
    """Lazy-load and cache the faster-whisper STT model."""
    global _WHISPER_MODEL
    with _WHISPER_LOCK:
        if _WHISPER_MODEL is None:
            try:
                from faster_whisper import WhisperModel
                _WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
            except Exception as e:
                logger.warning("Could not load faster-whisper: %s", e)
                return None
        return _WHISPER_MODEL


class JarvisVoiceListener:
    """Microphone audio recorder, multi-tier STT transcriber, and Wake-Word listener."""

    SAMPLE_RATE = 16000
    WAKE_WORDS = ["hey jarvis", "jarvis", "cənab jarvis", "salam jarvis", "ey jarvis", "friday"]

    def __init__(
        self,
        on_text_recognized: Callable[[str], None] | None = None,
        on_wake_word: Callable[[str], None] | None = None,
    ) -> None:
        self.on_text_recognized = on_text_recognized
        self.on_wake_word = on_wake_word
        self._is_recording = False
        self._audio_chunks: list[np.ndarray] = []
        self._stream = None
        self._model_size = "tiny"

        # OS process fallback recording (arecord / ffmpeg)
        self._proc_record: subprocess.Popen | None = None
        self._temp_wav: str | None = None

        # Continuous Wake-Word daemon state
        self._wake_daemon_active = False
        self._wake_thread: threading.Thread | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def is_wake_word_active(self) -> bool:
        return self._wake_daemon_active

    def start_recording(self) -> bool:
        """Start capturing audio from the default system microphone (sounddevice or OS fallback)."""
        if self._is_recording:
            return True

        self._audio_chunks = []
        self._is_recording = True

        # 1. Try sounddevice
        try:
            import sounddevice as sd

            def _audio_callback(indata, frames, time_info, status):
                if self._is_recording:
                    self._audio_chunks.append(indata.copy())

            self._stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=_audio_callback,
            )
            self._stream.start()
            return True
        except Exception as e:
            logger.warning("sounddevice recording unavailable (%s), trying native OS recorder...", e)

        # 2. Native OS Recorder Fallback (arecord / ffmpeg)
        try:
            tmp_f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            self._temp_wav = tmp_f.name
            tmp_f.close()

            if shutil.which("arecord"):
                self._proc_record = subprocess.Popen(
                    ["arecord", "-f", "cd", "-r", str(self.SAMPLE_RATE), "-c", "1", "-t", "wav", "-q", self._temp_wav],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            elif shutil.which("ffmpeg"):
                # Use default pulse/alsa input
                self._proc_record = subprocess.Popen(
                    ["ffmpeg", "-y", "-f", "pulse", "-i", "default", "-ar", str(self.SAMPLE_RATE), "-ac", "1", self._temp_wav],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
        except Exception as e:
            logger.error("All recording backends failed: %s", e)

        self._is_recording = False
        return False

    def stop_recording_and_transcribe(self, language: str | None = None) -> str:
        """Stop microphone recording and transcribe captured audio to text."""
        if not self._is_recording:
            return ""

        self._is_recording = False

        # Stop sounddevice stream
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # Stop OS process recorder
        if self._proc_record is not None:
            try:
                self._proc_record.terminate()
                self._proc_record.wait(timeout=1.5)
            except Exception:
                try:
                    self._proc_record.kill()
                except Exception:
                    pass
            self._proc_record = None

        # Collect audio data
        wav_bytes: bytes | None = None
        audio_array: np.ndarray | None = None

        if self._audio_chunks:
            try:
                audio_array = np.concatenate(self._audio_chunks, axis=0).flatten()
                if len(audio_array) >= self.SAMPLE_RATE * 0.25:  # At least 250ms
                    wav_io = io.BytesIO()
                    scaled = (audio_array * 32767).astype(np.int16)
                    with wave.open(wav_io, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(self.SAMPLE_RATE)
                        wf.writeframes(scaled.tobytes())
                    wav_bytes = wav_io.getvalue()
            except Exception:
                pass

        if not wav_bytes and self._temp_wav and os.path.exists(self._temp_wav):
            try:
                wav_bytes = Path(self._temp_wav).read_bytes()
                try:
                    os.remove(self._temp_wav)
                except Exception:
                    pass
            except Exception:
                pass

        if not wav_bytes:
            return ""

        # 1. First Priority: Fast Google Speech API (Ultra-accurate Azerbaijani and English)
        text = self._transcribe_with_speech_recognition(wav_bytes, language)

        # 2. Second Priority: Offline Local Whisper AI
        if not text and audio_array is not None:
            text = self._transcribe_with_whisper(audio_array, language)

        if text and self.on_text_recognized:
            self.on_text_recognized(text)

        return text

    def _transcribe_with_speech_recognition(self, wav_bytes: bytes, language: str | None = None) -> str:
        """Transcribe audio using Google Speech API via speech_recognition."""
        try:
            import speech_recognition as sr  # type: ignore

            r = sr.Recognizer()
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio_data = r.record(source)

            # Try Azerbaijani first
            target_lang = language or "az-AZ"
            try:
                res = r.recognize_google(audio_data, language=target_lang).strip()
                if res:
                    return res
            except Exception:
                pass

            # Fallback to English
            if target_lang != "en-US":
                try:
                    res_en = r.recognize_google(audio_data, language="en-US").strip()
                    if res_en:
                        return res_en
                except Exception:
                    pass
        except Exception:
            pass
        return ""

    def _transcribe_with_whisper(self, audio_array: np.ndarray, language: str | None = None) -> str:
        """Transcribe audio using local faster-whisper."""
        try:
            model = get_shared_whisper_model(self._model_size)
            if model is None:
                return ""

            segments, _info = model.transcribe(
                audio_array,
                beam_size=3,
                language=language or "az",
                vad_filter=True,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Continuous Wake-Word Background Listener
    # ------------------------------------------------------------------

    def start_wake_word_daemon(self) -> bool:
        """Start low-power background thread listening for 'Hey Jarvis' hotword."""
        if self._wake_daemon_active:
            return True

        self._wake_daemon_active = True
        self._wake_thread = threading.Thread(target=self._wake_word_worker, daemon=True)
        self._wake_thread.start()
        logger.info("J.A.R.V.I.S Wake-Word background daemon started.")
        return True

    def stop_wake_word_daemon(self) -> None:
        """Stop background wake-word listening thread."""
        self._wake_daemon_active = False
        if self._wake_thread:
            self._wake_thread.join(timeout=1.0)
            self._wake_thread = None

    def _wake_word_worker(self) -> None:
        """Continuous background audio stream processor."""
        while self._wake_daemon_active:
            if self._is_recording:
                time.sleep(0.5)
                continue

            try:
                if self.start_recording():
                    time.sleep(2.5)
                    text = self.stop_recording_and_transcribe().lower().strip()
                    if text:
                        for ww in self.WAKE_WORDS:
                            if ww in text:
                                prompt_after_wake = re.sub(rf"^(?:hey\s+|salam\s+|cənab\s+|ey\s+)?(?:jarvis|friday)[\s,:]*", "", text).strip()
                                if self.on_wake_word:
                                    self.on_wake_word(prompt_after_wake or text)
                                break
            except Exception:
                pass
            time.sleep(0.2)
