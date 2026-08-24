"""JarvisFloatingAvatar — Interactive Floating Mini J.A.R.V.I.S Avatar & Voice HUD.

Features:
- Floating holographic Arc-Reactor portrait widget (64x64) with rotating rings and pulsing energy core
- Live animation states: IDLE, LISTENING, THINKING, SPEAKING
- Expandable voice command bubble on click / hover
- Spoken audio playback and voice interaction
- Quick action buttons (Diagnostics, Push-to-Talk, Screenshot, Full HUD)
- Draggable across the window canvas
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.jarvis.engine import JarvisCore

_CYAN       = "#00f0ff"
_GOLD       = "#fbbf24"
_GREEN      = "#10b981"
_BG_DEEP    = "#080912"
_BG_PANEL   = "#0f1322"
_BORDER     = "#1e2640"
_TEXT       = "#e2e8f0"
_TEXT_MUTED = "#64748b"


class MiniReactorPortrait(QWidget):
    """Animated 60x60 Arc Reactor portrait."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 60)
        self._angle = 0.0
        self._pulse = 0.0
        self._state = "IDLE"  # "IDLE" | "LISTENING" | "THINKING" | "SPEAKING"

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def _tick(self) -> None:
        speed = 4.0 if self._state == "THINKING" else 1.5
        self._angle = (self._angle + speed) % 360.0
        self._pulse = (self._pulse + 0.08) % (2 * math.pi)
        self.update()

    def paintEvent(self, _) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = min(cx, cy) - 4

        # Glow color based on state
        glow_color = QColor(_CYAN)
        if self._state == "LISTENING":
            glow_color = QColor(_GREEN)
        elif self._state == "THINKING":
            glow_color = QColor(_GOLD)
        elif self._state == "SPEAKING":
            glow_color = QColor(244, 63, 94)

        pulse_factor = (math.sin(self._pulse) + 1.0) / 2.0
        glow_alpha = int(50 + pulse_factor * 80)

        # Outer glowing boundary
        painter.setPen(QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), glow_alpha), 2.5))
        painter.setBrush(QColor(10, 14, 26, 220))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # Rotating outer notches
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle)
        painter.setPen(QPen(glow_color, 2.0))
        for i in range(6):
            painter.drawArc(QRectF(-r + 6, -r + 6, (r - 6) * 2, (r - 6) * 2), int(i * 60 * 16), int(35 * 16))
        painter.restore()

        # Counter rotating inner ring
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._angle * 1.5)
        painter.setPen(QPen(QColor(_GOLD if self._state != "LISTENING" else _GREEN), 1.5))
        for i in range(4):
            painter.drawArc(QRectF(-r + 14, -r + 14, (r - 14) * 2, (r - 14) * 2), int(i * 90 * 16), int(50 * 16))
        painter.restore()

        # Center core energy
        core_r = max(4.0, (r - 18) + pulse_factor * 3)
        rad_grad = QRadialGradient(cx, cy, core_r)
        rad_grad.setColorAt(0.0, QColor(255, 255, 255, 250))
        rad_grad.setColorAt(0.6, glow_color)
        rad_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(rad_grad)
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)


