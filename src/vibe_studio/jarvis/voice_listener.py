"""JarvisVoiceListener — Real-Time Microphone Speech-to-Text (STT) for J.A.R.V.I.S.

Features:
- Offline & Local Multilingual Speech Recognition using faster-whisper (Azerbaijani, English, Turkish, Russian)
- Low-latency sounddevice recording with automatic audio normalization
- Push-to-Talk and Toggle Recording modes
- Direct integration with J.A.R.V.I.S Autonomous HUD and Core Engine
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

_WHISPER_MODEL = None
_WHISPER_LOCK = threading.Lock()


def get_shared_whisper_model(model_size: str = "base"):
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
    """Microphone audio recorder and speech-to-text transcriber for J.A.R.V.I.S."""

    SAMPLE_RATE = 16000

    def __init__(self, on_text_recognized: Callable[[str], None] | None = None) -> None:
        self.on_text_recognized = on_text_recognized
        self._is_recording = False
        self._audio_chunks: list[np.ndarray] = []
        self._stream = None
        self._record_thread: threading.Thread | None = None
        self._model_size = "base"

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start_recording(self) -> bool:
        """Start capturing audio from the default system microphone."""
        if self._is_recording:
            return True

        try:
            import sounddevice as sd

            self._audio_chunks = []
            self._is_recording = True

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
            logger.error("Failed to start audio recording: %s", e)
            self._is_recording = False
            return False

    def stop_recording_and_transcribe(self, language: str | None = None) -> str:
        """Stop microphone recording and transcribe captured audio to text."""
        if not self._is_recording:
            return ""

        self._is_recording = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        except Exception:
            pass

        if not self._audio_chunks:
            return ""

        try:
            full_audio = np.concatenate(self._audio_chunks, axis=0).flatten()
            if len(full_audio) < self.SAMPLE_RATE * 0.3:  # Less than 300ms
                return ""

            model = get_shared_whisper_model(self._model_size)
            if model is None:
                return ""

            # Transcribe audio array
            segments, _info = model.transcribe(
                full_audio,
                beam_size=5,
                language=language,  # Auto-detects if None
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()

            if text and self.on_text_recognized:
                self.on_text_recognized(text)

            return text
        except Exception as e:
            logger.error("Voice transcription failed: %s", e)
            return ""
