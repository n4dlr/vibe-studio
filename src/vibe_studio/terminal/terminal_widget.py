"""Multi-session terminal panel with command history, safe execution, and styled output."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.core.command_safety import CommandSafety, RiskLevel


# ---------------------------------------------------------------------------
# Background command runner — keeps UI responsive
# ---------------------------------------------------------------------------

class _CommandRunner(QThread):
    output_ready = Signal(str, str)   # (stdout, stderr)
    done = Signal(int, float)         # (exit_code, duration)

    def __init__(self, command: str, cwd: str, timeout: int = 120):
        super().__init__()
        self.command = command
        self.cwd = cwd
        self.timeout = timeout

    def run(self) -> None:
        result = CommandSafety.run(
            self.command,
            cwd=self.cwd,
            timeout=self.timeout,
        )
        self.output_ready.emit(result.stdout, result.stderr)
        self.done.emit(result.exit_code, result.duration)


# ---------------------------------------------------------------------------
# Individual terminal session
# ---------------------------------------------------------------------------

class TerminalSessionWidget(QWidget):
    """A single interactive terminal session tab."""

    def __init__(self, cwd: str | Path | None = None, parent=None):
        super().__init__(parent)
        self.cwd = str(Path(cwd or Path.cwd()).resolve())
        self._history: list[str] = []
        self._history_index = 0
        self._runner: _CommandRunner | None = None
        self._setup_ui()
        self._write_system(f"Working directory: {self.cwd}")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("monospace", 10))
        layout.addWidget(self.output)

        input_row = QHBoxLayout()
        self.prompt_label = QLabel("$")
        self.prompt_label.setStyleSheet("color: #4ade80; font-family: monospace; font-size: 12px;")
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter command…")
        self.input_field.setFont(QFont("monospace", 10))
        self.input_field.returnPressed.connect(self._execute)
        self.input_field.keyPressEvent = self._key_press

        self.run_btn = QPushButton("Run")
        self.run_btn.setFixedWidth(50)
        self.run_btn.setFixedHeight(28)
        self.run_btn.clicked.connect(self._execute)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedWidth(50)
        self.stop_btn.setFixedHeight(28)
        self.stop_btn.setStyleSheet("QPushButton{background:#dc2626;color:white;border:none;border-radius:4px;}")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)

        input_row.addWidget(self.prompt_label)
        input_row.addWidget(self.input_field, 1)
        input_row.addWidget(self.run_btn)
        input_row.addWidget(self.stop_btn)
        layout.addLayout(input_row)

    def _key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Up:
            if self._history_index > 0:
                self._history_index -= 1
                self.input_field.setText(self._history[self._history_index])
            return
        if event.key() == Qt.Key_Down:
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.input_field.setText(self._history[self._history_index])
            else:
                self._history_index = len(self._history)
                self.input_field.clear()
            return
        QLineEdit.keyPressEvent(self.input_field, event)

    def _execute(self) -> None:
        cmd = self.input_field.text().strip()
        if not cmd:
            return

        self._history.append(cmd)
        self._history_index = len(self._history)
        self.input_field.clear()

        # Built-in cd
        if cmd.startswith("cd "):
            target = cmd[3:].strip().strip('"').strip("'")
            new_dir = Path(self.cwd) / target
            try:
                new_dir = new_dir.resolve()
                if new_dir.is_dir():
                    self.cwd = str(new_dir)
                    self._write_system(f"Changed directory to {self.cwd}")
                else:
                    self._write_error(f"cd: {target}: No such directory")
            except Exception as e:
                self._write_error(str(e))
            return

        # Risk check — warn user but still allow
        assessment = CommandSafety.assess_risk(cmd)
        if assessment.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            self._write_system(
                f"⚠ Risk: {assessment.risk_level.value} — {'; '.join(assessment.reasons)}"
            )
            if assessment.risk_level == RiskLevel.CRITICAL:
                self._write_error("Command blocked by safety policy.")
                return

        self._write_prompt(cmd)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self._runner = _CommandRunner(cmd, self.cwd)
        self._runner.output_ready.connect(self._on_output)
        self._runner.done.connect(self._on_done)
        self._runner.start()

    @Slot(str, str)
    def _on_output(self, stdout: str, stderr: str) -> None:
        if stdout:
            self._write_output(stdout)
        if stderr:
            self._write_error(stderr)

    @Slot(int, float)
    def _on_done(self, exit_code: int, duration: float) -> None:
        colour = "#4ade80" if exit_code == 0 else "#f87171"
        self.output.append(
            f"<span style='color:{colour};font-size:10px;'>"
            f"[exit {exit_code} | {duration:.2f}s]</span>"
        )
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _stop(self) -> None:
        if self._runner and self._runner.isRunning():
            self._runner.terminate()
            self._runner.wait(500)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._write_system("Stopped.")

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def _write_prompt(self, cmd: str) -> None:
        self.output.append(
            f"<span style='color:#4ade80;'>$ </span>"
            f"<span style='color:#e6edf7;'>{_escape(cmd)}</span>"
        )

    def _write_output(self, text: str) -> None:
        self.output.append(f"<span style='color:#d0d7de;white-space:pre;'>{_escape(text)}</span>")

    def _write_error(self, text: str) -> None:
        self.output.append(f"<span style='color:#f87171;white-space:pre;'>{_escape(text)}</span>")

    def _write_system(self, text: str) -> None:
        self.output.append(f"<span style='color:#64748b;'>{_escape(text)}</span>")

    # Public write for main_window usage
    def write(self, text: str) -> None:
        if text.startswith("$"):
            self._write_prompt(text[1:].strip())
        else:
            self._write_output(text)


# ---------------------------------------------------------------------------
# Multi-tab terminal wrapper
# ---------------------------------------------------------------------------

class TerminalWidget(QTabWidget):
    """Multi-tab terminal panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_tab)
        self.setCornerWidget(self._make_new_tab_btn(), Qt.TopRightCorner)
        self.new_session()

    def _make_new_tab_btn(self) -> QPushButton:
        btn = QPushButton("+")
        btn.setFixedSize(24, 24)
        btn.setToolTip("New terminal session")
        btn.clicked.connect(lambda: self.new_session())
        return btn

    def new_session(self, cwd: str | Path | None = None) -> None:
        session = TerminalSessionWidget(cwd=cwd)
        n = self.count() + 1
        self.addTab(session, f"Terminal {n}")
        self.setCurrentIndex(self.count() - 1)

    def close_tab(self, index: int) -> None:
        if self.count() > 1:
            self.removeTab(index)

    def write(self, text: str) -> None:
        curr = self.currentWidget()
        if isinstance(curr, TerminalSessionWidget):
            curr.write(text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    """HTML-escape and preserve newlines."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("\n", "<br>")
    return text