class JarvisFloatingAvatar(QWidget):
    """Draggable mini floating J.A.R.V.I.S portrait with interactive command overlay."""

    hud_open_requested = Signal()

    def __init__(self, workspace_root: str | Path = ".", parent: QWidget | None = None):
        super().__init__(parent)
        self.workspace_root = Path(workspace_root).resolve()
        self.jarvis = JarvisCore(self.workspace_root)
        self.jarvis.voice_engine.add_state_callback(self._on_speech_state_change)

        self.setWindowFlags(Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._is_expanded = False
        self._drag_pos = QPoint()

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(6)

        # ── Expanded Command Card (Popup) ─────────────────────────────────
        self.popup_card = QFrame()
        self.popup_card.setFixedWidth(280)
        self.popup_card.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_PANEL};
                border: 1px solid {_CYAN};
                border-radius: 12px;
                padding: 4px;
            }}
        """)
        card_layout = QVBoxLayout(self.popup_card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)

        # Card Title
        hdr_row = QHBoxLayout()
        title_lbl = QLabel("⚡ J.A.R.V.I.S")
        title_lbl.setFont(QFont("Inter", 11, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {_CYAN}; font-weight: 700;")
        hdr_row.addWidget(title_lbl)
        hdr_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.setStyleSheet(f"background: transparent; color: {_TEXT_MUTED}; border: none; font-size: 11px;")
        close_btn.clicked.connect(self._toggle_popup)
        hdr_row.addWidget(close_btn)
        card_layout.addLayout(hdr_row)

        # Speech bubble
        self.bubble_lbl = QLabel("Ready for your command, sir.")
        self.bubble_lbl.setWordWrap(True)
        self.bubble_lbl.setStyleSheet(f"""
            background: {_BG_DEEP};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            border-radius: 8px;
            padding: 8px;
            font-size: 11px;
        """)
        card_layout.addWidget(self.bubble_lbl)

        # Quick action buttons
        actions_row = QHBoxLayout()
        actions_row.setSpacing(4)
        for label, cmd in [("⚡ Status", "system status"), ("📸 Shot", "take screenshot"), ("🎙️ Mic", "__mic__"), ("🚀 HUD", "__hud__")]:
            b = QPushButton(label)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {_BG_DEEP};
                    color: {_TEXT};
                    border: 1px solid {_BORDER};
                    border-radius: 4px;
                    padding: 3px 6px;
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    border-color: {_CYAN};
                    color: {_CYAN};
                }}
            """)
            b.clicked.connect(lambda _, c=cmd: self._handle_quick_action(c))
            actions_row.addWidget(b)
        card_layout.addLayout(actions_row)

        # Command input
        cmd_row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Ask Jarvis...")
        self.cmd_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_BG_DEEP};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {_CYAN};
            }}
        """)
        self.cmd_input.returnPressed.connect(self._on_submit_cmd)
        cmd_row.addWidget(self.cmd_input, 1)

        exec_btn = QPushButton("⚡")
        exec_btn.setFixedSize(26, 26)
        exec_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CYAN};
                color: #000;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #67e8f9;
            }}
        """)
        exec_btn.clicked.connect(self._on_submit_cmd)
        cmd_row.addWidget(exec_btn)
        card_layout.addLayout(cmd_row)

        self.popup_card.setVisible(False)
        self.main_layout.addWidget(self.popup_card)

        # ── Floating Portrait Orb (Bottom) ────────────────────────────────
        orb_row = QHBoxLayout()
        orb_row.addStretch()

        self.portrait = MiniReactorPortrait(self)
        self.portrait.setCursor(Qt.PointingHandCursor)
        self.portrait.setToolTip("J.A.R.V.I.S — Click to talk or command (Ctrl+Shift+J)")
        self.portrait.mousePressEvent = self._on_portrait_clicked
        orb_row.addWidget(self.portrait)

        self.main_layout.addLayout(orb_row)

    def _on_portrait_clicked(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._toggle_popup()

    def _toggle_popup(self) -> None:
        self._is_expanded = not self._is_expanded
        self.popup_card.setVisible(self._is_expanded)
        if self._is_expanded:
            self.cmd_input.setFocus()

    def _handle_quick_action(self, cmd: str) -> None:
        if cmd == "__hud__":
            self.hud_open_requested.emit()
            self._toggle_popup()
        elif cmd == "__mic__":
            parent_win = self.window()
            if hasattr(parent_win, "_open_voice_consultation"):
                parent_win._open_voice_consultation()
        else:
            self._run_command(cmd)

    def _on_submit_cmd(self) -> None:
        text = self.cmd_input.text().strip()
        if not text:
            return
        self.cmd_input.clear()
        self._run_command(text)

    def _run_command(self, cmd: str) -> None:
        self.portrait.set_state("THINKING")
        self.bubble_lbl.setText(f"Processing: {cmd}…")
        resp = self.jarvis.execute_command(cmd)
        self.bubble_lbl.setText(resp.spoken_text)
        self.portrait.set_state("IDLE")

    def _on_speech_state_change(self, is_speaking: bool) -> None:
        self.portrait.set_state("SPEAKING" if is_speaking else "IDLE")

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.RightButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
