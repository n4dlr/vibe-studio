"""SuperAgentPanel — Next-Gen AI Mission Control Deck for Vibe Studio.

Features:
- Glassmorphic Metric HUD (Steps, Browser Ops, Files Changed, Live Quality Grade)
- Dynamic Milestone Plan Tree (Live state progression: PENDING → IN_PROGRESS → COMPLETED)
- Real-Time Self-Critique Radar & Quality Gauge (Dynamic gradient bar, strengths & improvement pills)
- Live Browser & Artifact Viewport (High-res Playwright screenshot preview with URL badge)
- Real-Time Token & Tool Execution Stream
- Quick-Launch Goal Preset Chips & Push-Limits Autonomy Controls
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.agents.super_agent import SuperAgent, SuperAgentResult

logger = logging.getLogger(__name__)

# Dark Theme Palette
_BG_DEEP    = "#0c0d14"
_BG_BASE    = "#11121c"
_BG_PANEL   = "#161724"
_BG_RAISED  = "#1d1f30"
_BG_HOVER   = "#272a42"
_BORDER     = "#26293f"
_BORDER_LGT = "#363a59"
_TEXT       = "#f1f3f9"
_TEXT_DIM   = "#9ea4be"
_TEXT_MUTED = "#636985"
_ACCENT     = "#6366f1"
_ACCENT_HOV = "#4f46e5"
_ACCENT_VIO = "#8b5cf6"
_ACCENT_CYAN= "#06b6d4"
_SUCCESS    = "#10b981"
_WARN       = "#f59e0b"
_DANGER     = "#f43f5e"


class MetricCard(QFrame):
    """Sleek glassmorphic HUD metric tile with glowing icon and counter."""

    def __init__(self, title: str, icon: str, default_value: str = "0", accent_color: str = _ACCENT, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_RAISED};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 6px 10px;
            }}
            QFrame:hover {{
                border-color: {accent_color};
                background-color: {_BG_HOVER};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        top_row = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 14))
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        top_row.addWidget(icon_lbl)
        top_row.addWidget(title_lbl)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.value_lbl = QLabel(default_value)
        self.value_lbl.setFont(QFont("Inter", 16, QFont.Bold))
        self.value_lbl.setStyleSheet(f"color: {accent_color};")
        layout.addWidget(self.value_lbl)

    def set_value(self, val: str) -> None:
        self.value_lbl.setText(val)


class SuperAgentWorker(QObject):
    """Background worker for non-blocking SuperAgent execution."""

    progress = Signal(str, dict)
    stream_token = Signal(str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, agent: SuperAgent, goal: str):
        super().__init__()
        self.agent = agent
        self.goal = goal

    @Slot()
    def run(self) -> None:
        try:
            self.agent.progress_callback = lambda etype, data: self.progress.emit(etype, data)
            self.agent.stream_callback = lambda tok: self.stream_token.emit(tok)
            result = self.agent.run(self.goal)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class SuperAgentPanel(QWidget):
    """Interactive next-gen command deck for SuperAgent."""

    def __init__(self, workspace_root: str | Path, provider: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.workspace_root = Path(workspace_root).resolve()
        self.provider = provider
        self._thread: QThread | None = None
        self._worker: SuperAgentWorker | None = None
        self._current_agent: SuperAgent | None = None
        self._start_time: float = 0.0
        self._step_counter: int = 0
        self._browser_counter: int = 0
        self._files_counter: set[str] = set()

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_timer)

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── 1. HUD Metric Deck ─────────────────────────────────────────
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(8)

        self._card_steps = MetricCard("Steps Taken", "⚡", "0", _ACCENT)
        self._card_browser = MetricCard("Browser Ops", "🌐", "0", _ACCENT_CYAN)
        self._card_files = MetricCard("Files Changed", "📝", "0", _SUCCESS)
        self._card_score = MetricCard("Quality Score", "🎯", "-- / 100", _ACCENT_VIO)
        self._card_time = MetricCard("Elapsed Time", "⏱️", "00:00", _WARN)

        metrics_layout.addWidget(self._card_steps)
        metrics_layout.addWidget(self._card_browser)
        metrics_layout.addWidget(self._card_files)
        metrics_layout.addWidget(self._card_score)
        metrics_layout.addWidget(self._card_time)
        main_layout.addLayout(metrics_layout)

        # ── 2. Preset Goal Chips Bar ──────────────────────────────────
        presets_box = QWidget()
        presets_layout = QHBoxLayout(presets_box)
        presets_layout.setContentsMargins(0, 0, 0, 0)
        presets_layout.setSpacing(6)

        chip_label = QLabel("⚡ Quick Presets:")
        chip_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 11px; font-weight: bold;")
        presets_layout.addWidget(chip_label)

        presets = [
            ("🌐 Scrape & Synthesize Docs", "Scrape latest documentation on web, analyze it, and write a thorough technical guide in docs/"),
            ("🐞 Bug Hunt & Auto-Fix", "Scan workspace for runtime bugs and test failures, fix all root causes, and verify with pytest"),
            ("⚡ Full-Stack Feature", "Design and implement a complete modular feature with models, controllers, and comprehensive unit tests"),
            ("📑 Write Technical RFC", "Draft an in-depth architectural RFC detailing tech stack choices, data structures, and trade-offs"),
        ]

        for title, prompt_text in presets:
            btn = QPushButton(title)
            btn.setFixedHeight(26)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_BG_RAISED};
                    color: {_TEXT_DIM};
                    border: 1px solid {_BORDER};
                    border-radius: 13px;
                    padding: 2px 10px;
                    font-size: 11px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: {_BG_HOVER};
                    color: #ffffff;
                    border-color: {_ACCENT};
                }}
            """)
            btn.clicked.connect(lambda _, p=prompt_text: self._set_preset(p))
            presets_layout.addWidget(btn)

        presets_layout.addStretch()
        main_layout.addWidget(presets_box)

        # ── 3. Central Cockpit Splitter ────────────────────────────────
        cockpit_splitter = QSplitter(Qt.Vertical)
        cockpit_splitter.setHandleWidth(3)

        # Top section: Plan Tree & Quality Radar Dashboard
        top_deck = QWidget()
        top_layout = QHBoxLayout(top_deck)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        # Hierarchical Plan Box
        plan_box = QGroupBox("📋 Hierarchical Execution Plan")
        plan_vbox = QVBoxLayout(plan_box)
        plan_vbox.setContentsMargins(6, 6, 6, 6)

        self._plan_tree = QTreeWidget()
        self._plan_tree.setHeaderLabels(["Milestone & Tasks", "Status", "Score"])
        self._plan_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._plan_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._plan_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._plan_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {_BG_BASE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                font-size: 12px;
            }}
            QTreeWidget::item {{
                padding: 4px 6px;
            }}
        """)
        plan_vbox.addWidget(self._plan_tree)
        top_layout.addWidget(plan_box, 3)

        # Self-Critique Quality Radar Box
        radar_box = QGroupBox("🎯 Self-Critique Radar & Quality Breakdown")
        radar_vbox = QVBoxLayout(radar_box)
        radar_vbox.setContentsMargins(10, 10, 10, 10)
        radar_vbox.setSpacing(6)

        self._score_gauge_label = QLabel("Awaiting Evaluation...")
        self._score_gauge_label.setFont(QFont("Inter", 13, QFont.Bold))
        self._score_gauge_label.setStyleSheet(f"color: {_ACCENT_VIO};")
        radar_vbox.addWidget(self._score_gauge_label)

        self._score_bar = QProgressBar()
        self._score_bar.setRange(0, 100)
        self._score_bar.setValue(0)
        self._score_bar.setFixedHeight(8)
        radar_vbox.addWidget(self._score_bar)

        self._critique_details = QTextEdit()
        self._critique_details.setReadOnly(True)
        self._critique_details.setPlaceholderText("Self-critique breakdown, strengths, and auto-refinement improvements appear here...")
        self._critique_details.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_BG_BASE};
                color: {_TEXT_DIM};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                font-size: 11px;
                padding: 6px;
            }}
        """)
        radar_vbox.addWidget(self._critique_details)
        top_layout.addWidget(radar_box, 2)

        cockpit_splitter.addWidget(top_deck)

        # Bottom section: Real-Time Stream & Live Viewport Tabs
        bottom_tabs = QTabWidget()
        bottom_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {_BORDER};
                background: {_BG_BASE};
                border-radius: 6px;
            }}
        """)

        # Tab 1: Streaming Execution Console
        stream_tab = QWidget()
        stream_layout = QVBoxLayout(stream_tab)
        stream_layout.setContentsMargins(6, 6, 6, 6)

        self._output_stream = QTextEdit()
        self._output_stream.setReadOnly(True)
        self._output_stream.setPlaceholderText("SuperAgent thoughts, real-time token streaming, and tool execution logs...")
        self._output_stream.setFont(QFont("JetBrains Mono", 11))
        self._output_stream.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_BG_DEEP};
                color: #e2e8f0;
                border: none;
                padding: 8px;
                line-height: 1.5;
            }}
        """)
        stream_layout.addWidget(self._output_stream)
        bottom_tabs.addTab(stream_tab, "⚡ Live Stream & Timeline")

        # Tab 2: Live Browser Viewport
        browser_tab = QWidget()
        browser_layout = QVBoxLayout(browser_tab)
        browser_layout.setContentsMargins(8, 8, 8, 8)

        self._viewport_label = QLabel("No active browser screenshot")
        self._viewport_label.setAlignment(Qt.AlignCenter)
        self._viewport_label.setStyleSheet(f"""
            QLabel {{
                background-color: {_BG_DEEP};
                color: {_TEXT_MUTED};
                border: 1px dashed {_BORDER};
                border-radius: 8px;
                font-size: 12px;
            }}
        """)
        browser_layout.addWidget(self._viewport_label)
        bottom_tabs.addTab(browser_tab, "🌐 Live Browser Viewport")

        cockpit_splitter.addWidget(bottom_tabs)
        cockpit_splitter.setSizes([200, 260])
        main_layout.addWidget(cockpit_splitter, 1)

        # ── 4. Autonomous Control & Launch Bar ─────────────────────────
        control_deck = QFrame()
        control_deck.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_RAISED};
                border: 1px solid {_BORDER};
                border-radius: 10px;
                padding: 6px;
            }}
        """)
        control_layout = QVBoxLayout(control_deck)
        control_layout.setContentsMargins(8, 8, 8, 8)
        control_layout.setSpacing(6)

        # Controls Option Row
        options_row = QHBoxLayout()
        options_row.setSpacing(12)

        self._push_limits_cb = QCheckBox("⚡ Push Limits (Score ≥ 85%)")
        self._push_limits_cb.setChecked(True)
        self._push_limits_cb.setStyleSheet(f"color: {_TEXT}; font-weight: 600; font-size: 11px;")
        options_row.addWidget(self._push_limits_cb)

        self._model_selector = QComboBox()
        self._model_selector.addItems(["llama3.1", "qwen2.5-coder:7b", "qwen2.5:3b", "qwen2.5:1.5b", "deepseek-coder-v2:lite"])
        options_row.addWidget(QLabel("Model:"))
        options_row.addWidget(self._model_selector)

        options_row.addStretch()

        self._clear_btn = QPushButton("🗑️ Clear Log")
        self._clear_btn.setFixedHeight(28)
        self._clear_btn.clicked.connect(self._clear_deck)
        options_row.addWidget(self._clear_btn)

        control_layout.addLayout(options_row)

        # Goal Input Row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._goal_input = QTextEdit()
        self._goal_input.setPlaceholderText("Describe complex goal: Coding, Web research, Playwright automation, Writing (Ctrl+Enter to launch)...")
        self._goal_input.setFixedHeight(54)
        self._goal_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_BG_BASE};
                color: #ffffff;
                border: 1px solid {_BORDER_LGT};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QTextEdit:focus {{
                border-color: {_ACCENT};
            }}
        """)
        self._goal_input.keyPressEvent = self._handle_input_key
        input_row.addWidget(self._goal_input, 1)

        self._launch_btn = QPushButton("🚀  Launch SuperAgent")
        self._launch_btn.setFixedHeight(54)
        self._launch_btn.setMinimumWidth(180)
        self._launch_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_ACCENT}, stop:1 {_ACCENT_VIO});
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_ACCENT_HOV}, stop:1 {_ACCENT});
            }}
            QPushButton:disabled {{
                background: {_BG_HOVER};
                color: {_TEXT_MUTED};
            }}
        """)
        self._launch_btn.clicked.connect(self._launch_agent)
        input_row.addWidget(self._launch_btn)

        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setFixedHeight(54)
        self._stop_btn.setFixedWidth(80)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_DANGER};
                color: white;
                font-weight: bold;
                border-radius: 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #e11d48;
            }}
            QPushButton:disabled {{
                background-color: {_BG_BASE};
                color: {_TEXT_MUTED};
            }}
        """)
        self._stop_btn.clicked.connect(self._stop_agent)
        input_row.addWidget(self._stop_btn)

        control_layout.addLayout(input_row)
        main_layout.addWidget(control_deck)

    # ------------------------------------------------------------------
    # Actions & Lifecycle
    # ------------------------------------------------------------------

    def _set_preset(self, prompt: str) -> None:
        self._goal_input.setText(prompt)
        self._goal_input.setFocus()

    def _handle_input_key(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() == Qt.ControlModifier:
            self._launch_agent()
        else:
            QTextEdit.keyPressEvent(self._goal_input, event)

    def _clear_deck(self) -> None:
        self._output_stream.clear()
        self._plan_tree.clear()
        self._critique_details.clear()
        self._score_bar.setValue(0)
        self._card_steps.set_value("0")
        self._card_browser.set_value("0")
        self._card_files.set_value("0")
        self._card_score.set_value("-- / 100")
        self._card_time.set_value("00:00")
        self._score_gauge_label.setText("Awaiting Evaluation...")

    def _launch_agent(self) -> None:
        goal = self._goal_input.toPlainText().strip()
        if not goal:
            return

        self._launch_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._clear_deck()
        self._output_stream.append(f"🚀 [MISSION STARTED]: {goal}\n" + "─" * 60)

        self._step_counter = 0
        self._browser_counter = 0
        self._files_counter.clear()
        self._start_time = time.monotonic()
        self._timer.start()

        threshold = 85 if self._push_limits_cb.isChecked() else 70
        model = self._model_selector.currentText()

        self._current_agent = SuperAgent(
            workspace_root=self.workspace_root,
            provider=self.provider,
            model=model,
            push_hard_threshold=threshold,
        )

        self._thread = QThread(self)
        self._worker = SuperAgentWorker(self._current_agent, goal)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_agent_progress)
        self._worker.stream_token.connect(self._on_stream_token)
        self._worker.finished.connect(self._on_agent_finished)
        self._worker.error.connect(self._on_agent_error)
        self._thread.start()

    def _stop_agent(self) -> None:
        if self._current_agent:
            self._current_agent.cancellation_token.cancel()
        self._stop_btn.setEnabled(False)
        self._timer.stop()
        self._output_stream.append("\n🛑 [STOP REQUESTED BY OPERATOR]")

    def _update_timer(self) -> None:
        elapsed = int(time.monotonic() - self._start_time)
        mins, secs = divmod(elapsed, 60)
        self._card_time.set_value(f"{mins:02d}:{secs:02d}")

    @Slot(str, dict)
    def _on_agent_progress(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "plan_created":
            self._populate_plan_tree(data.get("plan", {}))
        elif event_type == "tool_executing":
            self._step_counter += 1
            self._card_steps.set_value(str(self._step_counter))
            tool = data.get("tool", "")
            thought = data.get("thought", "")
            if "browser_" in tool:
                self._browser_counter += 1
                self._card_browser.set_value(str(self._browser_counter))
            if thought:
                self._output_stream.append(f"\n🧠 [Thought]: {thought}")
            self._output_stream.append(f"🔧 [Execute]: {tool}({str(data.get('args', {}))[:80]})")
        elif event_type == "tool_finished":
            tool = data.get("tool", "")
            if tool == "browser_screenshot":
                self._update_screenshot()
            if tool in ("write_file", "patch_file", "create_file"):
                self._files_counter.add(str(data.get("path", "file")))
                self._card_files.set_value(str(len(self._files_counter)))
        elif event_type == "self_critique_finished":
            score = int(data.get("score", 0))
            self._card_score.set_value(f"{score} / 100")
            self._score_bar.setValue(score)
            grade = "A+ 🌟" if score >= 90 else "A ✅" if score >= 85 else "B ⚠️" if score >= 70 else "C ❌"
            self._score_gauge_label.setText(f"Quality Score: {score}/100 • Grade: {grade}")

            details = f"=== SELF-CRITIQUE REPORT ===\nScore: {score} / 100\n"
            if data.get("weaknesses"):
                details += "\n⚠️ Weaknesses Detected:\n" + "\n".join(f"  • {w}" for w in data["weaknesses"])
            if data.get("improvements"):
                details += "\n\n🎯 Required Improvements:\n" + "\n".join(f"  • {i}" for i in data["improvements"])
            self._critique_details.setText(details)
        elif event_type == "limit_push_triggered":
            attempt = data.get("attempt", 1)
            self._output_stream.append(f"\n⚡ [LIMIT PUSH REFINEMENT #{attempt}]: Quality score insufficient, automatically improving...")

    @Slot(str)
    def _on_stream_token(self, token: str) -> None:
        self._output_stream.insertPlainText(token)
        sb = self._output_stream.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot(object)
    def _on_agent_finished(self, result: SuperAgentResult) -> None:
        self._timer.stop()
        self._launch_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._card_score.set_value(f"{result.critique.score} / 100")
        self._card_files.set_value(str(len(result.files_changed)))
        self._output_stream.append(f"\n" + "═" * 60 + f"\n🏁 [MISSION FINISHED]: {result.status.value}\n" + "═" * 60)

        if self._thread:
            self._thread.quit()
            self._thread.wait()

    @Slot(str)
    def _on_agent_error(self, err: str) -> None:
        self._timer.stop()
        self._launch_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._output_stream.append(f"\n❌ [CRITICAL ERROR]: {err}")
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    def _populate_plan_tree(self, plan_dict: dict[str, Any]) -> None:
        self._plan_tree.clear()
        milestones = plan_dict.get("milestones", [])
        for m in milestones:
            item = QTreeWidgetItem([f"Milestone {m.get('id')}: {m.get('title')}", m.get('status', 'PENDING'), "--"])
            for st in m.get("sub_tasks", []):
                sub_item = QTreeWidgetItem([f"  • {st}", "Ready", ""])
                item.addChild(sub_item)
            item.setExpanded(True)
            self._plan_tree.addTopLevelItem(item)

    def _update_screenshot(self) -> None:
        ss_path = self.workspace_root / "screenshot.png"
        if not ss_path.exists():
            ss_path = self.workspace_root / ".vibe_studio" / "screenshots" / "screenshot.png"
        if ss_path.exists():
            pix = QPixmap(str(ss_path))
            if not pix.isNull():
                scaled = pix.scaled(self._viewport_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._viewport_label.setPixmap(scaled)
