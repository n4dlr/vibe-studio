"""JarvisVoiceEngine — Titan-Grade Neural Voice Synthesis for J.A.R.V.I.S.

Features:
- Ultra-Natural Microsoft Neural Voices (British Butler Ryan, US Christopher, Azerbaijani Babek, Turkish Ahmet)
- High-performance playback via gst-play-1.0 / ffplay / paplay without blocking UI
- In-memory MD5 audio caching for instantaneous repeat phrases ("System status is nominal", etc.)
- Voice personality presets & rate/pitch tuning
- Graceful multi-tier fallback: Edge-TTS -> gTTS -> pyttsx3 -> Linux spd-say
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable


class JarvisVoiceEngine:
    """Neural voice speech synthesizer with zero-latency playback caching."""

    VOICE_BRITISH_BUTLER = "en-GB-RyanNeural"     # Authentic J.A.R.V.I.S
    VOICE_US_MODERN      = "en-US-ChristopherNeural"
    VOICE_AZERBAIJANI    = "az-AZ-BabekNeural"
    VOICE_TURKISH        = "tr-TR-AhmetNeural"

    VOICE_MAP = {
        "british": VOICE_BRITISH_BUTLER,
        "modern": VOICE_US_MODERN,
        "azerbaijani": VOICE_AZERBAIJANI,
        "turkish": VOICE_TURKISH,
    }

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self.cache_dir = Path(cache_dir or tempfile.gettempdir()) / "vibe_jarvis_audio_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.current_voice = self.VOICE_BRITISH_BUTLER
        self.rate = "+5%"
        self.pitch = "+0Hz"
        self._lock = threading.Lock()
        self._is_speaking = False
        self.state_callbacks: list[Callable[[bool], None]] = []

    def set_voice(self, voice_name_or_key: str) -> None:
        """Change active voice by key ('british', 'azerbaijani') or full identifier."""
        self.current_voice = self.VOICE_MAP.get(voice_name_or_key.lower(), voice_name_or_key)

    def add_state_callback(self, cb: Callable[[bool], None]) -> None:
        self.state_callbacks.append(cb)

    def _set_speaking(self, val: bool) -> None:
        self._is_speaking = val
        for cb in self.state_callbacks:
            try:
                cb(val)
            except Exception:
                pass

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def speak(self, text: str, voice_override: str | None = None) -> None:
        """Speak text aloud using natural neural voice synthesis in a background thread."""
        if not text or not text.strip():
            return

        clean_text = self._sanitize_text(text)
        threading.Thread(target=self._speak_worker, args=(clean_text, voice_override), daemon=True).start()

    def _sanitize_text(self, text: str) -> str:
        """Strip markdown syntax, code fences, and symbols for clean spoken audio."""
        t = re.sub(r"```[\s\S]*?```", " [code omitted] ", text)
        t = re.sub(r"`.*?`", "", t)
        t = re.sub(r"\[.*?\]\(.*?\)", "", t)
        t = re.sub(r"https?://\S+", "", t)
        t = re.sub(r"[*_#~>|]", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _detect_voice(self, text: str) -> str:
        """Detect language if automatic mode is desired."""
        t_low = text.lower()
        if any(w in t_low for w in ["hər", "yaxşı", "salam", "necəsən", "layihə", "fayl", "bax", "etmək", "bəli", "xeyr", "kompüter"]):
            return self.VOICE_AZERBAIJANI
        if any(w in t_low for w in ["merhaba", "nasıl", "tamam", "proje", "kod", "ekran"]):
            return self.VOICE_TURKISH
        return self.current_voice

    def _speak_worker(self, text: str, voice_override: str | None = None) -> None:
        with self._lock:
            self._set_speaking(True)
            try:
                voice = voice_override or self._detect_voice(text)

                # Check audio cache
                cache_key = hashlib.md5(f"{text}:{voice}:{self.rate}".encode()).hexdigest()
                cached_file = self.cache_dir / f"{cache_key}.mp3"

                if cached_file.exists() and cached_file.stat().st_size > 100:
                    self._play_audio_file(str(cached_file))
                    return

                # 1. Edge-TTS (Ultra realistic neural voice)
                if self._try_edge_tts(text, voice, cached_file):
                    return

                # 2. Google TTS fallback
                if self._try_gtts(text, cached_file):
                    return

                # 3. pyttsx3 offline fallback
                if self._try_pyttsx3(text):
                    return

                # 4. Linux system speech
                self._try_system_speech(text)
            finally:
                self._set_speaking(False)

    def _try_edge_tts(self, text: str, voice: str, target_file: Path) -> bool:
        try:
            import edge_tts

            async def _generate():
                communicate = edge_tts.Communicate(text, voice, rate=self.rate, pitch=self.pitch)
                await communicate.save(str(target_file))

            asyncio.run(_generate())

            if target_file.exists() and target_file.stat().st_size > 100:
                self._play_audio_file(str(target_file))
                return True
        except Exception:
            pass
        return False

    def _try_gtts(self, text: str, target_file: Path) -> bool:
        try:
            from gtts import gTTS
            lang = "az" if any(w in text.lower() for w in ["salam", "necəsən", "yaxşı"]) else "en"
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(str(target_file))
            if target_file.exists():
                self._play_audio_file(str(target_file))
                return True
        except Exception:
            pass
        return False

    def _try_pyttsx3(self, text: str) -> bool:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 0.9)
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception:
            return False

    def _try_system_speech(self, text: str) -> None:
        try:
            if shutil.which("spd-say"):
                subprocess.run(["spd-say", "-r", "10", text], timeout=10)
            elif shutil.which("espeak"):
                subprocess.run(["espeak", "-s", "160", text], timeout=10)
        except Exception:
            pass

    def _play_audio_file(self, file_path: str) -> None:
        """Play audio using the best local player."""
        # 1. Try gst-play-1.0 (very fast native Linux GStreamer player)
        if shutil.which("gst-play-1.0"):
            try:
                subprocess.run(
                    ["gst-play-1.0", "--no-interactive", file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
                return
            except Exception:
                pass

        # 2. Try ffplay
        if shutil.which("ffplay"):
            try:
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
                return
            except Exception:
                pass

        # 3. Try mpv
        if shutil.which("mpv"):
            try:
                subprocess.run(
                    ["mpv", "--no-video", "--really-quiet", file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
                return
            except Exception:
                pass

        # 4. Fallback conversion to WAV for paplay / aplay
        if shutil.which("ffmpeg") and (shutil.which("paplay") or shutil.which("aplay")):
            wav_path = file_path.replace(".mp3", ".wav")
            try:
                subprocess.run(["ffmpeg", "-y", "-i", file_path, wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if os.path.exists(wav_path):
                    if shutil.which("paplay"):
                        subprocess.run(["paplay", wav_path], timeout=30)
                    elif shutil.which("aplay"):
                        subprocess.run(["aplay", wav_path], timeout=30)
                    try:
                        os.remove(wav_path)
                    except Exception:
                        pass
                    return
            except Exception:
                pass
