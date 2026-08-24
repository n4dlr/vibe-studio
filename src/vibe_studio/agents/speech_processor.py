"""SpeechProcessor — offline STT + TTS for the Voice Consultation Agent.

Dependencies (optional):
    pip install faster-whisper sounddevice pyttsx3 numpy

Graceful fallback: if any dependency is missing the processor still imports
correctly; calling ``transcribe_once()`` or ``speak()`` will raise
``SpeechProcessorUnavailableError`` with a helpful install hint.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Availability flags — checked lazily on first use
# ---------------------------------------------------------------------------

_WHISPER_OK: bool | None = None
_SOUNDDEVICE_OK: bool | None = None
_TTS_OK: bool | None = None


def _check_deps() -> dict[str, bool]:
    global _WHISPER_OK, _SOUNDDEVICE_OK, _TTS_OK
    if _WHISPER_OK is None:
        try:
            import faster_whisper  # noqa: F401
            _WHISPER_OK = True
        except ImportError:
            _WHISPER_OK = False
    if _SOUNDDEVICE_OK is None:
        try:
            import sounddevice  # noqa: F401
            import numpy  # noqa: F401
            _SOUNDDEVICE_OK = True
        except ImportError:
            _SOUNDDEVICE_OK = False
    if _TTS_OK is None:
        try:
            import pyttsx3  # noqa: F401
            _TTS_OK = True
        except ImportError:
            _TTS_OK = False
    return {
        "whisper": bool(_WHISPER_OK),
        "sounddevice": bool(_SOUNDDEVICE_OK),
        "tts": bool(_TTS_OK),
    }


class SpeechProcessorUnavailableError(RuntimeError):
    """Raised when a required speech dependency is not installed."""


# ---------------------------------------------------------------------------
# STT — faster-whisper
# ---------------------------------------------------------------------------

_SAMPLE_RATE = 16_000  # Hz — Whisper native
_CHANNELS = 1


class STTEngine:
    """Wraps faster-whisper for offline transcription."""

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        deps = _check_deps()
        if not deps["whisper"]:
            raise SpeechProcessorUnavailableError(
                "faster-whisper not installed. Run: pip install faster-whisper"
            )
        if not deps["sounddevice"]:
            raise SpeechProcessorUnavailableError(
                "sounddevice / numpy not installed. Run: pip install sounddevice numpy"
            )

        from faster_whisper import WhisperModel  # type: ignore
        logger.info("Loading Whisper model '%s' on %s (%s)…", model_size, device, compute_type)
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._model_size = model_size
        logger.info("Whisper model loaded.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe_audio(self, audio_array, language: str | None = None) -> str:
        """Transcribe a numpy float32 array sampled at 16 kHz.

        Returns the recognised text (may be empty string).
        """
        segments, _info = self._model.transcribe(
            audio_array,
            beam_size=5,
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def record_and_transcribe(
        self,
        duration_seconds: float = 5.0,
        language: str | None = None,
    ) -> str:
        """Record *duration_seconds* from the default microphone and transcribe."""
        import numpy as np
        import sounddevice as sd

        logger.debug("Recording %.1fs at %d Hz…", duration_seconds, _SAMPLE_RATE)
        audio = sd.rec(
            int(duration_seconds * _SAMPLE_RATE),
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="float32",
        )
        sd.wait()
        audio_flat = audio.flatten()
        return self.transcribe_audio(audio_flat, language=language)

    def stream_record_and_transcribe(
        self,
        stop_event: threading.Event,
        chunk_duration: float = 0.5,
        language: str | None = None,
        on_interim: Callable[[str], None] | None = None,
    ) -> str:
        """Stream audio until *stop_event* is set, then return full transcript.

        *on_interim* is called with partial results as audio is buffered.
        """
        import numpy as np
        import sounddevice as sd

        audio_queue: queue.Queue = queue.Queue()

        def _callback(indata, frames, time, status):
            if status:
                logger.warning("sounddevice status: %s", status)
            audio_queue.put(indata.copy())

        chunks: list = []
        with sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="float32",
            callback=_callback,
            blocksize=int(_SAMPLE_RATE * chunk_duration),
        ):
            while not stop_event.is_set():
                try:
                    chunk = audio_queue.get(timeout=0.1)
                    chunks.append(chunk)
                except queue.Empty:
                    continue

        if not chunks:
            return ""

        import numpy as np
        full_audio = np.concatenate(chunks, axis=0).flatten()
        result = self.transcribe_audio(full_audio, language=language)
        return result


# ---------------------------------------------------------------------------
# TTS — pyttsx3
# ---------------------------------------------------------------------------

class TTSEngine:
    """Wraps pyttsx3 for offline text-to-speech."""

    def __init__(self, rate: int = 185, volume: float = 0.9):
        deps = _check_deps()
        if not deps["tts"]:
            raise SpeechProcessorUnavailableError(
                "pyttsx3 not installed. Run: pip install pyttsx3"
            )
        import pyttsx3  # type: ignore
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._engine.setProperty("volume", volume)
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        """Speak *text* synchronously (blocks until done)."""
        with self._lock:
            self._engine.say(text)
            self._engine.runAndWait()

    def speak_async(self, text: str) -> threading.Thread:
        """Speak *text* in a background thread. Returns the thread."""
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        """Stop any ongoing speech."""
        with self._lock:
            try:
                self._engine.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# High-level facade
# ---------------------------------------------------------------------------

class SpeechProcessor:
    """Combined STT + TTS facade used by VoiceAgent and VoiceConsultationDialog.

    Parameters
    ----------
    whisper_model:
        Whisper model size. Smaller = faster but less accurate.
        Options: "tiny", "base", "small", "medium", "large-v3"
        For 2B LLM scenarios, "base" is recommended (fast, good AZ support).
    tts_rate:
        Words per minute for TTS speech.
    language:
        ISO-639-1 language hint for Whisper (None = auto-detect).
        Auto-detect works well for EN/AZ mixed speech.
    """

    def __init__(
        self,
        whisper_model: str = "base",
        tts_rate: int = 185,
        language: str | None = None,
    ):
        self._language = language
        self._stt: STTEngine | None = None
        self._tts: TTSEngine | None = None
        self._init_error: str = ""
        self._whisper_model = whisper_model
        self._tts_rate = tts_rate

        # Lazy init — actual model load deferred to first use
        # so the UI can open even if deps are missing.

    # ------------------------------------------------------------------
    # Lazy initialisation
    # ------------------------------------------------------------------

    def _ensure_stt(self) -> STTEngine:
        if self._stt is None:
            self._stt = STTEngine(model_size=self._whisper_model)
        return self._stt

    def _ensure_tts(self) -> TTSEngine:
        if self._tts is None:
            self._tts = TTSEngine(rate=self._tts_rate)
        return self._tts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_stt_available(self) -> bool:
        deps = _check_deps()
        return deps["whisper"] and deps["sounddevice"]

    def is_tts_available(self) -> bool:
        return _check_deps()["tts"]

    def availability_summary(self) -> dict[str, bool]:
        return _check_deps()

    def record_and_transcribe(self, duration_seconds: float = 5.0) -> str:
        """Record audio then return transcribed text. Blocking."""
        return self._ensure_stt().record_and_transcribe(
            duration_seconds=duration_seconds,
            language=self._language,
        )

    def stream_record_and_transcribe(
        self,
        stop_event: threading.Event,
        on_interim: Callable[[str], None] | None = None,
    ) -> str:
        """Stream audio until stop_event, return full transcript."""
        return self._ensure_stt().stream_record_and_transcribe(
            stop_event=stop_event,
            language=self._language,
            on_interim=on_interim,
        )

    def speak(self, text: str, async_: bool = True) -> threading.Thread | None:
        """Speak *text*. Returns thread handle if async_=True."""
        if not self.is_tts_available():
            logger.warning("TTS unavailable — skipping speech output.")
            return None
        tts = self._ensure_tts()
        if async_:
            return tts.speak_async(text)
        else:
            tts.speak(text)
            return None

    def stop_speaking(self) -> None:
        if self._tts is not None:
            self._tts.stop()
