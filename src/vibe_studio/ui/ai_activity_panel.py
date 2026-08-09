"""Real-time AI agent activity feed panel."""
from __future__ import annotations

import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class AIActivityPanel(QWidget):
    """
    Displays structured real-time events from the autonomous agent:
      - State transitions
      - Plan steps
      - Tool calls (start / finish / error)
      - Streaming progress
      - Self-correction cycles
      - Project detection results
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row
        header_row = QHBoxLayout()
        self.status_label = QLabel("● Agent: Idle")
        self.status_label.setStyleSheet("font-weight: bold; color: #4e6178;")
        header_row.addWidget(self.status_label)
        header_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(22)
        clear_btn.setFixedWidth(50)
        clear_btn.clicked.connect(self.clear)
        header_row.addWidget(clear_btn)
        layout.addLayout(header_row)

        # Progress bar (indeterminate while running)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Activity log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(__import__("PySide6.QtGui", fromlist=["QFont"]).QFont("monospace", 10))
        layout.addWidget(self.log_text)

    # ------------------------------------------------------------------

    def clear(self) -> None:
        self.log_text.clear()

    def set_agent_state(self, state: str) -> None:
        running = state in {
            "EXECUTING", "ANALYZING", "PLANNING", "OBSERVING",
            "FIXING", "VALIDATING", "REVIEWING",
        }
        self.progress_bar.setVisible(running)

        colours = {
            "IDLE":             ("#4e6178", "●"),
            "ANALYZING":        ("#f59e0b", "🔍"),
            "PLANNING":         ("#a78bfa", "📋"),
            "WAITING_APPROVAL": ("#fbbf24", "⏸"),
            "EXECUTING":        ("#38bdf8", "⚡"),
            "OBSERVING":        ("#34d399", "👁"),
            "VALIDATING":       ("#22d3ee", "✔"),
            "FIXING":           ("#f87171", "🔧"),
            "REVIEWING":        ("#818cf8", "📝"),
            "COMPLETED":        ("#4ade80", "✅"),
            "FAILED":           ("#f87171", "✗"),
            "CANCELLED":        ("#94a3b8", "⏹"),
            "BLOCKED":          ("#fb923c", "🚫"),
        }
        colour, icon = colours.get(state, ("#94a3b8", "●"))
        self.status_label.setText(f"{icon} Agent: {state}")
        self.status_label.setStyleSheet(f"font-weight: bold; color: {colour};")

    def _append(self, html: str) -> None:
        self.log_text.append(html)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def add_activity_event(self, event_type: str, data: dict) -> None:  # noqa: C901
        if event_type == "state_changed":
            state = data.get("state", "IDLE")
            self.set_agent_state(state)
            self._append(f"<span style='color:#38bdf8;'>[{state}]</span>")

        elif event_type == "analyzing":
            task = data.get("task", "")[:120]
            self._append(f"<span style='color:#f59e0b;'>🔍 Analyzing: {task}</span>")

        elif event_type == "project_detected":
            fw = ", ".join(data.get("frameworks", [])) or "—"
            langs = ", ".join(data.get("languages", [])) or "—"
            self._append(
                f"<span style='color:#4ade80;'>✓ Project detected — "
                f"frameworks: <b>{fw}</b> | languages: <b>{langs}</b></span>"
            )

        elif event_type == "plan_created":
            self._append("<span style='color:#a78bfa;'>📋 Execution Plan:</span>")
            for i, step in enumerate(data.get("plan", []), 1):
                self._append(f"<span style='color:#c4b5fd;'>  {i}. {step}</span>")

        elif event_type == "tool_starting":
            tool = data.get("tool", "")
            args = data.get("args", {})
            # Show key args concisely
            arg_str = ", ".join(
                f"{k}={str(v)[:60]}" for k, v in args.items()
            )[:120]
            thought = data.get("thought", "")[:100]
            thought_html = f" <i style='color:#64748b;'>{thought}</i>" if thought else ""
            # Sütun 6: Explainable AI — show REASON: if provided
            reason = data.get("reason", "")[:150]
            reason_html = (
                f"<br><span style='color:#fbbf24; font-size:10px;'>💡 <i>Reason: {reason}</i></span>"
                if reason else ""
            )
            self._append(
                f"<span style='color:#818cf8;'>⚡ <b>{tool}</b>({arg_str}){thought_html}{reason_html}</span>"
            )

        elif event_type == "tool_finished":
            tool = data.get("tool", "")
            obs = data.get("observation", {})
            code = obs.get("exit_code", 0)
            dur = data.get("duration", 0.0)
            if code == 0:
                out_snip = (obs.get("stdout", "")[:120] or "").replace("\n", " ")
                self._append(
                    f"<span style='color:#4ade80;'>  ✓ {tool} done ({dur:.2f}s)"
                    f"{f' → {out_snip}' if out_snip else ''}</span>"
                )
            else:
                err_snip = (obs.get("stderr", "")[:120] or obs.get("stdout", "")[:120]).replace("\n", " ")
                self._append(
                    f"<span style='color:#f87171;'>  ✗ {tool} failed (exit {code})"
                    f"{f': {err_snip}' if err_snip else ''}</span>"
                )

        elif event_type == "self_correcting":
            cycle = data.get("cycle", "?")
            mx = data.get("max", "?")
            err = (data.get("error", "")[:150]).replace("\n", " ")
            self._append(
                f"<span style='color:#fb923c;'>🔧 Self-correction [{cycle}/{mx}]: {err}</span>"
            )

        elif event_type == "loop_detected":
            tool = data.get("tool", "")
            self._append(
                f"<span style='color:#fbbf24;'>⚠ Loop detected for '{tool}' — choosing different approach</span>"
            )

        elif event_type == "reviewing":
            summary = data.get("summary", "")[:200]
            self._append(f"<span style='color:#818cf8;'>📝 Reviewing: {summary}</span>")

        elif event_type == "completed":
            files = data.get("files_changed", [])
            summary = data.get("summary", "")[:200]
            files_str = ", ".join(files[:5]) + ("…" if len(files) > 5 else "")
            self._append(
                f"<span style='color:#4ade80;'>✅ <b>Completed</b>"
                f"{f' — changed: {files_str}' if files_str else ''}</span>"
            )
            if summary:
                self._append(f"<span style='color:#a3e635;'>  {summary}</span>")

        elif event_type == "provider_error":
            err = data.get("error", "")[:200]
            self._append(
                f"<span style='color:#f87171;'>⚠ Provider error (using offline mode): {err}</span>"
            )

        elif event_type == "stream_chunk":
            # Don't show raw stream in activity — it goes to the chat view
            pass
