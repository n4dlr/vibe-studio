"""JarvisStandaloneWindow — Detached Cyber-Holographic J.A.R.V.I.S Window with Aero Edge Snapping.

Features:
- Standalone detached desktop window independent from the main IDE window
- Windows-like Aero Edge Snapping:
  * Dragging to Left Edge -> Snaps to Left Half Screen (50% width, 100% height)
  * Dragging to Right Edge -> Snaps to Right Half Screen (50% width, 100% height)
  * Dragging to Top Edge -> Snaps to Full Screen (Maximized)
  * Magnetic edge attraction when within 25px of any screen boundary
  * Dragging away from snapped state restores original floating size
- Custom Cyber Titlebar with Snap-Left (◧), Snap-Right (◨), Pin-on-Top (📌), Maximize (◻), Minimize (—), and Close (✕)
- Direct integration with JarvisHUDPanel & Neural Voice Engine
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.ui.jarvis_hud import JarvisHUDPanel

_BG_DEEP    = "#070810"
_BG_PANEL   = "#0d101d"
_BG_RAISED  = "#13172c"
_BORDER     = "#1c2340"
_CYAN       = "#00f0ff"
_CYAN_DIM   = "rgba(0, 240, 255, 0.18)"
_GOLD       = "#fbbf24"
_GREEN      = "#10b981"
_TEXT       = "#f1f5f9"
_TEXT_MUTED = "#64748b"


class JarvisTitleBar(QFrame):
    """Custom Glassmorphic Cyber Title Bar for J.A.R.V.I.S Window."""

    def __init__(self, parent_window: JarvisStandaloneWindow):
        super().__init__(parent_window)
        self.win = parent_window
        self._drag_pos: QPoint | None = None

        self.setFixedHeight(38)
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_BG_DEEP}, stop:1 {_BG_PANEL});
                border-bottom: 1px solid {_BORDER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(6)

        # Title & Icon
        title_lbl = QLabel("⚡ J.A.R.V.I.S · Autonomous Cockpit")
        title_lbl.setFont(QFont("Inter", 11, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {_CYAN}; letter-spacing: 1px;")
        layout.addWidget(title_lbl)

        layout.addStretch()

        # 📌 Pin On Top
        self.pin_btn = QPushButton("📌")
        self.pin_btn.setFixedSize(26, 26)
        self.pin_btn.setToolTip("Toggle Always on Top")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setStyleSheet(self._btn_style())
        self.pin_btn.clicked.connect(self.win.toggle_pin_on_top)
        layout.addWidget(self.pin_btn)

        # ◧ Snap Left
        snap_left_btn = QPushButton("◧")
        snap_left_btn.setFixedSize(26, 26)
        snap_left_btn.setToolTip("Snap to Left Half of Screen")
        snap_left_btn.setStyleSheet(self._btn_style())
        snap_left_btn.clicked.connect(self.win.snap_left)
        layout.addWidget(snap_left_btn)

        # ◨ Snap Right
        snap_right_btn = QPushButton("◨")
        snap_right_btn.setFixedSize(26, 26)
        snap_right_btn.setToolTip("Snap to Right Half of Screen")
        snap_right_btn.setStyleSheet(self._btn_style())
        snap_right_btn.clicked.connect(self.win.snap_right)
        layout.addWidget(snap_right_btn)

        # ◻ Maximize / Restore
        self.max_btn = QPushButton("◻")
        self.max_btn.setFixedSize(26, 26)
        self.max_btn.setToolTip("Maximize / Restore")
        self.max_btn.setStyleSheet(self._btn_style())
        self.max_btn.clicked.connect(self.win.toggle_maximize)
        layout.addWidget(self.max_btn)

        # — Minimize
        min_btn = QPushButton("—")
        min_btn.setFixedSize(26, 26)
        min_btn.setToolTip("Minimize Window")
        min_btn.setStyleSheet(self._btn_style())
        min_btn.clicked.connect(self.win.showMinimized)
        layout.addWidget(min_btn)

        # ✕ Close
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setToolTip("Close J.A.R.V.I.S")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {_TEXT_MUTED};
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: #ef4444;
                color: #ffffff;
            }}
        """)
        close_btn.clicked.connect(self.win.close)
        layout.addWidget(close_btn)

    def _btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: {_BG_RAISED};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {_CYAN_DIM};
                color: {_CYAN};
                border-color: {_CYAN};
            }}
            QPushButton:checked {{
                background: {_CYAN};
                color: #000000;
            }}
        """

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            # If currently snapped / maximized, restore floating size when dragged away
            if self.win._is_snapped or self.win.isMaximized():
                self.win.restore_floating_from_drag(event.globalPosition().toPoint())
                self._drag_pos = QPoint(self.win.width() // 2, 20)

            new_top_left = event.globalPosition().toPoint() - self._drag_pos
            self.win.move(new_top_left)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            self.win.check_edge_snapping(event.globalPosition().toPoint())
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.win.toggle_maximize()


class JarvisStandaloneWindow(QMainWindow):
    """Detached Cyber-Holographic J.A.R.V.I.S Window with Aero Edge Snapping."""

    SNAP_THRESHOLD_PX = 25

    def __init__(self, workspace_root: str | Path = ".", parent: QWidget | None = None):
        super().__init__(None)  # Top-level standalone window
        self.workspace_root = Path(workspace_root).resolve()
        self._is_snapped = False
        self._is_pinned = False
        self._floating_geometry = QRect(200, 150, 560, 720)

        self.setWindowTitle("J.A.R.V.I.S — Autonomous Operating System Cockpit")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(f"background-color: {_BG_DEEP}; color: {_TEXT};")
        self.resize(560, 720)

        # Central Layout
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        # Custom Title Bar
        self.title_bar = JarvisTitleBar(self)
        layout.addWidget(self.title_bar)

        # Embedded HUD Panel
        self.hud_panel = JarvisHUDPanel(self.workspace_root, parent=self)
        layout.addWidget(self.hud_panel, 1)

    def show_and_activate(self) -> None:
        """Show window, bring to front, and activate."""
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_pin_on_top(self) -> None:
        """Toggle Always on Top mode."""
        self._is_pinned = not self._is_pinned
        flags = self.windowFlags()
        if self._is_pinned:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _get_current_screen_geometry(self, cursor_pos: QPoint | None = None) -> QRect:
        """Get available desktop geometry for the screen where cursor or window is located."""
        if cursor_pos is None:
            cursor_pos = self.mapToGlobal(QPoint(self.width() // 2, 20))
        screen = QGuiApplication.screenAt(cursor_pos)
        if not screen:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

    def snap_left(self) -> None:
        """Snap window to fill left half of current screen."""
        if not self._is_snapped:
            self._floating_geometry = self.geometry()
        screen_geo = self._get_current_screen_geometry()
        half_w = screen_geo.width() // 2
        self.setGeometry(screen_geo.left(), screen_geo.top(), half_w, screen_geo.height())
        self._is_snapped = True

    def snap_right(self) -> None:
        """Snap window to fill right half of current screen."""
        if not self._is_snapped:
            self._floating_geometry = self.geometry()
        screen_geo = self._get_current_screen_geometry()
        half_w = screen_geo.width() // 2
        self.setGeometry(screen_geo.left() + half_w, screen_geo.top(), half_w, screen_geo.height())
        self._is_snapped = True

    def toggle_maximize(self) -> None:
        """Maximize or restore window geometry."""
        screen_geo = self._get_current_screen_geometry()
        if self.geometry() == screen_geo:
            self.setGeometry(self._floating_geometry)
            self._is_snapped = False
        else:
            if not self._is_snapped:
                self._floating_geometry = self.geometry()
            self.setGeometry(screen_geo)
            self._is_snapped = True

    def restore_floating_from_drag(self, cursor_pos: QPoint) -> None:
        """Restore window to floating dimensions when user drags away from snapped edge."""
        self._is_snapped = False
        target_w = min(self._floating_geometry.width(), 560)
        target_h = min(self._floating_geometry.height(), 720)
        self.resize(target_w, target_h)
        self.move(cursor_pos.x() - target_w // 2, cursor_pos.y() - 15)

    def check_edge_snapping(self, cursor_pos: QPoint) -> None:
        """Windows Aero Snap & Magnetic Edge Detection."""
        screen_geo = self._get_current_screen_geometry(cursor_pos)
        win_geo = self.frameGeometry()

        # 1. Top Edge Drag -> Maximize
        if cursor_pos.y() <= screen_geo.top() + 10:
            if not self._is_snapped:
                self._floating_geometry = win_geo
            self.setGeometry(screen_geo)
            self._is_snapped = True
            return

        # 2. Left Edge Drag -> Snap Left Half
        if cursor_pos.x() <= screen_geo.left() + self.SNAP_THRESHOLD_PX:
            self.snap_left()
            return

        # 3. Right Edge Drag -> Snap Right Half
        if cursor_pos.x() >= screen_geo.right() - self.SNAP_THRESHOLD_PX:
            self.snap_right()
            return

        # 4. Magnetic Border Pull (within 25px of edges, snap flush to edge)
        new_x = win_geo.x()
        new_y = win_geo.y()
        snapped = False

        if abs(win_geo.left() - screen_geo.left()) <= self.SNAP_THRESHOLD_PX:
            new_x = screen_geo.left()
            snapped = True
        elif abs(win_geo.right() - screen_geo.right()) <= self.SNAP_THRESHOLD_PX:
            new_x = screen_geo.right() - win_geo.width()
            snapped = True

        if abs(win_geo.top() - screen_geo.top()) <= self.SNAP_THRESHOLD_PX:
            new_y = screen_geo.top()
            snapped = True
        elif abs(win_geo.bottom() - screen_geo.bottom()) <= self.SNAP_THRESHOLD_PX:
            new_y = screen_geo.bottom() - win_geo.height()
            snapped = True

        if snapped:
            self.move(new_x, new_y)
        else:
            self._floating_geometry = self.geometry()
            self._is_snapped = False
