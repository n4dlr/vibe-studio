from __future__ import annotations

import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class AIActivityPanel(QWidget):
    """Real-time streaming agent activity panel showing step events, tool calls, and plan status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header_row = QHBoxLayout()
        self.status_label = QLabel("Agent: Idle")
        self.status_label.setStyleSheet("font-weight: bold; color: #38bdf8;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setVisible(False)

        header_row.addWidget(self.status_label)
        header_row.addStretch()
        layout.addLayout(header_row)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFontFamily("monospace")
        self.log_text.setStyleSheet("QTextEdit { background: #0a1016; color: #e6edf7; border: 1px solid #202a36; border-radius: 6px; padding: 6px; }")
        layout.addWidget(self.log_text)

    def set_agent_state(self, state: str):
        self.status_label.setText(f"Agent: {state}")
        if state in {"EXECUTING", "ANALYZING", "PLANNING", "OBSERVING", "FIXING"}:
            self.progress_bar.setVisible(True)
        else:
            self.progress_bar.setVisible(False)

    def add_activity_event(self, event_type: str, data: dict):
        if event_type == "state_changed":
            state = data.get("state", "IDLE")
            self.set_agent_state(state)
            self.log_text.append(f"<span style='color: #38bdf8;'>[STATE] {state}</span>")

        elif event_type == "plan_created":
            steps = data.get("plan", [])
            self.log_text.append("<span style='color: #f59e0b;'>[PLAN] Generated Plan:</span>")
            for idx, s in enumerate(steps, 1):
                self.log_text.append(f"<span style='color: #fbbf24;'>  {idx}. {s}</span>")

        elif event_type == "tool_starting":
            tool = data.get("tool", "")
            args = data.get("args", {})
            self.log_text.append(f"<span style='color: #a78bfa;'>[TOOL START] {tool}({json.dumps(args)})</span>")

        elif event_type == "tool_finished":
            tool = data.get("tool", "")
            obs = data.get("observation", {})
            code = obs.get("exit_code", 0)
            color = "#4ade80" if code == 0 else "#f87171"
            self.log_text.append(f"<span style='color: {color};'>[TOOL FINISHED] {tool} → Exit Code {code}</span>")

        elif event_type == "self_correcting":
            err = data.get("error", "")
            self.log_text.append(f"<span style='color: #ef4444;'>[SELF-CORRECTION] Analyzing error and patching code...</span>")

        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
