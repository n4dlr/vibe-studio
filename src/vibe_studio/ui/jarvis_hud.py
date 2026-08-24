"""JarvisHUDPanel — Cyber-Holographic Arc Reactor Cockpit & Voice Assistant.

Features:
- Animated Pulsing ARC Reactor widget with rotating holographic energy rings
- Real-time hardware telemetry HUD gauges (CPU, RAM, Disk, Uptime, Battery)
- Voice Command Center with Push-to-Talk and text command box
- System Actions Toolbar (Browser, Screenshot, Volume, Pytest, Diagnostics)
- Spoken vocal feedback with mute/unmute control
"""
from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
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

_BG_DEEP    = "#08090f"
_BG_PANEL   = "#0e101a"
_BG_RAISED  = "#151828"
_BORDER     = "#1f243d"
_CYAN       = "#00f0ff"
_CYAN_DIM   = "rgba(0, 240, 255, 0.3)"
_GOLD       = "#fbbf24"
_TEXT       = "#f1f5f9"
_TEXT_MUTED = "#64748b"


class ArcReactorWidget(QWidget):
    """Pulsing holographic Iron Man Arc Reactor with rotating rings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(140, 140)
        self._angle = 0.0
        self._pulse = 0.0
        self._is_active = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)  # ~33 fps

    def _animate(self) -> None:
        self._angle = (self._angle + 1.5) % 360.0
        self._pulse = (self._pulse + 0.05) % (2 * math.pi)
        self.update()

    def paintEvent(self, _) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r_max = min(w, h) / 2.0 - 6

        # Outer glowing ring
        pulse_val = (math.sin(self._pulse) + 1.0) / 2.0  # 0..1
        glow_alpha = int(40 + pulse_val * 60)
        painter.setPen(QPen(QColor(0, 240, 255, glow_alpha), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r_max, r_max)

        # Rotating segmented middle ring
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle)
        pen_seg = QPen(QColor(_CYAN), 2.5)
        painter.setPen(pen_seg)
        for i in range(8):
            painter.drawArc(QRectF(-r_max + 12, -r_max + 12, (r_max - 12) * 2, (r_max - 12) * 2), int(i * 45 * 16), int(30 * 16))
        painter.restore()

        # Counter-rotating inner ring
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._angle * 1.5)
        painter.setPen(QPen(QColor(251, 191, 36, 180), 1.5))
        for i in range(6):
            painter.drawArc(QRectF(-r_max + 26, -r_max + 26, (r_max - 26) * 2, (r_max - 26) * 2), int(i * 60 * 16), int(40 * 16))
        painter.restore()

        # Center core with radial gradient
        core_r = r_max - 36 + pulse_val * 4
        rad_grad = QRadialGradient(cx, cy, core_r)
        rad_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        rad_grad.setColorAt(0.5, QColor(0, 240, 255, 180))
        rad_grad.setColorAt(1.0, QColor(0, 240, 255, 20))
        painter.setPen(Qt.NoPen)
        painter.setBrush(rad_grad)
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)


class JarvisHUDPanel(QWidget):
    """JARVIS holographic control center and voice assistant panel."""

    def __init__(self, workspace_root: str | Path = ".", parent=None):
        super().__init__(parent)
        self.workspace_root = Path(workspace_root).resolve()
        self.jarvis = JarvisCore(self.workspace_root)
        self._setup_ui()

        # 2-second telemetry refresh timer
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self._refresh_telemetry)
        self._telemetry_timer.start(2000)
        self._refresh_telemetry()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header with Arc Reactor & Status
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_BG_PANEL}, stop:1 {_BG_RAISED});
                border: 1px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        hdr_layout = QHBoxLayout(hdr_frame)
        hdr_layout.setContentsMargins(12, 10, 12, 10)
        hdr_layout.setSpacing(14)

        self.reactor = ArcReactorWidget()
        hdr_layout.addWidget(self.reactor)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        title_lbl = QLabel("⚡ J.A.R.V.I.S")
        title_lbl.setFont(QFont("Inter", 16, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {_CYAN}; letter-spacing: 2px;")
        info_layout.addWidget(title_lbl)

        sub_lbl = QLabel("Autonomous Operating System & Voice Agent · Online")
        sub_lbl.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 11px;")
        info_layout.addWidget(sub_lbl)

        # Status pills
        pill_layout = QHBoxLayout()
        self.cpu_pill = QLabel("CPU: 0%")
        self.cpu_pill.setStyleSheet(f"background: {_BG_DEEP}; color: {_CYAN}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;")
        self.ram_pill = QLabel("RAM: 0 GB")
        self.ram_pill.setStyleSheet(f"background: {_BG_DEEP}; color: {_GOLD}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;")
        self.uptime_pill = QLabel("Uptime: 0h")
        self.uptime_pill.setStyleSheet(f"background: {_BG_DEEP}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 2px 8px; font-size: 11px;")
        pill_layout.addWidget(self.cpu_pill)
        pill_layout.addWidget(self.ram_pill)
        pill_layout.addWidget(self.uptime_pill)
        pill_layout.addStretch()
        info_layout.addLayout(pill_layout)

        hdr_layout.addLayout(info_layout, 1)
        layout.addWidget(hdr_frame)

        # Quick Action Chips
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)
        chips = [
            ("⚡ Diagnostics", "system status"),
            ("🌐 Browser", "open chrome"),
            ("📸 Screenshot", "take screenshot"),
            ("🧪 Run Tests", "run tests"),
            ("⬛ Terminal", "open terminal"),
        ]
        for label, cmd in chips:
            btn = QPushButton(label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_BG_RAISED};
                    color: {_TEXT};
                    border: 1px solid {_BORDER};
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 11px;
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

        # Telemetry & Output Splitter
        splitter = QSplitter(Qt.Vertical)

        # Output Log Box
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setPlaceholderText("J.A.R.V.I.S responses and voice activity log appear here…")
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
        splitter.addWidget(self.output_box)

        layout.addWidget(splitter, 1)

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

        mic_btn = QPushButton("🎙️")
        mic_btn.setFixedSize(32, 32)
        mic_btn.setToolTip("Push-to-Talk / Voice Command")
        mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CYAN};
                color: #000000;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #67e8f9;
            }}
        """)
        mic_btn.clicked.connect(self._on_mic_clicked)
        input_layout.addWidget(mic_btn)

        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Tell Jarvis anything... (e.g. 'Jarvis, check system status' or 'open browser')")
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

        send_btn = QPushButton("⚡ Execute")
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
        """Update hardware monitor status pills."""
        snap = self.jarvis.telemetry.get_snapshot()
        self.cpu_pill.setText(f"CPU: {snap.cpu_percent:.0f}%")
        self.ram_pill.setText(f"RAM: {snap.ram_used_gb:.1f} / {snap.ram_total_gb:.0f} GB")
        self.uptime_pill.setText(f"Uptime: {snap.uptime_hours:.1f}h")

    def _on_enter(self) -> None:
        text = self.cmd_input.text().strip()
        if not text:
            return
        self.cmd_input.clear()
        self._send_command(text)

    def _send_command(self, cmd: str) -> None:
        self.output_box.append(f"<span style='color:{_CYAN}; font-weight:bold;'>YOU:</span> {cmd}")
        resp = self.jarvis.execute_command(cmd)
        self.output_box.append(f"<span style='color:{_GOLD}; font-weight:bold;'>JARVIS:</span> {resp.spoken_text}\n")
        self.output_box.ensureCursorVisible()

    def _on_mic_clicked(self) -> None:
        """Trigger voice command consultation dialog."""
        parent_win = self.window()
        if hasattr(parent_win, "_open_voice_consultation"):
            parent_win._open_voice_consultation()
        else:
            self._send_command("system status")
