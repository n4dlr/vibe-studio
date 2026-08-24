"""VoiceConsultationDialog — premium PySide6 dialog for voice interaction.

Features
--------
- Animated waveform visualizer (listening / speaking / idle states)
- Push-to-Talk (hold) + Auto-detect (VAD) modes
- Real-time transcript display as user speaks
- Chat bubble conversation history
- Ollama model selector (only local models listed)
- Keyboard shortcut: Space bar = Push-to-Talk
- Graceful degradation when speech deps are not installed (shows install hint)
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRectF,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Colour palette — matches Vibe Studio dark theme
# ---------------------------------------------------------------------------
_BG_DEEP    = "#13141c"
_BG_BASE    = "#181924"
_BG_PANEL   = "#1c1d2a"
_BG_RAISED  = "#242536"
_BG_HOVER   = "#2d2e42"
_BORDER     = "#28293d"
_TEXT       = "#e2e4ed"
_TEXT_DIM   = "#9ca3af"
_ACCENT     = "#6366f1"
_ACCENT_HOV = "#4f46e5"
_DANGER     = "#f43f5e"
_SUCCESS    = "#10b981"
_WARN       = "#f59e0b"


# ---------------------------------------------------------------------------
# Animated Waveform Widget
# ---------------------------------------------------------------------------

class WaveformWidget(QWidget):
    """Animated audio waveform visualiser.

    States: idle | listening | speaking | thinking
    """

    IDLE      = "idle"
    LISTENING = "listening"
    SPEAKING  = "speaking"
    THINKING  = "thinking"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._state = self.IDLE
        self._phase = 0.0
        self._amplitudes: list[float] = [0.0] * 32

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)  # ~33 fps

    def set_state(self, state: str) -> None:
        self._state = state

    def _tick(self) -> None:
        import random
        self._phase += 0.12

        if self._state == self.LISTENING:
            target = [0.4 + 0.5 * abs(math.sin(self._phase * 1.3 + i * 0.4 + random.uniform(-0.2, 0.2)))
                      for i in range(32)]
        elif self._state == self.SPEAKING:
            target = [0.2 + 0.7 * abs(math.sin(self._phase * 2.1 + i * 0.6))
                      for i in range(32)]
        elif self._state == self.THINKING:
            target = [0.1 + 0.15 * abs(math.sin(self._phase * 0.6 + i * 0.9))
                      for i in range(32)]
        else:  # idle
            target = [0.05 + 0.05 * abs(math.sin(self._phase * 0.3 + i * 0.5))
                      for i in range(32)]

        # Smooth interpolation
        self._amplitudes = [
            self._amplitudes[i] * 0.6 + target[i] * 0.4
            for i in range(32)
        ]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2

        # Background
        painter.fillRect(self.rect(), QColor(_BG_PANEL))

        # Choose bar colour by state
        if self._state == self.LISTENING:
            color_top    = QColor("#818cf8")
            color_bottom = QColor("#6366f1")
        elif self._state == self.SPEAKING:
            color_top    = QColor("#34d399")
            color_bottom = QColor("#059669")
        elif self._state == self.THINKING:
            color_top    = QColor("#fbbf24")
            color_bottom = QColor("#d97706")
        else:
            color_top    = QColor("#374151")
            color_bottom = QColor("#1f2937")

        n_bars = 32
        bar_w  = max(2, w / n_bars - 3)
        spacing = w / n_bars

        for i, amp in enumerate(self._amplitudes):
            bar_h = max(4, amp * (h - 16))
            x = i * spacing + spacing / 2 - bar_w / 2
            y = cy - bar_h / 2

            grad = QLinearGradient(x, y, x, y + bar_h)
            grad.setColorAt(0.0, color_top)
            grad.setColorAt(1.0, color_bottom)

            path = QPainterPath()
            radius = min(bar_w / 2, 3.0)
            path.addRoundedRect(QRectF(x, y, bar_w, bar_h), radius, radius)
            painter.fillPath(path, grad)

        painter.end()


# ---------------------------------------------------------------------------
# Chat Bubble Widget
# ---------------------------------------------------------------------------

class ChatBubble(QFrame):
    """Single message bubble (user=right, assistant=left)."""

    def __init__(self, text: str, role: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.role = role

        is_user = role == "user"
        bubble_color = _ACCENT if is_user else _BG_RAISED
        text_color   = "#ffffff" if is_user else _TEXT
        align        = Qt.AlignRight if is_user else Qt.AlignLeft

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        label.setFont(QFont("Inter", 12))
        label.setStyleSheet(
            f"QLabel {{ background: {bubble_color}; color: {text_color}; "
            f"padding: 10px 14px; border-radius: 14px; "
            f"border-{'bottom-right' if is_user else 'bottom-left'}-radius: 4px; }}"
        )
        label.setMaximumWidth(380)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        if is_user:
            icon_lbl = QLabel("👤")
            icon_lbl.setFont(QFont("Segoe UI Emoji", 16))
            layout.addStretch()
            layout.addWidget(label)
            layout.addWidget(icon_lbl)
        else:
            icon_lbl = QLabel("🤖")
            icon_lbl.setFont(QFont("Segoe UI Emoji", 16))
            layout.addWidget(icon_lbl)
            layout.addWidget(label)
            layout.addStretch()

        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("QFrame { background: transparent; }")


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class ListenWorker(QObject):
    """Runs STT in a background thread."""

    finished  = Signal(str)   # transcribed text
    error     = Signal(str)
    interim   = Signal(str)   # partial transcript while streaming

    def __init__(self, speech_processor: Any, stop_event: threading.Event):
        super().__init__()
        self._sp = speech_processor
        self._stop_event = stop_event

    @Slot()
    def run(self) -> None:
        try:
            text = self._sp.stream_record_and_transcribe(
                stop_event=self._stop_event,
                on_interim=lambda t: self.interim.emit(t),
            )
            self.finished.emit(text.strip())
        except Exception as exc:
            self.error.emit(str(exc))


class AgentWorker(QObject):
    """Runs VoiceAgent.chat_stream in a background thread."""

    token    = Signal(str)
    finished = Signal(str)
    error    = Signal(str)

    def __init__(self, agent: Any, user_text: str):
        super().__init__()
        self._agent = agent
        self._user_text = user_text

    @Slot()
    def run(self) -> None:
        try:
            full = []
            for tok in self._agent.chat_stream(self._user_text):
                full.append(tok)
                self.token.emit(tok)
            self.finished.emit("".join(full))
        except Exception as exc:
            self.error.emit(str(exc))


class SpeakWorker(QObject):
    """Runs TTS in a background thread."""

    finished = Signal()

    def __init__(self, speech_processor: Any, text: str):
        super().__init__()
        self._sp = speech_processor
        self._text = text

    @Slot()
    def run(self) -> None:
        try:
            self._sp.speak(self._text, async_=False)
        except Exception:
            pass
        self.finished.emit()


# ---------------------------------------------------------------------------
# Main Dialog
# ---------------------------------------------------------------------------

class VoiceConsultationDialog(QDialog):
    """Premium voice consultation dialog for Vibe Studio."""

    def __init__(
        self,
        provider: Any,
        workspace_root: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._provider = provider
        self._workspace_root = workspace_root

        # Lazy imports
        self._voice_agent: Any = None
        self._speech_processor: Any = None

        # Threading state
        self._listen_thread: QThread | None = None
        self._listen_worker: ListenWorker | None = None
        self._agent_thread: QThread | None = None
        self._agent_worker: AgentWorker | None = None
        self._speak_thread: QThread | None = None
        self._speak_worker: SpeakWorker | None = None
        self._stop_event = threading.Event()
        self._is_listening = False
        self._current_reply_label: QLabel | None = None

        self.setWindowTitle("🎙️ Voice Consultation — Vibe Studio")
        self.setMinimumSize(620, 700)
        self.resize(680, 760)
        self.setModal(False)
        self._apply_dialog_style()
        self._build_ui()
        self._init_agent()

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_dialog_style(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background: {_BG_DEEP};
                color: {_TEXT};
                font-family: "Inter", "Segoe UI", system-ui, sans-serif;
            }}
            QLabel {{
                color: {_TEXT};
                background: transparent;
            }}
            QComboBox {{
                background: {_BG_RAISED};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {_BG_RAISED};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                selection-background-color: {_BG_HOVER};
            }}
            QScrollArea {{
                background: {_BG_BASE};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {_BG_PANEL};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {_BG_HOVER};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────
        header = self._build_header()
        main_layout.addWidget(header)

        # ── Waveform ──────────────────────────────────────────────────
        self._waveform = WaveformWidget()
        main_layout.addWidget(self._waveform)

        # ── Status label ──────────────────────────────────────────────
        self._status_label = QLabel("Hazır — mikrofon düyməsinə basın")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet(
            f"QLabel {{ color: {_TEXT_DIM}; font-size: 12px; padding: 4px; }}"
        )
        main_layout.addWidget(self._status_label)

        # ── Transcript (interim speech) ───────────────────────────────
        self._transcript_label = QLabel("")
        self._transcript_label.setAlignment(Qt.AlignCenter)
        self._transcript_label.setWordWrap(True)
        self._transcript_label.setStyleSheet(
            f"QLabel {{ color: {_ACCENT}; font-size: 13px; font-style: italic; "
            f"background: {_BG_PANEL}; border-radius: 8px; padding: 6px 12px; "
            f"min-height: 32px; }}"
        )
        main_layout.addWidget(self._transcript_label)

        # ── Chat history ──────────────────────────────────────────────
        self._history_scroll = QScrollArea()
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setMinimumHeight(280)
        self._history_scroll.setStyleSheet(
            f"QScrollArea {{ background: {_BG_BASE}; border: 1px solid {_BORDER}; "
            f"border-radius: 10px; }}"
        )

        self._history_container = QWidget()
        self._history_container.setStyleSheet(f"background: {_BG_BASE};")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(8, 8, 8, 8)
        self._history_layout.setSpacing(6)
        self._history_layout.addStretch()
        self._history_scroll.setWidget(self._history_container)
        main_layout.addWidget(self._history_scroll, 1)

        # ── Controls ─────────────────────────────────────────────────
        controls = self._build_controls()
        main_layout.addWidget(controls)

        # ── Deps warning (shown if speech deps missing) ────────────────
        self._deps_warning = QLabel("")
        self._deps_warning.setWordWrap(True)
        self._deps_warning.setStyleSheet(
            f"QLabel {{ background: #2d1a00; color: {_WARN}; border: 1px solid #78350f; "
            f"border-radius: 6px; padding: 8px 12px; font-size: 11px; }}"
        )
        self._deps_warning.hide()
        main_layout.addWidget(self._deps_warning)

    def _build_header(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(
            f"QWidget {{ background: {_BG_PANEL}; border-radius: 10px; border: 1px solid {_BORDER}; }}"
        )
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Title
        title = QLabel("🎙️  Sesli Danışma Agenti")
        title.setStyleSheet(
            f"QLabel {{ font-size: 15px; font-weight: bold; color: {_TEXT}; "
            f"background: transparent; border: none; }}"
        )
        layout.addWidget(title)
        layout.addStretch()

        # Model selector
        model_lbl = QLabel("Model:")
        model_lbl.setStyleSheet(
            f"QLabel {{ color: {_TEXT_DIM}; font-size: 11px; background: transparent; border: none; }}"
        )
        layout.addWidget(model_lbl)

        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(160)
        self._model_combo.setToolTip("Sesli danışma üçün Ollama modeli seçin")
        self._populate_models()
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        layout.addWidget(self._model_combo)

        # TTS toggle
        self._tts_btn = QPushButton("🔊 TTS")
        self._tts_btn.setCheckable(True)
        self._tts_btn.setChecked(True)
        self._tts_btn.setFixedSize(68, 28)
        self._tts_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_RAISED}; color: {_TEXT_DIM}; border: 1px solid {_BORDER}; "
            f"border-radius: 6px; font-size: 11px; }}"
            f"QPushButton:checked {{ background: {_ACCENT}; color: white; border-color: {_ACCENT}; }}"
        )
        self._tts_btn.setToolTip("Agentin cavablarını oxu (TTS)")
        layout.addWidget(self._tts_btn)

        # Clear
        clear_btn = QPushButton("🗑️")
        clear_btn.setFixedSize(30, 28)
        clear_btn.setToolTip("Söhbət tarixini sil")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_RAISED}; color: {_TEXT_DIM}; border: 1px solid {_BORDER}; "
            f"border-radius: 6px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {_BG_HOVER}; color: {_TEXT}; }}"
        )
        clear_btn.clicked.connect(self._clear_history)
        layout.addWidget(clear_btn)

        return widget

    def _build_controls(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(
            f"QWidget {{ background: {_BG_PANEL}; border-radius: 12px; border: 1px solid {_BORDER}; }}"
        )
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Mic / Push-to-Talk button
        self._mic_btn = QPushButton("🎙️  Danış  (Space)")
        self._mic_btn.setFixedHeight(52)
        self._mic_btn.setMinimumWidth(200)
        self._mic_btn.setCheckable(True)
        self._mic_btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 #7c3aed, stop:1 {_ACCENT}); "
            f"color: white; border: none; border-radius: 10px; "
            f"font-size: 14px; font-weight: bold; letter-spacing: 0.5px; }}"
            f"QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 #6d28d9, stop:1 {_ACCENT_HOV}); }}"
            f"QPushButton:checked {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 #dc2626, stop:1 {_DANGER}); }}"
            f"QPushButton:disabled {{ background: {_BG_RAISED}; color: {_TEXT_DIM}; }}"
        )
        self._mic_btn.clicked.connect(self._toggle_listening)
        layout.addWidget(self._mic_btn, 2)

        # Stop speaking
        self._stop_btn = QPushButton("⏹ Dur")
        self._stop_btn.setFixedHeight(52)
        self._stop_btn.setFixedWidth(80)
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background: {_DANGER}; color: white; border: none; "
            f"border-radius: 10px; font-size: 13px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #e11d48; }}"
            f"QPushButton:disabled {{ background: {_BG_RAISED}; color: {_TEXT_DIM}; }}"
        )
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_all)
        layout.addWidget(self._stop_btn)

        return widget

    # ------------------------------------------------------------------
    # Keyboard shortcut — Space = Push-to-Talk
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if not self._is_listening:
                self._mic_btn.setChecked(True)
                self._toggle_listening()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if self._is_listening:
                self._stop_listening()
        super().keyReleaseEvent(event)

    # ------------------------------------------------------------------
    # Agent & speech init
    # ------------------------------------------------------------------

    def _init_agent(self) -> None:
        """Initialise VoiceAgent and SpeechProcessor (may fail gracefully)."""
        try:
            from vibe_studio.agents.voice_agent import VoiceAgent, VoiceAgentConfig
            from vibe_studio.agents.speech_processor import SpeechProcessor

            model = self._model_combo.currentText() or "qwen2.5:1.5b"
            self._voice_agent = VoiceAgent(
                provider=self._provider,
                model=model,
                workspace_root=self._workspace_root,
                config=VoiceAgentConfig(model=model, stream=True),
            )

            self._speech_processor = SpeechProcessor(
                whisper_model="base",
                language=None,  # auto-detect AZ/EN
            )

            # Check dependency availability
            avail = self._speech_processor.availability_summary()
            missing = [k for k, v in avail.items() if not v]
            if missing:
                hint = (
                    "Səs xüsusiyyətləri üçün əlavə paketlər lazımdır:\n"
                    "pip install faster-whisper sounddevice pyttsx3 numpy\n\n"
                    f"Əskik paketlər: {', '.join(missing)}"
                )
                self._deps_warning.setText(hint)
                self._deps_warning.show()
                self._mic_btn.setEnabled(False)
                self._mic_btn.setText("🎙️  Paket əskikdir")
                self._status_label.setText("Zəhmət olmasa əskik paketləri quraşdırın")

        except ImportError as exc:
            self._show_import_error(str(exc))

    def _show_import_error(self, msg: str) -> None:
        self._deps_warning.setText(
            f"Import xətası: {msg}\n"
            "Zəhmət olmasa tələb olunan paketləri quraşdırın."
        )
        self._deps_warning.show()
        self._mic_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Model selector
    # ------------------------------------------------------------------

    def _populate_models(self) -> None:
        self._model_combo.clear()
        # Voice-friendly defaults first
        VOICE_MODELS = [
            "qwen2.5:1.5b",
            "qwen2.5:3b",
            "llama3.2:1b",
            "llama3.2:3b",
            "gemma3:1b",
            "phi3.5:mini",
        ]
        try:
            from vibe_studio.providers.ollama_provider import OllamaProvider
            provider = OllamaProvider()
            local_models = [m.name for m in provider.list_models()]
            if local_models:
                for m in local_models:
                    self._model_combo.addItem(m)
                return
        except Exception:
            pass

        # Fallback — show recommended list
        for m in VOICE_MODELS:
            self._model_combo.addItem(m)

    def _on_model_changed(self, model: str) -> None:
        if self._voice_agent:
            self._voice_agent.model = model

    # ------------------------------------------------------------------
    # Listening control
    # ------------------------------------------------------------------

    def _toggle_listening(self) -> None:
        if self._is_listening:
            self._stop_listening()
        else:
            self._start_listening()

    def _start_listening(self) -> None:
        if self._speech_processor is None or not self._speech_processor.is_stt_available():
            self._status_label.setText("STT paketi quraşdırılmayıb")
            return

        self._is_listening = True
        self._stop_event.clear()
        self._mic_btn.setChecked(True)
        self._mic_btn.setText("⏹  Dinlənir…  (Space)")
        self._status_label.setText("🎙️  Dinlənir… (Space-i buraxın və ya düyməyə basın)")
        self._waveform.set_state(WaveformWidget.LISTENING)
        self._transcript_label.setText("")
        self._stop_btn.setEnabled(True)

        # Run STT in background thread
        self._listen_thread = QThread(self)
        self._listen_worker = ListenWorker(self._speech_processor, self._stop_event)
        self._listen_worker.moveToThread(self._listen_thread)
        self._listen_thread.started.connect(self._listen_worker.run)
        self._listen_worker.finished.connect(self._on_listening_finished)
        self._listen_worker.interim.connect(self._transcript_label.setText)
        self._listen_worker.error.connect(self._on_listen_error)
        self._listen_thread.start()

    def _stop_listening(self) -> None:
        if not self._is_listening:
            return
        self._stop_event.set()
        self._is_listening = False
        self._mic_btn.setChecked(False)
        self._mic_btn.setText("🎙️  Danış  (Space)")
        self._status_label.setText("⏳  Transkripsiya edilir…")
        self._waveform.set_state(WaveformWidget.THINKING)

    @Slot(str)
    def _on_listening_finished(self, text: str) -> None:
        if self._listen_thread:
            self._listen_thread.quit()
            self._listen_thread.wait()

        self._is_listening = False
        self._mic_btn.setChecked(False)
        self._mic_btn.setText("🎙️  Danış  (Space)")

        if not text:
            self._status_label.setText("Heç bir nitq aşkar edilmədi — yenidən cəhd edin")
            self._waveform.set_state(WaveformWidget.IDLE)
            return

        self._transcript_label.setText(f'"{text}"')
        self._add_bubble(text, "user")
        self._run_agent(text)

    @Slot(str)
    def _on_listen_error(self, error: str) -> None:
        self._status_label.setText(f"Xəta: {error}")
        self._waveform.set_state(WaveformWidget.IDLE)
        self._is_listening = False
        self._mic_btn.setChecked(False)
        self._mic_btn.setText("🎙️  Danış  (Space)")

    # ------------------------------------------------------------------
    # Agent run
    # ------------------------------------------------------------------

    def _run_agent(self, user_text: str) -> None:
        if self._voice_agent is None:
            self._status_label.setText("Agent hazır deyil")
            return

        self._status_label.setText("🤖  Agent düşünür…")
        self._waveform.set_state(WaveformWidget.THINKING)
        self._mic_btn.setEnabled(False)

        # Create a streaming reply bubble
        self._current_reply_label = self._create_streaming_bubble()

        self._agent_thread = QThread(self)
        self._agent_worker = AgentWorker(self._voice_agent, user_text)
        self._agent_worker.moveToThread(self._agent_thread)
        self._agent_thread.started.connect(self._agent_worker.run)
        self._agent_worker.token.connect(self._on_agent_token)
        self._agent_worker.finished.connect(self._on_agent_finished)
        self._agent_worker.error.connect(self._on_agent_error)
        self._agent_thread.start()

    @Slot(str)
    def _on_agent_token(self, token: str) -> None:
        if self._current_reply_label:
            current = self._current_reply_label.text()
            self._current_reply_label.setText(current + token)
            # Auto-scroll
            sb = self._history_scroll.verticalScrollBar()
            sb.setValue(sb.maximum())

    @Slot(str)
    def _on_agent_finished(self, full_reply: str) -> None:
        if self._agent_thread:
            self._agent_thread.quit()
            self._agent_thread.wait()

        self._current_reply_label = None
        self._mic_btn.setEnabled(True)
        self._mic_btn.setText("🎙️  Danış  (Space)")
        self._waveform.set_state(WaveformWidget.IDLE)
        self._status_label.setText("✅  Hazır — mikrofon düyməsinə basın")
        self._stop_btn.setEnabled(False)

        # TTS
        if self._tts_btn.isChecked() and full_reply and self._speech_processor:
            self._speak_reply(full_reply)

    @Slot(str)
    def _on_agent_error(self, error: str) -> None:
        self._mic_btn.setEnabled(True)
        self._waveform.set_state(WaveformWidget.IDLE)
        self._status_label.setText(f"Xəta: {error}")
        self._stop_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------

    def _speak_reply(self, text: str) -> None:
        self._waveform.set_state(WaveformWidget.SPEAKING)
        self._status_label.setText("🔊  Danışır…")

        self._speak_thread = QThread(self)
        self._speak_worker = SpeakWorker(self._speech_processor, text)
        self._speak_worker.moveToThread(self._speak_thread)
        self._speak_thread.started.connect(self._speak_worker.run)
        self._speak_worker.finished.connect(self._on_speaking_finished)
        self._speak_thread.start()

    @Slot()
    def _on_speaking_finished(self) -> None:
        if self._speak_thread:
            self._speak_thread.quit()
            self._speak_thread.wait()
        self._waveform.set_state(WaveformWidget.IDLE)
        self._status_label.setText("Hazır — mikrofon düyməsinə basın")

    # ------------------------------------------------------------------
    # Stop all
    # ------------------------------------------------------------------

    def _stop_all(self) -> None:
        self._stop_event.set()
        if self._voice_agent:
            self._voice_agent.stop()
        if self._speech_processor:
            self._speech_processor.stop_speaking()
        self._waveform.set_state(WaveformWidget.IDLE)
        self._status_label.setText("Dayandırıldı — hazır")
        self._mic_btn.setEnabled(True)
        self._mic_btn.setChecked(False)
        self._mic_btn.setText("🎙️  Danış  (Space)")
        self._stop_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Chat bubble helpers
    # ------------------------------------------------------------------

    def _add_bubble(self, text: str, role: str) -> None:
        """Add a completed bubble to the history."""
        bubble = ChatBubble(text, role)
        # Insert before the trailing stretch
        count = self._history_layout.count()
        self._history_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _create_streaming_bubble(self) -> QLabel:
        """Create an empty assistant bubble and return its label for token appends."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        row = QHBoxLayout(container)
        row.setContentsMargins(8, 4, 8, 4)

        icon = QLabel("🤖")
        icon.setFont(QFont("Segoe UI Emoji", 16))

        lbl = QLabel("")
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.PlainText)
        lbl.setFont(QFont("Inter", 12))
        lbl.setStyleSheet(
            f"QLabel {{ background: {_BG_RAISED}; color: {_TEXT}; "
            f"padding: 10px 14px; border-radius: 14px; "
            f"border-bottom-left-radius: 4px; }}"
        )
        lbl.setMaximumWidth(380)
        lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        row.addWidget(icon)
        row.addWidget(lbl)
        row.addStretch()

        count = self._history_layout.count()
        self._history_layout.insertWidget(count - 1, container)
        QTimer.singleShot(50, self._scroll_to_bottom)
        return lbl

    def _scroll_to_bottom(self) -> None:
        sb = self._history_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_history(self) -> None:
        # Remove all widgets except the final stretch
        while self._history_layout.count() > 1:
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if self._voice_agent:
            self._voice_agent.clear_history()
        self._transcript_label.setText("")
        self._status_label.setText("Söhbət tarixi silindi — hazır")

    # ------------------------------------------------------------------
    # Close event — clean up threads
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_all()
        for thread in [self._listen_thread, self._agent_thread, self._speak_thread]:
            if thread and thread.isRunning():
                thread.quit()
                thread.wait(2000)
        super().closeEvent(event)
