"""AIActivityPanel — Real-Time Agent Execution Feed and Timeline.

Features:
- Live status banner with animated glowing state badge
- Filter chips (All, Tools, File Changes, Issues)
- Expandable event cards with elapsed timestamps and tool parameters
- Export activity timeline to Markdown
"""
from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Dark Theme Tokens
_BG_DEEP    = "#0c0d14"
_BG_BASE    = "#11121c"
_BG_PANEL   = "#161724"
_BG_RAISED  = "#1d1f30"
_BG_HOVER   = "#272a42"
_BORDER     = "#26293f"
_BORDER_LGT = "#363a59"
_TEXT       = "#f1f3f9"
_TEXT_DIM   = "#9ea4be"
_ACCENT     = "#6366f1"
_ACCENT_VIO = "#8b5cf6"
_ACCENT_CYAN= "#06b6d4"
_SUCCESS    = "#10b981"
_WARN       = "#f59e0b"
_DANGER     = "#f43f5e"


class AIActivityPanel(QWidget):
    """Next-generation real-time AI agent activity feed."""

    _STATE_STYLES: dict[str, tuple[str, str]] = {
        "IDLE":                    ("#636985", "○"),
        "ANALYZING":               (_WARN, "🔍"),
        "PLANNING":                (_ACCENT_VIO, "📋"),
        "WAITING_APPROVAL":        ("#fbbf24", "⏸"),
        "EXECUTING":               (_ACCENT_CYAN, "⚡"),
        "OBSERVING":               (_SUCCESS, "👁"),
        "VALIDATING":              ("#22d3ee", "✔"),
        "FIXING":                  (_DANGER, "🔧"),
        "REVIEWING":               (_ACCENT, "📝"),
        "VERIFYING":               ("#22d3ee", "🔍"),
        "COMPLETED":               (_SUCCESS, "✅"),
        "COMPLETED_WITH_WARNINGS": (_WARN, "⚠️"),
        "PARTIAL":                 ("#fb923c", "🌗"),
        "FAILED":                  (_DANGER, "✗"),
        "CANCELLED":               ("#94a3b8", "⏹"),
        "BLOCKED":                 ("#fb923c", "🚫"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step_count = 0
        self._task_start: float = 0.0
        self._last_tool_start: float = 0.0
        self._all_events_html: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header bar
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_RAISED};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 4px 8px;
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(8)

        self.status_label = QLabel("○ Agent: Idle")
        self.status_label.setFont(QFont("Inter", 12, QFont.Bold))
        self.status_label.setStyleSheet(f"color: {_TEXT_DIM};")
        h_layout.addWidget(self.status_label)

        h_layout.addStretch()

        self._elapsed_label = QLabel("")
        self._elapsed_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 11px;")
        h_layout.addWidget(self._elapsed_label)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(24)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BG_HOVER};
                color: {_TEXT_DIM};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 0 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: #ffffff;
                border-color: {_ACCENT};
            }}
        """)
        clear_btn.clicked.connect(self.clear)
        h_layout.addWidget(clear_btn)

        layout.addWidget(header)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background: {_BG_DEEP};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_ACCENT}, stop:1 {_ACCENT_CYAN});
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        # Timeline text
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("JetBrains Mono", 11))
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_BG_DEEP};
                color: #cbd5e1;
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 10px;
                line-height: 1.6;
            }}
        """)
        layout.addWidget(self.log_text, 1)

    def clear(self) -> None:
        self.log_text.clear()
        self._step_count = 0
        self._task_start = 0.0
        self._elapsed_label.setText("")
        self._all_events_html.clear()

    def set_agent_state(self, state: str) -> None:
        running = state in {
            "EXECUTING", "ANALYZING", "PLANNING", "OBSERVING",
            "FIXING", "VALIDATING", "REVIEWING",
        }
        self.progress_bar.setVisible(running)
        colour, icon = self._STATE_STYLES.get(state, ("#94a3b8", "●"))
        self.status_label.setText(f"{icon} Agent: {state}")
        self.status_label.setStyleSheet(f"font-weight: 700; color: {colour}; font-size: 12px;")

    def add_activity_event(self, event_type: str, data: dict[str, Any]) -> None:
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
            task = data.get("task", "")[:120]
            self._card("🔍", _WARN, "Analyzing Objective", task)

        elif event_type == "project_detected":
            fw = ", ".join(data.get("frameworks", [])) or "Standard"
            langs = ", ".join(data.get("languages", [])) or "Code"
            self._append(
                f"<div style='margin:4px 0; padding:6px 10px; background:{_BG_RAISED}; border-radius:6px;'>"
                f"<span style='color:{_ACCENT_CYAN}; font-weight:bold;'>🛠️ Ecosystem:</span> {langs} | "
                f"<span style='color:{_ACCENT_VIO}; font-weight:bold;'>Framework:</span> {fw}"
                f"</div>"
            )

        elif event_type == "plan_created":
            self._card("📋", _ACCENT_VIO, "Execution Plan Formulated", "")
            for i, step in enumerate(data.get("plan", []), 1):
                self._append(
                    f"<div style='padding-left:14px; margin:2px 0; color:#c4b5fd; font-size:11px;'>"
                    f"  <b style='color:{_ACCENT};'>{i}.</b> {step}</div>"
                )

        elif event_type == "tool_starting":
            self._step_count += 1
            self._last_tool_start = now
            tool = data.get("tool", "")
            args = data.get("args", {})
            arg_str = ", ".join(f"<b>{k}:</b> {str(v)[:40]}" for k, v in args.items())[:120]
            thought = data.get("thought", "")[:90]
            thought_html = f"<div style='color:#64748b; font-style:italic; font-size:11px; margin-top:2px;'>💭 {thought}</div>" if thought else ""

            self._append(
                f"<div style='margin:4px 0; padding:6px 10px; background:{_BG_RAISED}; border-left:3px solid {_ACCENT}; border-radius:0 6px 6px 0;'>"
                f"<span style='color:{_ACCENT_CYAN}; font-weight:bold;'>⚡ Step {self._step_count}:</span> "
                f"<code style='color:#ffffff; font-weight:bold;'>{tool}</code>({arg_str})"
                f"{thought_html}</div>"
            )

        elif event_type == "tool_finished":
            tool = data.get("tool", "")
            obs = data.get("observation", {})
            code = obs.get("exit_code", 0)
            dur = now - self._last_tool_start if self._last_tool_start else 0.0
            if code == 0:
                out_snip = (obs.get("stdout", "")[:120] or "").replace("\n", " ").strip()
                extra = f"<span style='color:#94a3be;'> → {out_snip}</span>" if out_snip else ""
                self._append(
                    f"<div style='margin:2px 0 6px 12px; font-size:11px; color:{_SUCCESS};'>"
                    f"✓ <code style='color:#ffffff;'>{tool}</code> completed ({dur:.2f}s) {extra}</div>"
                )
            else:
                err_snip = ((obs.get("stderr", "") or obs.get("stdout", ""))[:120]).replace("\n", " ").strip()
                self._append(
                    f"<div style='margin:2px 0 6px 12px; font-size:11px; color:{_DANGER};'>"
                    f"✗ <code style='color:#ffffff;'>{tool}</code> failed (exit {code}): {err_snip}</div>"
                )

        elif event_type == "self_correcting":
            cycle = data.get("cycle", "?")
            mx = data.get("max", "?")
            err = (data.get("error", "")[:140]).replace("\n", " ")
            self._card("🔧", _WARN, f"Self-Correction Cycle [{cycle}/{mx}]", err)

        elif event_type == "completed":
            files = data.get("files_changed", [])
            summary = data.get("summary", "")[:200]
            elapsed = (now - self._task_start) if self._task_start else 0
            files_html = ", ".join(f"<code>{f.split('/')[-1]}</code>" for f in files[:5]) if files else "None"
            self._append(
                f"<div style='margin:6px 0; padding:10px 12px; background:#0e2016; border-left:4px solid {_SUCCESS}; border-radius:0 8px 8px 0;'>"
                f"<span style='color:{_SUCCESS}; font-weight:bold; font-size:13px;'>✅ Task Successfully Completed</span>"
                f"<span style='color:#64748b; font-size:11px;'> · {elapsed:.1f}s · {self._step_count} steps</span>"
                f"<div style='color:{_TEXT}; font-size:12px; margin-top:4px;'>{summary}</div>"
                f"<div style='color:#86efac; font-size:11px; margin-top:4px;'>📁 Modified files: {files_html}</div>"
                f"</div>"
            )

    def _card(self, icon: str, colour: str, title: str, body: str) -> None:
        body_html = f"<div style='color:{_TEXT_DIM}; font-size:11px; margin-top:2px;'>{body}</div>" if body else ""
        self._append(
            f"<div style='margin:4px 0; padding:6px 10px; background:{_BG_RAISED}; border-left:3px solid {colour}; border-radius:0 6px 6px 0;'>"
            f"<span style='color:{colour}; font-weight:bold;'>{icon} {title}</span>"
            f"{body_html}</div>"
        )

    def _append(self, html: str) -> None:
        self.log_text.append(html)
        self._all_events_html.append(html)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())
