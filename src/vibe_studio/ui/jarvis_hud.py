"""JarvisHUDPanel — Titan Cyber-Holographic Arc Reactor Cockpit & Full Agentic Voice Assistant.

Features:
- Animated Holographic Arc Reactor widget with rotating kinetic rings and audio reactivity
- Real-Time Microphone Push-to-Talk Speech-to-Text (faster-whisper STT in Azerbaijani & English)
- Full Agentic Coding & OS Execution (writes files, runs commands, tests, launches desktop apps)
- Dynamic AI Model Selector (qwen2.5-coder:14b, qwen3:8b, deepseek-coder-v2:lite, etc.)
- Neural Voice Persona Selector (British Butler Ryan, Azerbaijani Babek, Modern AI Christopher)
- Proactive Watchdog Sentinel Toggle (Hardware overload protection)
- Telemetry HUD with real-time CPU, RAM, Disk, and Network Ping
"""
from __future__ import annotations

import math
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.jarvis.engine import JarvisCore, JarvisResponse

_BG_DEEP    = "#070810"
_BG_PANEL   = "#0d101d"
_BG_RAISED  = "#13172c"
_BORDER     = "#1c2340"
_CYAN       = "#00f0ff"
_CYAN_DIM   = "rgba(0, 240, 255, 0.25)"
_GOLD       = "#fbbf24"
_GREEN      = "#10b981"
_TEXT       = "#f1f5f9"
_TEXT_MUTED = "#64748b"


