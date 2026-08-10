"""Real-time AI agent activity feed panel — rich timeline with step tracking."""
from __future__ import annotations

import time
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
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
    Displays structured real-time events from the autonomous agent as a
    rich timeline::

        ✓ Step 1  Analyzed project structure           (0.12s)
        ✓ Step 2  Found 4 relevant files (Graph RAG)   (0.35s)
        → Step 3  Editing src/controllers/auth.py
        → Step 4  Running pytest...
    """

    # State → (hex_colour, icon)
    _STATE_STYLES: dict[str, tuple[str, str]] = {
        "IDLE":             ("#4e6178", "○"),
        "ANALYZING":        ("#f59e0b", "🔍"),
        "PLANNING":         ("#a78bfa", "📋"),
        "WAITING_APPROVAL": ("#fbbf24", "⏸"),
        "EXECUTING":        ("#38bdf8", "⚡"),
        "OBSERVING":        ("#34d399", "👁"),
        "VALIDATING":       ("#22d3ee", "✔"),
        "FIXING":           ("#f87171", "🔧"),
        "REVIEWING":               ("#818cf8", "📝"),
        "VERIFYING":               ("#22d3ee", "🔍"),
        "COMPLETED":               ("#4ade80", "✅"),
        "COMPLETED_WITH_WARNINGS": ("#facc15", "⚠️"),
        "PARTIAL":                 ("#fb923c", "🌗"),
        "FAILED":                  ("#f87171", "✗"),
        "CANCELLED":               ("#94a3b8", "⏹"),
        "BLOCKED":                 ("#fb923c", "🚫"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step_count = 0
        self._task_start: float = 0.0
        self._last_tool_start: float = 0.0
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row
        header_row = QHBoxLayout()
        self.status_label = QLabel("○ Agent: Idle")
        self.status_label.setStyleSheet(
            "font-weight: 600; color: #4e6178; font-size: 12px;"
        )
        header_row.addWidget(self.status_label)
        header_row.addStretch()

        self._elapsed_label = QLabel("")
        self._elapsed_label.setStyleSheet("color: #64748b; font-size: 11px;")
        header_row.addWidget(self._elapsed_label)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(22)
        clear_btn.setFixedWidth(50)
        clear_btn.setStyleSheet(
            "QPushButton { background: #1e2030; color: #64748b; border: 1px solid #2e3050; "
            "border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { color: #f1f5f9; border-color: #818cf8; }"
        )
        clear_btn.clicked.connect(self.clear)
        header_row.addWidget(clear_btn)
        layout.addLayout(header_row)

        # Progress bar (indeterminate while running)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: none; background: #1e2030; border-radius: 2px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            " stop:0 #6366f1, stop:1 #38bdf8); border-radius: 2px; }"
        )
        layout.addWidget(self.progress_bar)

        # Timeline log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont("monospace", 11)
        self.log_text.setFont(font)
        self.log_text.setStyleSheet(
            "QTextEdit { background: #12131c; color: #cbd5e1; border: none; "
            "padding: 6px; line-height: 1.6; }"
        )
        layout.addWidget(self.log_text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self.log_text.clear()
        self._step_count = 0
        self._task_start = 0.0

    def set_agent_state(self, state: str) -> None:
        running = state in {
            "EXECUTING", "ANALYZING", "PLANNING", "OBSERVING",
            "FIXING", "VALIDATING", "REVIEWING",
        }
        self.progress_bar.setVisible(running)
        colour, icon = self._STATE_STYLES.get(state, ("#94a3b8", "●"))
        self.status_label.setText(f"{icon} Agent: {state}")
        self.status_label.setStyleSheet(
            f"font-weight: 600; color: {colour}; font-size: 12px;"
        )

    def add_activity_event(self, event_type: str, data: dict) -> None:  # noqa: C901
        now = time.monotonic()

        if event_type == "state_changed":
            state = data.get("state", "IDLE")
            self.set_agent_state(state)
            if state in ("ANALYZING", "EXECUTING") and self._task_start == 0.0:
                self._task_start = now
            if state in ("COMPLETED", "CANCELLED", "FAILED") and self._task_start:
                elapsed = now - self._task_start
                self._elapsed_label.setText(f"⏱ {elapsed:.1f}s total")
                self._task_start = 0.0

        elif event_type == "analyzing":
            self._step_count = 0
            self._task_start = now
            task = data.get("task", "")[:100]
            self._timeline("🔍", "#f59e0b", f"<b>Analyzing:</b> {task}")

        elif event_type == "project_detected":
            fw = ", ".join(data.get("frameworks", [])) or "—"
            langs = ", ".join(data.get("languages", [])) or "—"
            self._done_step(
                f"Project detected — "
                f"<b style='color:#38bdf8;'>{langs}</b>"
                f" | <span style='color:#a78bfa;'>{fw}</span>"
            )

        elif event_type == "plan_created":
            self._timeline("📋", "#a78bfa", "<b>Execution Plan:</b>")
            for i, step in enumerate(data.get("plan", []), 1):
                self._append(
                    f"<span style='color:#c4b5fd; padding-left:16px;'>  {i}. {step}</span>"
                )

        elif event_type == "tool_starting":
            self._step_count += 1
            self._last_tool_start = now
            tool = data.get("tool", "")
            args = data.get("args", {})
            arg_parts = []
            for k, v in args.items():
                vs = str(v)
                if k in ("path", "file", "filename") and "/" in vs:
                    vs = "…/" + vs.split("/")[-1]
                if k == "path":
                    arg_parts.append(f"<b>{vs[:50]}</b>")
                else:
                    arg_parts.append(f"{vs[:40]}")
            arg_str = ", ".join(arg_parts)[:120]
            thought = data.get("thought", "")[:80]
            thought_html = (
                f"<br><span style='color:#475569; font-style:italic;'>  💭 {thought}</span>"
                if thought else ""
            )
            self._running_step(
                f"<code style='color:#818cf8;'>{tool}</code>({arg_str}){thought_html}"
            )

        elif event_type == "tool_finished":
            tool = data.get("tool", "")
            obs = data.get("observation", {})
            code = obs.get("exit_code", 0)
            dur = now - self._last_tool_start
            if code == 0:
                out_snip = (obs.get("stdout", "")[:100] or "").replace("\n", " ").strip()
                extra = (
                    f" <span style='color:#64748b;'>→ {out_snip}</span>"
                    if out_snip else ""
                )
                self._done_step(
                    f"<code style='color:#818cf8;'>{tool}</code>"
                    f" <span style='color:#475569;'>({dur:.2f}s)</span>{extra}"
                )
            else:
                err_snip = (
                    (obs.get("stderr", "") or obs.get("stdout", ""))[:100]
                ).replace("\n", " ").strip()
                self._fail_step(
                    f"<code>{tool}</code> failed (exit {code})"
                    + (f": {err_snip}" if err_snip else "")
                )

        elif event_type == "auto_rollback":
            reason = data.get("reason", "")[:100]
            self._timeline(
                "↩", "#fb923c",
                f"<b>Auto-Rollback</b> — validation failed, reverted to clean state"
                f"<br><span style='color:#94a3b8; font-size:10px;'>  Reason: {reason}</span>"
            )

        elif event_type == "self_correcting":
            cycle = data.get("cycle", "?")
            mx = data.get("max", "?")
            err = (data.get("error", "")[:120]).replace("\n", " ")
            cat = data.get("category", "")
            self._timeline(
                "🔧", "#fb923c",
                f"<b>Self-correction [{cycle}/{mx}]</b>"
                f" <span style='color:#64748b; font-size:10px;'>[{cat}]</span>"
                f"<br><span style='color:#94a3b8; font-size:10px;'>  {err}</span>"
            )

        elif event_type == "loop_detected":
            tool = data.get("tool", "")
            self._timeline(
                "⚠", "#fbbf24",
                f"Loop detected for <code>{tool}</code> — choosing different approach"
            )

        elif event_type == "task_timeout":
            summary = data.get("summary", "")
            self._timeline("⏱", "#f87171", f"<b>Timeout:</b> {summary}")

        elif event_type == "reviewing":
            summary = data.get("summary", "")[:150]
            self._timeline("📝", "#818cf8", f"<b>Reviewing:</b> {summary}")

        elif event_type == "completed":
            files = data.get("files_changed", [])
            summary = data.get("summary", "")[:160]
            elapsed = (now - self._task_start) if self._task_start else 0
            files_html = (
                ", ".join(f"<code>{f.split('/')[-1]}</code>" for f in files[:4])
                + ("…" if len(files) > 4 else "")
            )
            self._append(
                f"<div style='margin:4px 0; padding:6px 10px; background:#0d1f12; "
                f"border-left:3px solid #4ade80; border-radius:0 6px 6px 0;'>"
                f"<span style='color:#4ade80; font-weight:600;'>✅ Completed</span>"
                f" <span style='color:#475569; font-size:10px;'>"
                f"· {elapsed:.1f}s · {self._step_count} steps</span>"
                + (f"<br><span style='color:#94a3b8; font-size:11px;'>📁 {files_html}</span>" if files_html else "")
                + (f"<br><span style='color:#a3e635; font-size:11px;'>{summary}</span>" if summary else "")
                + "</div>"
            )

        elif event_type == "provider_error":
            err = data.get("error", "")[:150]
            self._timeline("⚠", "#f87171", f"Provider error (offline mode): {err}")

        elif event_type == "stream_chunk":
            pass  # Goes to chat view, not activity

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _append(self, html: str) -> None:
        self.log_text.append(html)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _timeline(self, icon: str, colour: str, message: str) -> None:
        self._append(
            f"<div style='margin:2px 0; padding:3px 0;'>"
            f"<span style='color:{colour}; font-weight:600;'>{icon}</span> "
            f"<span style='color:#e2e8f0;'>{message}</span>"
            f"</div>"
        )

    def _done_step(self, message: str) -> None:
        step = self._step_count
        self._append(
            f"<div style='margin:1px 0;'>"
            f"<span style='color:#4ade80;'>✓</span> "
            f"<span style='color:#475569; font-size:10px;'>Step {step}</span>  "
            f"<span style='color:#cbd5e1;'>{message}</span>"
            f"</div>"
        )

    def _running_step(self, message: str) -> None:
        step = self._step_count
        self._append(
            f"<div style='margin:1px 0;'>"
            f"<span style='color:#38bdf8;'>→</span> "
            f"<span style='color:#475569; font-size:10px;'>Step {step}</span>  "
            f"<span style='color:#e2e8f0;'>{message}</span>"
            f"</div>"
        )

    def _fail_step(self, message: str) -> None:
        step = self._step_count
        self._append(
            f"<div style='margin:1px 0;'>"
            f"<span style='color:#f87171;'>✗</span> "
            f"<span style='color:#475569; font-size:10px;'>Step {step}</span>  "
            f"<span style='color:#f87171;'>{message}</span>"
            f"</div>"
        )
