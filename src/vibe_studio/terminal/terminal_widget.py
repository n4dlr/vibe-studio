from __future__ import annotations

import os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.core.command_safety import CommandSafety


class TerminalSessionWidget(QWidget):
    """Individual terminal session tab with command execution, shell history, and output display."""

    def __init__(self, cwd: str | Path | None = None, parent=None):
        super().__init__(parent)
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self.history: list[str] = []
        self.history_index = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFontFamily("monospace")
        self.output.setStyleSheet("QTextEdit { background: #0a1016; color: #dfeaf8; border: 1px solid #202a36; border-radius: 6px; padding: 6px; }")
        self.output.append(f"Vibe Studio Terminal ready. Working directory: {self.cwd}\n")

        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter shell command...")
        self.input_field.setStyleSheet("QLineEdit { background: #101821; color: #edf5ff; border: 1px solid #2b3341; border-radius: 6px; padding: 6px; font-family: monospace; }")
        self.input_field.returnPressed.connect(self._execute_command)
        self.input_field.keyPressEvent = self._handle_key_press

        self.run_btn = QPushButton("Run")
        self.run_btn.setStyleSheet("QPushButton { background: #3b82f6; color: white; border: none; border-radius: 6px; padding: 6px 12px; font-weight: bold; } QPushButton:hover { background: #2563eb; }")
        self.run_btn.clicked.connect(self._execute_command)

        input_row.addWidget(self.input_field)
        input_row.addWidget(self.run_btn)

        layout.addWidget(self.output)
        layout.addLayout(input_row)

    def _handle_key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key_Up:
            if self.history and self.history_index > 0:
                self.history_index -= 1
                self.input_field.setText(self.history[self.history_index])
            return
        elif event.key() == Qt.Key_Down:
            if self.history and self.history_index < len(self.history) - 1:
                self.history_index += 1
                self.input_field.setText(self.history[self.history_index])
            else:
                self.history_index = len(self.history)
                self.input_field.clear()
            return
        QLineEdit.keyPressEvent(self.input_field, event)

    def _execute_command(self):
        cmd = self.input_field.text().strip()
        if not cmd:
            return
        self.history.append(cmd)
        self.history_index = len(self.history)
        self.input_field.clear()

        self.output.append(f"$ {cmd}\n")
        try:
            res = CommandSafety.run(cmd, cwd=self.cwd, timeout=60)
            if res.stdout:
                self.output.append(res.stdout)
            if res.stderr:
                self.output.append(f"<span style='color: #f87171;'>{res.stderr}</span>")
        except Exception as exc:
            self.output.append(f"<span style='color: #ef4444;'>Error: {exc}</span>\n")


class TerminalWidget(QTabWidget):
    """Multi-tab interactive terminal panel supporting multiple sessions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_tab)
        self.new_session()

    def new_session(self, cwd: str | Path | None = None):
        session = TerminalSessionWidget(cwd=cwd, parent=self)
        count = self.count() + 1
        self.addTab(session, f"Terminal {count}")
        self.setCurrentIndex(self.count() - 1)

    def close_tab(self, index: int):
        if self.count() > 1:
            self.removeTab(index)

    def write(self, text: str) -> None:
        curr = self.currentWidget()
        if isinstance(curr, TerminalSessionWidget):
            curr.output.append(text)