class ArcReactorWidget(QWidget):
    """Pulsing holographic Iron Man Arc Reactor with rotating rings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 130)
        self._angle = 0.0
        self._pulse = 0.0
        self._is_active = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)

    def _animate(self) -> None:
        self._angle = (self._angle + 1.5) % 360.0
        self._pulse = (self._pulse + 0.06) % (2 * math.pi)
        self.update()

    def paintEvent(self, _) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r_max = min(w, h) / 2.0 - 6

        pulse_val = (math.sin(self._pulse) + 1.0) / 2.0
        glow_alpha = int(45 + pulse_val * 65)

        # Outer ring
        painter.setPen(QPen(QColor(0, 240, 255, glow_alpha), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r_max, r_max)

        # Rotating outer segment
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle)
        painter.setPen(QPen(QColor(_CYAN), 2.5))
        for i in range(8):
            painter.drawArc(QRectF(-r_max + 12, -r_max + 12, (r_max - 12) * 2, (r_max - 12) * 2), int(i * 45 * 16), int(30 * 16))
        painter.restore()

        # Counter-rotating inner ring
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._angle * 1.5)
        painter.setPen(QPen(QColor(251, 191, 36, 180), 1.5))
        for i in range(6):
            painter.drawArc(QRectF(-r_max + 24, -r_max + 24, (r_max - 24) * 2, (r_max - 24) * 2), int(i * 60 * 16), int(40 * 16))
        painter.restore()

        # Center glowing core
        core_r = r_max - 34 + pulse_val * 4
        rad_grad = QRadialGradient(cx, cy, core_r)
        rad_grad.setColorAt(0.0, QColor(255, 255, 255, 250))
        rad_grad.setColorAt(0.5, QColor(0, 240, 255, 180))
        rad_grad.setColorAt(1.0, QColor(0, 240, 255, 15))
        painter.setPen(Qt.NoPen)
        painter.setBrush(rad_grad)
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)


class VoiceBridge(QObject):
    """Thread-safe Qt signal bridge for audio transcription and wake-word events."""
    transcription_ready = Signal(str)


class JarvisHUDPanel(QWidget):
    """Full Agentic J.A.R.V.I.S holographic cockpit and voice intelligence panel."""

    def __init__(self, workspace_root: str | Path = ".", parent=None):
        super().__init__(parent)
        self.workspace_root = Path(workspace_root).resolve()
        self.jarvis = JarvisCore(self.workspace_root)
        self.jarvis.add_event_callback(self._on_jarvis_event)
        self.jarvis.start_sentinel()
        self._is_voice_recording = False

        # Thread-safe Voice Bridge for GUI STT
        self._voice_bridge = VoiceBridge()
        self._voice_bridge.transcription_ready.connect(self._on_transcribed)
        self.jarvis.voice_listener.on_wake_word = lambda w: self._voice_bridge.transcription_ready.emit(w)

        self._setup_ui()


        # Telemetry refresh timer (every 2 seconds)
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self._refresh_telemetry)
        self._telemetry_timer.start(2000)
        self._refresh_telemetry()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header Frame
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_BG_PANEL}, stop:1 {_BG_RAISED});
                border: 1px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        hdr_layout = QHBoxLayout(hdr_frame)
        hdr_layout.setContentsMargins(10, 8, 10, 8)
        hdr_layout.setSpacing(12)

        self.reactor = ArcReactorWidget()
        hdr_layout.addWidget(self.reactor)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        # Title + Selectors Row
        title_row = QHBoxLayout()
        title_lbl = QLabel("⚡ J.A.R.V.I.S")
        title_lbl.setFont(QFont("Inter", 15, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {_CYAN}; letter-spacing: 2px;")
        title_row.addWidget(title_lbl)

        # AI Model Selector
        self.model_combo = QComboBox()
        self.model_combo.setMaximumWidth(135)
        available_models = self.jarvis.list_available_models()
        self.model_combo.addItems(available_models)
        if self.jarvis.model in available_models:
            self.model_combo.setCurrentText(self.jarvis.model)
        self.model_combo.setStyleSheet(f"""
            QComboBox {{
                background: {_BG_DEEP};
                color: {_GOLD};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        title_row.addWidget(self.model_combo)

        # Voice Persona / Gender Selector
        self.voice_combo = QComboBox()
        self.voice_combo.setMaximumWidth(140)
        self.voice_combo.addItems([
            "🇦🇿 Banu (Qadın)",
            "🇦🇿 Babək (Kişi)",
            "🇬🇧 Ryan (Butler)",
            "🇺🇸 Jenny (Friday)",
            "🇺🇸 Christopher",
            "🇹🇷 Emel (Kadın)",
            "🇹🇷 Ahmet (Erkek)",
        ])
        self.voice_combo.setStyleSheet(f"""
            QComboBox {{
                background: {_BG_DEEP};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
            }}
        """)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        title_row.addWidget(self.voice_combo)

        # Wake-Word Live Listener Toggle
        self.wake_btn = QPushButton("🎙️ Wake: OFF")
        self.wake_btn.setMaximumWidth(90)
        self.wake_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BG_DEEP};
                color: {_TEXT_MUTED};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        self.wake_btn.clicked.connect(self._toggle_wake_word)
        title_row.addWidget(self.wake_btn)

        # Sentinel Watchdog Toggle
        self.sentinel_btn = QPushButton("🛡️ Sentinel: ON")
        self.sentinel_btn.setMaximumWidth(95)
        self.sentinel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BG_DEEP};
                color: {_GREEN};
                border: 1px solid {_GREEN};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        self.sentinel_btn.clicked.connect(self._toggle_sentinel)
        title_row.addWidget(self.sentinel_btn)
        title_row.addStretch()


        info_layout.addLayout(title_row)


        sub_lbl = QLabel("Full Agentic Autonomous Intelligence · Bilingual Neural Voice · OS & Software Engineer")
        sub_lbl.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 11px;")
        info_layout.addWidget(sub_lbl)

        # Telemetry Status Pills
        pill_layout = QHBoxLayout()
        self.cpu_pill = QLabel("CPU: 0%")
        self.cpu_pill.setStyleSheet(f"background: {_BG_DEEP}; color: {_CYAN}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold;")
        self.ram_pill = QLabel("RAM: 0 GB")
        self.ram_pill.setStyleSheet(f"background: {_BG_DEEP}; color: {_GOLD}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold;")
        self.model_pill = QLabel(f"Brain: {self.jarvis.model}")
        self.model_pill.setStyleSheet(f"background: {_BG_DEEP}; color: {_CYAN}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 6px; font-size: 11px;")
        self.net_pill = QLabel("Net: Online")
        self.net_pill.setStyleSheet(f"background: {_BG_DEEP}; color: {_GREEN}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 6px; font-size: 11px;")
        self.uptime_pill = QLabel("Uptime: 0h")
        self.uptime_pill.setStyleSheet(f"background: {_BG_DEEP}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 6px; font-size: 11px;")

        pill_layout.addWidget(self.cpu_pill)
        pill_layout.addWidget(self.ram_pill)
        pill_layout.addWidget(self.model_pill)
        pill_layout.addWidget(self.net_pill)
        pill_layout.addWidget(self.uptime_pill)
        pill_layout.addStretch()
        info_layout.addLayout(pill_layout)

        hdr_layout.addLayout(info_layout, 1)
        layout.addWidget(hdr_frame)

        # Quick Action Chips Toolbar
        chips_layout = QHBoxLayout()
        chips = [
            ("⚡ Status", "system status"),
            ("🌐 Browser", "open browser"),
            ("💻 Terminal", "open terminal"),
            ("🧪 Run Tests", "run tests"),
            ("🔒 Lock PC", "lock screen"),
            ("📸 Screenshot", "take screenshot"),
            ("🧹 Clean Cache", "clean cache"),
        ]

        for label, cmd in chips:
            btn = QPushButton(label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_BG_RAISED};
                    color: {_TEXT};
                    border: 1px solid {_BORDER};
                    border-radius: 5px;
                    padding: 4px 8px;
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    background: {_CYAN_DIM};
                    color: #ffffff;
                    border-color: {_CYAN};
                }}
            """)
            btn.clicked.connect(lambda _, c=cmd: self._send_command(c))
            chips_layout.addWidget(btn)
        chips_layout.addStretch()
        layout.addLayout(chips_layout)

        # Output Log Box
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setPlaceholderText("J.A.R.V.I.S Agentic dialogue, code actions, and real-time voice transcripts appear here…")
        self.output_box.setStyleSheet(f"""
            QTextEdit {{
                background: {_BG_DEEP};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
                font-family: Consolas, Monaco, monospace;
            }}
        """)
        layout.addWidget(self.output_box, 1)

        # Voice & Command Input Bar
        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            QFrame {{
                background: {_BG_RAISED};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(6, 4, 6, 4)
        input_layout.setSpacing(6)

        self.mic_btn = QPushButton("🎙️ Səsli")
        self.mic_btn.setFixedSize(70, 32)
        self.mic_btn.setToolTip("Klikləyin və səsli danışın (Azərbaycan və ya İngiliscə)")
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CYAN};
                color: #000000;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #67e8f9;
            }}
        """)
        self.mic_btn.clicked.connect(self._on_mic_toggle)
        input_layout.addWidget(self.mic_btn)

        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Jarvis-ə istənilən tapşırığı verin... ('Mənə bir FastAPI serveri yaz', 'create simple nodejs file', 'status')")

        self.cmd_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_BG_DEEP};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {_CYAN};
            }}
        """)
        self.cmd_input.returnPressed.connect(self._on_enter)
        input_layout.addWidget(self.cmd_input, 1)

        send_btn = QPushButton("⚡ İcra Et")
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BG_PANEL};
                color: {_CYAN};
                border: 1px solid {_CYAN};
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {_CYAN};
                color: #000000;
            }}
        """)
        send_btn.clicked.connect(self._on_enter)
        input_layout.addWidget(send_btn)

        layout.addWidget(input_frame)

    def _refresh_telemetry(self) -> None:
        snap = self.jarvis.telemetry.get_snapshot()
        self.cpu_pill.setText(f"CPU: {snap.cpu_percent:.0f}%")
        self.ram_pill.setText(f"RAM: {snap.ram_used_gb:.1f} / {snap.ram_total_gb:.0f} GB")
        self.uptime_pill.setText(f"Uptime: {snap.uptime_hours:.1f}h")

    def _on_model_changed(self, model_name: str) -> None:
        if model_name:
            self.jarvis.set_model(model_name)
            self.model_pill.setText(f"Brain: {model_name}")
            self.output_box.append(f"<span style='color:{_GOLD}; font-style:italic;'>[System] J.A.R.V.I.S brain switched to {model_name}</span>\n")
            self.jarvis.speak(f"Neural model updated to {model_name}, sir.")

    def _on_voice_changed(self, index: int) -> None:
        persona_keys = ["banu", "babek", "ryan", "friday", "modern", "emel", "ahmet"]
        if 0 <= index < len(persona_keys):
            p = persona_keys[index]
            self.jarvis.voice_engine.set_persona(p)
            v_info = self.jarvis.voice_engine.get_current_voice_info()
            g_name = "Qadın (Banu)" if p == "banu" else ("Kişi (Babək)" if p == "babek" else p.capitalize())
            self.output_box.append(f"<span style='color:{_GOLD}; font-style:italic;'>[Voice] Səs '{g_name}' olaraq dəyişdirildi.</span>\n")
            self.jarvis.speak("Səs tənzimləməsi yeniləndi, cənab.")

    def _toggle_wake_word(self) -> None:
        if self.jarvis.voice_listener.is_wake_word_active:
            self.jarvis.voice_listener.stop_wake_word_daemon()
            self.wake_btn.setText("🎙️ Wake: OFF")
            self.wake_btn.setStyleSheet(f"background: {_BG_DEEP}; color: {_TEXT_MUTED}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 8px; font-size: 10px;")
            self.output_box.append("<span style='color:#94a3b8; font-style:italic;'>[Wake-Word] Canlı dinləmə dayandırıldı.</span>\n")
        else:
            self.jarvis.voice_listener.start_wake_word_daemon()
            self.wake_btn.setText("🎙️ Wake: ON")
            self.wake_btn.setStyleSheet(f"background: {_BG_DEEP}; color: {_CYAN}; border: 1px solid {_CYAN}; border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: bold;")
            self.output_box.append("<span style='color:#38bdf8; font-style:italic;'>[Wake-Word] Canlı 'Hey Jarvis' dinləməsi aktivdir!</span>\n")
            self.jarvis.speak("Canlı dinləmə aktivdir, cənab.")


    def _toggle_sentinel(self) -> None:
        if self.jarvis.watchdog.is_running:
            self.jarvis.stop_sentinel()
            self.sentinel_btn.setText("🛡️ Sentinel: OFF")
            self.sentinel_btn.setStyleSheet(f"background: {_BG_DEEP}; color: {_TEXT_MUTED}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 8px; font-size: 10px;")
        else:
            self.jarvis.start_sentinel()
            self.sentinel_btn.setText("🛡️ Sentinel: ON")
            self.sentinel_btn.setStyleSheet(f"background: {_BG_DEEP}; color: {_GREEN}; border: 1px solid {_GREEN}; border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: bold;")

    def _on_enter(self) -> None:
        text = self.cmd_input.text().strip()
        if not text:
            return
        self.cmd_input.clear()
        self._send_command(text)

    def _send_command(self, cmd: str) -> None:
        self.output_box.append(f"<span style='color:{_CYAN}; font-weight:bold;'>YOU:</span> {cmd}")
        resp = self.jarvis.execute_command(cmd)
        self.output_box.append(f"<span style='color:{_GOLD}; font-weight:bold;'>JARVIS ({resp.model_used}):</span> {resp.spoken_text}\n")
        if resp.files_modified:
            self.output_box.append(f"<span style='color:{_GREEN}; font-weight:bold;'>📁 Modified Files:</span> {', '.join(resp.files_modified)}\n")
        self.output_box.ensureCursorVisible()

    def _on_mic_toggle(self) -> None:
        """Toggle real-time microphone recording and speech recognition."""
        if not self._is_voice_recording:
            started = self.jarvis.voice_listener.start_recording()
            if started:
                self._is_voice_recording = True
                self.mic_btn.setText("🔴 Dinləyirəm")
                self.mic_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #ef4444;
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        font-size: 10px;
                        font-weight: bold;
                    }}
                """)
                self.output_box.append("<span style='color:#ef4444; font-style:italic;'>🎙️ [Mikrofon Aktivdir] Danışın, bitəndə yenidən düyməyə basın...</span>\n")
        else:
            self._is_voice_recording = False
            self.mic_btn.setText("⏳ Tanıyır...")
            self.mic_btn.setStyleSheet(f"background: {_GOLD}; color: #000; border-radius: 6px; font-size: 10px; font-weight: bold;")

            def _transcribe_bg():
                text = self.jarvis.voice_listener.stop_recording_and_transcribe()
                # Run back on Qt event loop via QTimer.singleShot
                QTimer.singleShot(0, lambda: self._on_transcribed(text))

            threading.Thread(target=_transcribe_bg, daemon=True).start()

    def _on_transcribed(self, recognized_text: str) -> None:
        self.mic_btn.setText("🎙️ Səsli")
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CYAN};
                color: #000000;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        if recognized_text:
            self.output_box.append(f"<span style='color:#38bdf8; font-style:italic;'>🗣️ [Tanındı]: {recognized_text}</span>\n")
            self._send_command(recognized_text)
        else:
            self.output_box.append("<span style='color:#94a3b8; font-style:italic;'>[Audio] Səs aşkar edilmədi.</span>\n")

    def _on_jarvis_event(self, event_type: str, data: dict) -> None:
        if event_type == "watchdog_alert":
            self.output_box.append(f"<span style='color:#ef4444; font-weight:bold;'>⚠️ SENTINEL ALERT:</span> {data.get('message', '')}\n")
            self.output_box.ensureCursorVisible()
