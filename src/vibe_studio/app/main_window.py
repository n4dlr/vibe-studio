"""Main application window — VS Code-like layout for the Vibe Studio AI IDE."""
from __future__ import annotations
from PySide6.QtGui import QTextCursor


import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QDir, QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QFont, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFileSystemModel,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.agents.coding_agent import AgentState, AutonomyMode
from vibe_studio.ai.chat_service import ChatService
from vibe_studio.ai.model_manager import ModelManager
from vibe_studio.core.settings import AppSettings, ProviderConfig, SettingsStore
from vibe_studio.editor.diff_viewer import DiffViewerDialog
from vibe_studio.editor.editor_widget import EditorWidget
from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine
from vibe_studio.filesystem.file_watcher import WorkspaceFileWatcher
from vibe_studio.filesystem.project_manager import ProjectManager
from vibe_studio.terminal.terminal_widget import TerminalWidget
from vibe_studio.ui.ai_activity_panel import AIActivityPanel
from vibe_studio.ui.command_palette import CommandPaletteDialog
from vibe_studio.ui.git_panel import GitPanel
from vibe_studio.ui.problems_panel import ProblemsPanel
from vibe_studio.ui.search_panel import SearchPanel
from vibe_studio.ui.test_runner_panel import TestRunnerPanel
from vibe_studio.ui.theme import apply_theme


# ---------------------------------------------------------------------------
# Agent worker — runs in a background QThread
# ---------------------------------------------------------------------------

class AgentWorker(QObject):
    finished = Signal(str)
    error = Signal(str)
    activity = Signal(str, dict)
    stream_chunk = Signal(str)   # incremental text from streaming

    def __init__(self, chat_service: ChatService, prompt: str, mode: AutonomyMode):
        super().__init__()
        self.chat_service = chat_service
        self.prompt = prompt
        self.mode = mode
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self.chat_service.cancel_current_agent()

    @Slot()
    def process(self) -> None:
        try:
            def _activity(event_type: str, data: dict):
                self.activity.emit(event_type, data)
                if event_type == "stream_chunk":
                    self.stream_chunk.emit(data.get("chunk", ""))

            # Use set_activity_callback so this replaces any stale callback from
            # a previous run — prevents old deleted workers from firing signals.
            self.chat_service.set_activity_callback(_activity)
            response = self.chat_service.chat(self.prompt, autonomy_mode=self.mode)
            self.finished.emit(response)
        except Exception as exc:
            self.error.emit(str(exc))



# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """VS Code-like Desktop AI IDE main window."""

    def __init__(self, settings_store: SettingsStore, settings: AppSettings):
        super().__init__()
        self.settings_store = settings_store
        self.settings = settings
        self.project_manager = ProjectManager()
        self.model_manager = ModelManager(settings)
        self.chat_service = ChatService(self.model_manager)
        self._agent_thread: QThread | None = None
        self._agent_worker: AgentWorker | None = None
        self._streaming_response = False
        self._file_watcher = WorkspaceFileWatcher(parent=self)
        self._code_intelligence: CodeIntelligenceEngine | None = None
        self._file_watcher.directory_changed.connect(self._on_workspace_changed)
        self._file_watcher.file_changed.connect(self._on_file_changed_on_disk)

        self.setWindowTitle("Vibe Studio — AI Desktop IDE")
        self.resize(1600, 980)
        apply_theme(self, dark=settings.dark_theme)

        self._setup_menu()
        self._setup_central_layout()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._refresh_model_selector()
        self._open_default_project()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _setup_menu(self) -> None:
        mb = self.menuBar()

        # File
        fm = mb.addMenu("&File")
        fm.addAction("Open Project…", self.open_project, QKeySequence("Ctrl+Shift+O"))
        fm.addAction("Open File…", self.open_file, QKeySequence("Ctrl+O"))
        fm.addAction("Save Current File", self._save_current_editor, QKeySequence("Ctrl+S"))
        fm.addAction("New File", self._new_file, QKeySequence("Ctrl+N"))
        fm.addSeparator()
        fm.addAction("Exit", self.close, QKeySequence("Ctrl+Q"))

        # Edit
        em = mb.addMenu("&Edit")
        em.addAction("Command Palette…", self.show_command_palette, QKeySequence("Ctrl+Shift+P"))
        em.addAction("Find in Project", self._focus_search, QKeySequence("Ctrl+Shift+F"))
        em.addSeparator()
        em.addAction("Undo AI Change", self._undo_last_change, QKeySequence("Ctrl+Z"))

        # View
        vm = mb.addMenu("&View")
        vm.addAction("Toggle Explorer", self._toggle_left_panel, QKeySequence("Ctrl+B"))
        vm.addAction("Toggle Terminal Panel", self._toggle_bottom_panel, QKeySequence("Ctrl+`"))
        vm.addAction("Toggle AI Panel", self._toggle_right_panel, QKeySequence("Ctrl+Shift+A"))
        vm.addAction("Refresh Git Status", self.refresh_git_status)

        # AI
        aim = mb.addMenu("&AI")
        aim.addAction("Run Multi-Agent Task Orchestrator", lambda: self._run_ai_prompt(
            "Execute full multi-agent task orchestrator on this project."))
        aim.addAction("Analyze Project", lambda: self._run_ai_prompt(
            "Analyze this project and summarize the architecture, tech stack, and important files."))
        aim.addAction("Find Bugs", lambda: self._run_ai_prompt(
            "Scan the entire codebase for bugs, logic errors, and potential crashes. List every issue found."))
        aim.addAction("Run Tests && Fix", lambda: self._run_ai_prompt(
            "Run the project tests and automatically fix any failing tests."))
        aim.addAction("Run Build && Fix", lambda: self._run_ai_prompt(
            "Run the project build and automatically fix any build errors."))
        aim.addAction("Fix All Problems", lambda: self._run_ai_prompt(
            "Inspect all project problems, errors, and warnings. Fix every one you can."))
        aim.addAction("Code Review", lambda: self._run_ai_prompt(
            "Inspect the Git diff and perform a comprehensive code review."))
        aim.addAction("Generate Tests", lambda: self._run_ai_prompt(
            "Generate comprehensive unit tests for the main project modules."))
        aim.addAction("Stop Agent", self._stop_agent, QKeySequence("Escape"))

        # Tools
        tm = mb.addMenu("&Tools")
        tm.addAction("Proactive Security & Performance Scan", self._run_proactive_scan)
        tm.addAction("Discover Untested Functions", self._discover_untested_functions)
        tm.addAction("Manage Plugins", self._manage_plugins)
        tm.addAction("Export Memory Sync Bundle", self._export_sync_bundle)

        # Run
        rm = mb.addMenu("&Run")
        rm.addAction("Run Tests", self.run_project_tests, QKeySequence("Ctrl+Shift+T"))
        rm.addAction("Run Linter", self._run_linter)
        rm.addAction("Run Formatter", self._run_formatter)

        # Git
        gm = mb.addMenu("&Git")
        gm.addAction("Refresh Status", self.refresh_git_status)
        gm.addAction("Show Diff", lambda: self._run_ai_prompt("Show me the current git diff and summarize the changes."))
        gm.addAction("Commit (AI message)", lambda: self._run_ai_prompt(
            "Review the staged git changes and commit them with an appropriate commit message."))

        # Settings
        mb.addAction("⚙ Settings", self.show_settings)


    # ------------------------------------------------------------------
    # Central Layout
    # ------------------------------------------------------------------

    def _setup_central_layout(self) -> None:
        root_widget = QWidget(self)
        self.setCentralWidget(root_widget)
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Vertical splitter: [main area] / [bottom panels] ──────────
        self._v_splitter = QSplitter(Qt.Vertical)
        self._v_splitter.setHandleWidth(4)

        # ── Horizontal splitter: [left sidebar] / [editor] / [right AI]
        self._h_splitter = QSplitter(Qt.Horizontal)
        self._h_splitter.setHandleWidth(4)

        self._build_left_sidebar()
        self._build_editor_area()
        self._build_right_panel()

        self._h_splitter.setSizes([240, 860, 460])
        self._v_splitter.addWidget(self._h_splitter)

        self._build_bottom_panel()
        self._v_splitter.setSizes([740, 240])

        root_layout.addWidget(self._v_splitter)

    # ── Left sidebar ───────────────────────────────────────────────────
    def _build_left_sidebar(self) -> None:
        self._left_tabs = QTabWidget()

        # Explorer
        self.explorer = QTreeView()
        self.explorer.setHeaderHidden(True)
        self.explorer.setAnimated(True)
        self.explorer.setIndentation(16)
        self.file_model = QFileSystemModel()
        self.file_model.setReadOnly(True)
        self.file_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.explorer.setModel(self.file_model)
        # Hide size/type/date columns — only show name
        for col in range(1, 4):
            self.explorer.hideColumn(col)
        self.explorer.clicked.connect(self._open_selected_file_from_tree)
        self.explorer.doubleClicked.connect(self._open_selected_file_from_tree)
        self.explorer.setContextMenuPolicy(Qt.CustomContextMenu)
        self.explorer.customContextMenuRequested.connect(self._explorer_context_menu)

        # Search panel
        self.search_panel = SearchPanel(self.settings.project_path or str(Path.cwd()))

        # Git panel
        self.git_panel = GitPanel()

        self._left_tabs.addTab(self.explorer, "📁 Explorer")
        self._left_tabs.addTab(self.search_panel, "🔍 Search")
        self._left_tabs.addTab(self.git_panel, "⎇ Git")
        self._h_splitter.addWidget(self._left_tabs)

    # ── Editor center ──────────────────────────────────────────────────
    def _build_editor_area(self) -> None:
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.setDocumentMode(True)
        self.editor_tabs.setMovable(True)
        self.editor_tabs.tabCloseRequested.connect(self.close_editor_tab)
        cl.addWidget(self.editor_tabs)
        self._h_splitter.addWidget(center)

    # ── Right AI panel ─────────────────────────────────────────────────
    def _build_right_panel(self) -> None:
        self._right_widget = QWidget()
        rl = QVBoxLayout(self._right_widget)
        rl.setContentsMargins(8, 8, 8, 8)
        rl.setSpacing(6)

        # Model / mode header
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(160)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Auto Mode", "Plan Mode", "Ask Mode"])
        model_row.addWidget(QLabel("Model:"))
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.mode_combo)
        rl.addLayout(model_row)

        # Refresh model button
        ref_btn = QPushButton("↻ Refresh Models")
        ref_btn.setFixedHeight(26)
        ref_btn.clicked.connect(self._refresh_model_selector)
        rl.addWidget(ref_btn)

        # AI tabs — Chat / Activity
        self._ai_tabs = QTabWidget()

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("AI responses appear here…")
        self.chat.setFont(QFont("monospace", 11))

        self.activity_panel = AIActivityPanel()
        self.changes_panel = _ChangesPanel()
        self._ai_tabs.addTab(self.chat, "💬 Chat")
        self._ai_tabs.addTab(self.activity_panel, "⚡ Activity")
        self._ai_tabs.addTab(self.changes_panel, "📝 Changes")
        rl.addWidget(self._ai_tabs, 1)

        # Prompt input
        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText(
            "Ask Vibe Studio…\n  e.g. 'Login page-in backgroundunu dəyiş'\n  Ctrl+Enter to send"
        )
        self.chat_input.setFixedHeight(100)
        self.chat_input.setFont(QFont("monospace", 11))
        self.chat_input.keyPressEvent = self._chat_key_press
        rl.addWidget(self.chat_input)

        # Action buttons
        btn_row = QHBoxLayout()
        self.send_btn = QPushButton("▶  Send Task")
        self.send_btn.setStyleSheet(
            "QPushButton{background:#3b82f6;color:white;border:none;border-radius:6px;"
            "padding:8px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#2563eb;}"
            "QPushButton:disabled{background:#1e2d40;color:#4e6178;}"
        )
        self.send_btn.clicked.connect(self._send_chat_message)

        self.stop_btn = QPushButton("⏹  Stop")
        self.stop_btn.setStyleSheet(
            "QPushButton{background:#ef4444;color:white;border:none;border-radius:6px;"
            "padding:8px 12px;font-weight:bold;}"
            "QPushButton:hover{background:#dc2626;}"
        )
        self.stop_btn.clicked.connect(self._stop_agent)

        self.undo_btn = QPushButton("↩  Undo")
        self.undo_btn.clicked.connect(self._undo_last_change)

        self.clear_chat_btn = QPushButton("🗑️")
        self.clear_chat_btn.setToolTip("Clear Chat History")
        self.clear_chat_btn.setFixedSize(28, 26)
        self.clear_chat_btn.clicked.connect(self._clear_chat_history)

        self.export_chat_btn = QPushButton("📥")
        self.export_chat_btn.setToolTip("Export Chat History to Markdown")
        self.export_chat_btn.setFixedSize(28, 26)
        self.export_chat_btn.clicked.connect(self._export_chat_history)

        btn_row.addWidget(self.send_btn, 2)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.undo_btn)
        btn_row.addWidget(self.clear_chat_btn)
        btn_row.addWidget(self.export_chat_btn)
        rl.addLayout(btn_row)
        self._h_splitter.addWidget(self._right_widget)

    # ── Bottom panel ───────────────────────────────────────────────────
    def _build_bottom_panel(self) -> None:
        self._bottom_tabs = QTabWidget()

        self.terminal = TerminalWidget()
        self.problems_panel = ProblemsPanel()
        self.test_runner_panel = TestRunnerPanel()

        self._bottom_tabs.addTab(self.terminal, "⬛ Terminal")
        self._bottom_tabs.addTab(self.problems_panel, "⚠ Problems")
        self._bottom_tabs.addTab(self.test_runner_panel, "✓ Tests")
        self._v_splitter.addWidget(self._bottom_tabs)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_statusbar(self) -> None:
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_model_label = QLabel("  No model")
        self._status_state_label = QLabel("Idle")
        self._status.addPermanentWidget(self._status_model_label)
        self._status.addWidget(self._status_state_label)
        self._status.showMessage("Vibe Studio ready.")

    def _set_status(self, text: str) -> None:
        self._status.showMessage(text)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+Shift+P", self.show_command_palette),
            ("Ctrl+P",       self._quick_open_file),
            ("Ctrl+S",       self._save_current_editor),
            ("Ctrl+W",       self._close_current_tab),
            ("Ctrl+N",       self._new_file),
            ("Ctrl+B",       self._toggle_left_panel),
            ("Ctrl+`",       self._focus_terminal),
            ("Ctrl+Shift+F", self._focus_search),
            ("Ctrl+Shift+A", self._toggle_right_panel),
        ]
        for key, slot in shortcuts:
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(slot)

    # ------------------------------------------------------------------
    # Shortcut actions
    # ------------------------------------------------------------------

    def _quick_open_file(self) -> None:
        """Quick-open dialog listing project files."""
        if not self.settings.project_path:
            self.open_file()
            return
        root = Path(self.settings.project_path)
        files: list[str] = []
        skip = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            parts = p.relative_to(root).parts
            if any(s in skip for s in parts):
                continue
            files.append(p.relative_to(root).as_posix())
        actions = [{"category": "File", "title": f} for f in sorted(files)[:500]]
        dlg = CommandPaletteDialog(actions, parent=self)
        if dlg.exec_() == CommandPaletteDialog.Accepted and dlg.selected_action:
            title = dlg.selected_action.get("title", "")
            self.open_editor(root / title)

    def _close_current_tab(self) -> None:
        idx = self.editor_tabs.currentIndex()
        if idx >= 0:
            self.close_editor_tab(idx)

    def _toggle_left_panel(self) -> None:
        if self._left_tabs.isVisible():
            self._left_tabs.hide()
        else:
            self._left_tabs.show()

    def _toggle_right_panel(self) -> None:
        if self._right_widget.isVisible():
            self._right_widget.hide()
        else:
            self._right_widget.show()

    def _toggle_bottom_panel(self) -> None:
        if self._bottom_tabs.isVisible():
            self._bottom_tabs.hide()
        else:
            self._bottom_tabs.show()

    def _focus_terminal(self) -> None:
        self._bottom_tabs.setCurrentWidget(self.terminal)
        self._bottom_tabs.show()

    def _focus_search(self) -> None:
        self._left_tabs.setCurrentWidget(self.search_panel)
        self.search_panel.search_input.setFocus()

    def _new_file(self) -> None:
        editor = EditorWidget("untitled")
        self.editor_tabs.addTab(editor, "untitled")
        self.editor_tabs.setCurrentIndex(self.editor_tabs.count() - 1)

    # ------------------------------------------------------------------
    # Chat / Agent
    # ------------------------------------------------------------------

    def _chat_key_press(self, event: QKeyEvent) -> None:
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Return:
            self._send_chat_message()
            return
        QTextEdit.keyPressEvent(self.chat_input, event)

    def _send_chat_message(self) -> None:
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        # Include selected editor text or active file as context
        curr_editor = self.editor_tabs.currentWidget()
        if isinstance(curr_editor, EditorWidget) and getattr(curr_editor, "path", None):
            file_name = Path(curr_editor.path).name
            sel = curr_editor.textCursor().selectedText()
            if sel.strip():
                text = f"{text}\n\n[Selected code in {file_name}]:\n```\n{sel}\n```"
            else:
                text = f"{text}\n\n[Active file: {file_name}]"
        self._run_ai_prompt(text)

    def _run_ai_prompt(self, prompt: str) -> None:
        # Guard: check if previous thread is still alive (with safety for already-deleted C++ objects)
        try:
            if self._agent_thread and self._agent_thread.isRunning():
                self.chat.append("<b style='color:#f59e0b;'>⚠ Agent already running. Press Stop first.</b>\n")
                return
        except RuntimeError:
            # C++ QThread object already deleted — safe to proceed
            self._agent_thread = None
            self._agent_worker = None

        self.chat.append(f"<b style='color:#60a5fa;'>You:</b> {prompt[:200]}{'…' if len(prompt) > 200 else ''}\n")
        self.chat_input.clear()

        mode_str = self.mode_combo.currentText()
        mode = AutonomyMode.PLAN if "Plan" in mode_str else AutonomyMode.ASK if "Ask" in mode_str else AutonomyMode.AUTO

        # Update selected model in settings
        model_text = self.model_combo.currentText()
        if model_text and "unavailable" not in model_text.lower():
            self.settings.default_model = model_text

        self.send_btn.setEnabled(False)
        self.send_btn.setText("⟳  Running…")
        self._status_state_label.setText("Agent: Running")
        self._ai_tabs.setCurrentWidget(self.activity_panel)
        self._streaming_response = False

        worker = AgentWorker(self.chat_service, prompt, mode)
        thread = QThread(self)
        worker.moveToThread(thread)

        def _clear_refs() -> None:
            """Clear Python references after the C++ QThread is deleted."""
            self._agent_thread = None
            self._agent_worker = None

        thread.started.connect(worker.process)
        worker.activity.connect(self._on_agent_activity)
        worker.stream_chunk.connect(self._on_stream_chunk)
        worker.finished.connect(self._handle_agent_response)
        worker.error.connect(self._handle_agent_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(_clear_refs)   # ← clears refs AFTER deleteLater

        thread.start()
        self._agent_thread = thread
        self._agent_worker = worker


    @Slot(str, dict)
    def _on_agent_activity(self, event_type: str, data: dict) -> None:
        self.activity_panel.add_activity_event(event_type, data)

        # ── Rich status bar feedback ──────────────────────────────────────────
        if event_type == "state_changed":
            state = data.get("state", "")
            _icons = {
                "ANALYZING":        "🔍 Analyzing…",
                "PLANNING":         "📋 Planning steps…",
                "EXECUTING":        "⚡ Executing…",
                "OBSERVING":        "👁 Observing result…",
                "REVIEWING":        "📝 Reviewing output…",
                "FIXING":           "🔧 Self-correcting…",
                "VALIDATING":       "✅ Validating…",
                "COMPLETED":        "✅ Completed",
                "FAILED":           "❌ Failed",
                "CANCELLED":        "⛔ Cancelled",
                "WAITING_APPROVAL": "⏸ Waiting for your approval…",
            }
            label = _icons.get(state, f"Agent: {state}")
            self._status_state_label.setText(label)
            self._set_status(label)

        elif event_type == "analyzing":
            task_snip = data.get("task", "")[:60]
            self._set_status(f"🔍 Analyzing: {task_snip}")

        elif event_type == "project_detected":
            fw = ", ".join(data.get("frameworks", [])) or "—"
            langs = ", ".join(data.get("languages", [])) or "—"
            self._set_status(f"✓ Project detected — frameworks: {fw} | languages: {langs}")

        elif event_type == "plan_created":
            steps = data.get("plan", [])
            if steps:
                self._set_status(f"📋 Plan ready — {len(steps)} step(s): {steps[0][:50]}…")
            # Ask for permission if in Ask Mode or Plan Mode
            if hasattr(self, "mode_combo") and self.mode_combo.currentText() in ("Ask Mode", "Plan Mode"):
                from PySide6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self,
                    "Agent Plan Approval Required",
                    f"Agent proposed execution plan ({len(steps)} steps):\n\n"
                    + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps[:5]))
                    + "\n\nProceed with these changes?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.No:
                    self._stop_agent()

        elif event_type == "tool_starting":
            tool = data.get("tool", "")
            args = data.get("args", {})
            hint = args.get("path") or args.get("command") or args.get("query") or args.get("pattern") or ""
            hint = str(hint)[:50]
            label = f"⚡ {tool}({hint})" if hint else f"⚡ {tool}(…)"
            self._set_status(label)

        elif event_type == "tool_finished":
            tool = data.get("tool", "")
            obs  = data.get("observation") or {}
            code = obs.get("exit_code", 0)
            dur  = data.get("duration", 0)
            icon = "✓" if code == 0 else "✗"
            self._set_status(f"{icon} {tool} done ({dur:.2f}s)")
            if obs.get("files_changed"):
                self._reload_open_editors(obs["files_changed"])

        elif event_type == "stuck_detected":
            tool = data.get("tool", "")
            self._set_status(f"⚠ Stuck detected on '{tool}' — switching approach…")

        elif event_type == "loop_detected":
            self._set_status(f"🔁 Loop detected — retrying differently…")

        elif event_type == "self_correcting":
            cyc = data.get("cycle", "?")
            mx  = data.get("max", "?")
            cat = data.get("category", "error")
            self._set_status(f"🔧 Self-repair {cyc}/{mx}: fixing {cat}…")

        elif event_type == "completed":
            files = data.get("files_changed", [])
            label = f"✅ Done — {len(files)} file(s) changed" if files else "✅ Done"
            self._set_status(label)
            if files:
                self._reload_open_editors(files)

        elif event_type == "provider_error":
            self._set_status(f"⚠ Provider error — using offline fallback")
        # ─────────────────────────────────────────────────────────────────────


    @Slot(str)
    def _on_stream_chunk(self, chunk: str) -> None:
        """Append streaming text incrementally to chat."""
        if not self._streaming_response:
            self.chat.append("<b style='color:#4ade80;'>AI:</b> ")
            self._streaming_response = True
        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.chat.setTextCursor(cursor)
        self.chat.ensureCursorVisible()

    def _reload_open_editors(self, files: list[str] | set[str] | str) -> None:
        """Reload any open editor tab matching changed files on disk."""
        if isinstance(files, str):
            files = [files]
        for f in files:
            if not f:
                continue
            target_name = Path(f).name
            target_path = Path(f).resolve() if Path(f).is_absolute() else None
            for idx in range(self.editor_tabs.count()):
                w = self.editor_tabs.widget(idx)
                if isinstance(w, EditorWidget) and getattr(w, "path", None):
                    w_path = Path(w.path).resolve()
                    if w_path.name == target_name or (target_path and w_path == target_path):
                        w.is_dirty = False
                        w.reload_from_disk()

    def _handle_agent_response(self, response: str) -> None:
        # Build detailed diff & file stats summary if files were changed
        diff_stats = ""
        if hasattr(self, "chat_service") and self.chat_service._agent:
            agent = self.chat_service._agent
            history = agent.tool_registry.patch_tools.history
            if history:
                diff_stats = "\n\n<b>📝 Dəyişikliklər Xülasəsi:</b><ul>"
                modified_paths = []
                for snap in history:
                    file_name = Path(snap.path).name
                    modified_paths.append(snap.path)
                    lines_added = len([l for l in snap.diff.splitlines() if l.startswith("+") and not l.startswith("+++")])
                    lines_removed = len([l for l in snap.diff.splitlines() if l.startswith("-") and not l.startswith("---")])
                    file_size = Path(snap.path).stat().st_size if Path(snap.path).exists() else 0
                    diff_stats += f"<li>📄 <b>{file_name}</b>: +{lines_added} / -{lines_removed} sətir ({file_size} bayt)</li>"
                diff_stats += "</ul>"
                self._reload_open_editors(modified_paths)

        full_response = response + diff_stats

        if not self._streaming_response:
            self.chat.append(f"<b style='color:#4ade80;'>AI:</b> {full_response}\n")
        else:
            if diff_stats:
                self.chat.append(diff_stats)
            self.chat.append("\n")
            self._streaming_response = False
        self.send_btn.setEnabled(True)
        self.send_btn.setText("▶  Send Task")
        self._status_state_label.setText("Agent: Idle")
        self._set_status("Agent task completed.")
        # Refresh file tree, git panel, and changes tab after agent work
        self.refresh_git_status()
        self._refresh_changes_panel()

    def _handle_agent_error(self, error: str) -> None:
        self.chat.append(f"<b style='color:#f87171;'>Error:</b> {error}\n")
        self.send_btn.setEnabled(True)
        self.send_btn.setText("▶  Send Task")
        self._status_state_label.setText("Agent: Error")
        self._set_status(f"Agent error: {error[:80]}")
        self._streaming_response = False

    def _stop_agent(self) -> None:
        if self._agent_worker:
            self._agent_worker.cancel()
        if self.chat_service:
            self.chat_service.cancel_current_agent()
        if self._agent_thread and self._agent_thread.isRunning():
            self._agent_thread.quit()
            self._agent_thread.wait(200)

        self.chat.append("<b style='color:#f59e0b;'>System:</b> Execution cancelled.\n")
        self._set_status("Agent cancelled.")
        self.send_btn.setEnabled(True)
        self.send_btn.setText("▶  Send Task")
        self._status_state_label.setText("Agent: Idle")
        self._streaming_response = False

    def _refresh_changes_panel(self) -> None:
        """Populate the Changes panel with diffs from the most recent agent task."""
        if not hasattr(self, "chat_service") or not self.chat_service._agent:
            return
        history = self.chat_service._agent.tool_registry.patch_tools.history
        self.changes_panel.set_snapshots(history)

    def _undo_last_change(self) -> None:
        if self.chat_service.revert_last_change():
            self.chat.append("<b style='color:#4ade80;'>AI:</b> Last AI change reverted.\n")
            self._set_status("Reverted last AI file change.")
        else:
            self.chat.append("<b style='color:#94a3b8;'>AI:</b> Nothing to undo.\n")

    def trigger_ai_action(self, action_kind: str, file_path: str, selection: str) -> None:
        prompts = {
            "explain": f"Explain this code in {file_path}:\n```\n{selection}\n```",
            "fix": f"Fix issues in this code in {file_path}:\n```\n{selection}\n```",
            "refactor": f"Refactor and improve this code in {file_path}:\n```\n{selection}\n```",
            "tests": f"Generate unit tests for this code in {file_path}:\n```\n{selection}\n```",
            "docs": f"Add documentation comments to this code in {file_path}:\n```\n{selection}\n```",
            "run_tests_and_fix": "Run the project tests and automatically fix any failing tests.",
            "run_build_and_fix": "Run the project build and automatically fix any build errors.",
            "code_review": "Inspect the Git diff and perform a comprehensive AI code review.",
            "fix_problems": "Inspect current problems and fix all errors in the project.",
        }
        self._run_ai_prompt(prompts.get(action_kind, f"Perform {action_kind} on {file_path}"))

    # ------------------------------------------------------------------
    # Command palette
    # ------------------------------------------------------------------

    def show_command_palette(self) -> None:
        actions = [
            {"category": "AI", "title": "Analyze Project"},
            {"category": "AI", "title": "Find Bugs"},
            {"category": "AI", "title": "Run Tests & Fix"},
            {"category": "AI", "title": "Run Build & Fix"},
            {"category": "AI", "title": "Fix All Problems"},
            {"category": "AI", "title": "Code Review"},
            {"category": "AI", "title": "Generate Tests"},
            {"category": "AI", "title": "Stop Agent"},
            {"category": "File", "title": "Open Project"},
            {"category": "File", "title": "Open File"},
            {"category": "File", "title": "New File"},
            {"category": "File", "title": "Save File"},
            {"category": "Edit", "title": "Undo AI Change"},
            {"category": "View", "title": "Toggle Explorer"},
            {"category": "View", "title": "Toggle Terminal"},
            {"category": "View", "title": "Toggle AI Panel"},
            {"category": "Run", "title": "Run Tests"},
            {"category": "Run", "title": "Run Linter"},
            {"category": "Git", "title": "Git Status"},
            {"category": "Git", "title": "Git Diff"},
            {"category": "IDE", "title": "Settings"},
        ]
        dlg = CommandPaletteDialog(actions, parent=self)
        if dlg.exec_() != CommandPaletteDialog.Accepted or not dlg.selected_action:
            return
        title = dlg.selected_action.get("title", "")
        dispatch = {
            "Analyze Project": lambda: self._run_ai_prompt("Analyze this project and summarize the architecture."),
            "Find Bugs": lambda: self._run_ai_prompt("Find all bugs in this project."),
            "Run Tests & Fix": lambda: self.trigger_ai_action("run_tests_and_fix", "", ""),
            "Run Build & Fix": lambda: self.trigger_ai_action("run_build_and_fix", "", ""),
            "Fix All Problems": lambda: self.trigger_ai_action("fix_problems", "", ""),
            "Code Review": lambda: self.trigger_ai_action("code_review", "", ""),
            "Generate Tests": lambda: self._run_ai_prompt("Generate tests for this project."),
            "Stop Agent": self._stop_agent,
            "Open Project": self.open_project,
            "Open File": self.open_file,
            "New File": self._new_file,
            "Save File": self._save_current_editor,
            "Undo AI Change": self._undo_last_change,
            "Toggle Explorer": self._toggle_left_panel,
            "Toggle Terminal": self._toggle_bottom_panel,
            "Toggle AI Panel": self._toggle_right_panel,
            "Run Tests": self.run_project_tests,
            "Run Linter": self._run_linter,
            "Git Status": self.refresh_git_status,
            "Git Diff": lambda: self._run_ai_prompt("Show me the current git diff."),
            "Settings": self.show_settings,
            "Proactive Scan": self._run_proactive_scan,
            "Untested Functions": self._discover_untested_functions,
            "Plugins": self._manage_plugins,
            "Export Sync": self._export_sync_bundle,
        }
        if title in dispatch:
            dispatch[title]()

    def _run_proactive_scan(self) -> None:
        folder = self.settings.project_path or str(Path.cwd())
        from vibe_studio.agents.proactive_analyzer import ProactiveAnalyzer
        analyzer = ProactiveAnalyzer(folder)
        res = analyzer.run_analysis()
        QMessageBox.information(
            self, "Proactive Analysis",
            f"Security Issues: {len(res.get('security_findings', []))}\n"
            f"Performance Bottlenecks: {len(res.get('performance_findings', []))}\n"
            f"Unpinned Dependencies: {len(res.get('dependency_findings', []))}"
        )

    def _discover_untested_functions(self) -> None:
        folder = self.settings.project_path or str(Path.cwd())
        from vibe_studio.agents.self_learning_tests import SelfLearningTests
        slt = SelfLearningTests()
        untested = slt.find_untested_functions(Path(folder))
        QMessageBox.information(
            self, "Untested Functions",
            f"Found {len(untested)} functions without dedicated unit tests.\n"
            f"Top example: {untested[0].function_name if untested else 'None'}"
        )

    def _manage_plugins(self) -> None:
        folder = self.settings.project_path or str(Path.cwd())
        from vibe_studio.plugin.plugin_manager import PluginManager
        pm = PluginManager()
        plugins = pm.discover_plugins()
        QMessageBox.information(
            self, "Plugins Manager",
            f"Plugins Directory: ~/.vibe_studio/plugins/\n"
            f"Discovered Plugins: {', '.join(plugins) if plugins else 'None'}"
        )

    def _export_sync_bundle(self) -> None:
        folder = self.settings.project_path or str(Path.cwd())
        from vibe_studio.cloud.sync_manager import SyncManager
        sm = SyncManager(folder)
        bundle = sm.export_sync_bundle()
        QMessageBox.information(
            self, "Memory Sync Bundle",
            f"Exported Workspace Memory Bundle ({len(bundle)} bytes)."
        )

    # ------------------------------------------------------------------
    # Model selector
    # ------------------------------------------------------------------

    def _refresh_model_selector(self) -> None:
        self.model_combo.clear()
        models = self.model_manager.list_models()
        items = [m.get("model", "") for m in models if m.get("model")]
        if not items:
            items = ["(Ollama unavailable)"]
        self.model_combo.addItems(items)
        if items:
            self._status_model_label.setText(f"  {items[0]}")

    # ------------------------------------------------------------------
    # Project / file management
    # ------------------------------------------------------------------

    def _open_default_project(self) -> None:
        default = self.settings.project_path or str(Path.cwd())
        if Path(default).exists():
            self.open_project(Path(default))

    def open_project(self, folder: "str | Path | None" = None) -> None:
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Open Project Folder")
            if not folder:
                return
        folder = str(Path(folder).resolve())
        self.settings.project_path = folder
        self.settings_store.save(self.settings)
        self.project_manager.open_project(Path(folder))
        self.file_model.setRootPath(folder)
        self.explorer.setRootIndex(self.file_model.index(folder))
        self.search_panel.set_workspace_root(folder)
        self.terminal.new_session(cwd=folder)
        self.setWindowTitle(f"Vibe Studio \u2014 {Path(folder).name}")
        self._set_status(f"Opened project: {folder}")
        self.refresh_git_status()
        # Activate real-time file watching and code intelligence
        self._file_watcher.set_workspace_root(folder)
        self._code_intelligence = CodeIntelligenceEngine(folder)
        self._code_intelligence.on_diagnostics(self._on_lsp_diagnostics_received)
        # Update LSP status on status bar
        status_msg = self._code_intelligence.get_status("python")
        self._set_status(f"Opened project: {folder} | {status_msg}")
        # Load persistent chat history for project
        self._load_saved_chat_history()

    def _load_saved_chat_history(self) -> None:
        """Load and display saved chat history for the project."""
        history = self.chat_service.load_history(self.settings.project_path)
        self.chat.clear()
        if not history:
            return
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                self.chat.append(f"<b style='color:#60a5fa;'>You:</b> {content}\n")
            else:
                self.chat.append(f"<b style='color:#4ade80;'>AI:</b> {content}\n")
        self._set_status(f"Loaded {len(history)} messages from chat history.")

    def _clear_chat_history(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Clear Chat History",
            "Are you sure you want to clear all conversation history for this project?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.chat_service.clear_history(self.settings.project_path)
            self.chat.clear()
            self.chat.append("<b style='color:#94a3b8;'>System: Chat history cleared.</b>\n")
            self._set_status("Chat history cleared.")

    def _export_chat_history(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Chat History", "chat_history.md", "Markdown Files (*.md);;All Files (*)"
        )
        if file_path:
            self.chat_service.export_history_markdown(file_path)
            self._set_status(f"Exported chat history to {file_path}")
            self.chat.append(f"<b style='color:#38bdf8;'>System:</b> Exported chat history to {file_path}\n")

    def open_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File")
        if file_name:
            self.open_editor(Path(file_name))

    def open_editor(self, path: "str | Path", goto_line: int = 0) -> None:
        path = Path(path)
        for idx in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(idx)
            if getattr(w, "path", None) == str(path):
                self.editor_tabs.setCurrentIndex(idx)
                if goto_line:
                    w.go_to_line(goto_line)
                return
        editor = EditorWidget(str(path))
        if self._code_intelligence is not None:
            editor.set_code_intelligence(self._code_intelligence)
        self.editor_tabs.addTab(editor, path.name)
        self.editor_tabs.setCurrentIndex(self.editor_tabs.count() - 1)
        if goto_line:
            editor.go_to_line(goto_line)

    def close_editor_tab(self, index: int) -> None:
        widget = self.editor_tabs.widget(index)
        if isinstance(widget, EditorWidget) and widget.is_dirty:
            reply = QMessageBox.question(
                self, "Unsaved changes",
                f"{Path(widget.path).name} has unsaved changes. Close anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self.editor_tabs.removeTab(index)

    @Slot(str)
    def _on_workspace_changed(self, changed_dir: str) -> None:
        """Refresh explorer and git status when a directory entry changes."""
        folder = self.settings.project_path
        if folder:
            self.file_model.setRootPath(folder)
            self.explorer.setRootIndex(self.file_model.index(folder))
        self.refresh_git_status()
        if self._code_intelligence is not None:
            self._code_intelligence.invalidate_index()

    @Slot(str)
    def _on_file_changed_on_disk(self, changed_file: str) -> None:
        """Reload an open editor tab if the file changed on disk and is unmodified."""
        for idx in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(idx)
            if isinstance(w, EditorWidget) and w.path == changed_file:
                w.reload_from_disk()
                break
        if self._code_intelligence is not None:
            self._code_intelligence.invalidate_index()

    def _on_lsp_diagnostics_received(self, uri: str, diagnostics: list[dict]) -> None:
        """Receive live LSP diagnostics and push to ProblemsPanel."""
        try:
            rel_file = Path(uri.replace("file://", "")).relative_to(Path(self.settings.project_path or ".")).as_posix()
        except ValueError:
            rel_file = uri.replace("file://", "")

        problems = []
        for d in diagnostics:
            sev_num = d.get("severity", 1)
            sev_str = "Error" if sev_num == 1 else "Warning" if sev_num == 2 else "Info"
            range_info = d.get("range", {})
            start = range_info.get("start", {})
            problems.append({
                "severity": sev_str,
                "message": d.get("message", ""),
                "file": rel_file,
                "line": start.get("line", 0) + 1,
                "col": start.get("character", 0),
                "source": "LSP",
            })

        self.problems_panel.set_problems(problems)


    def _save_current_editor(self) -> None:
        curr = self.editor_tabs.currentWidget()
        if isinstance(curr, EditorWidget):
            curr.save()
            self._set_status(f"Saved {Path(curr.path).name}")
            # Update dirty indicator in tab title
            idx = self.editor_tabs.currentIndex()
            name = Path(curr.path).name
            self.editor_tabs.setTabText(idx, name)

    def _open_selected_file_from_tree(self, index) -> None:
        file_path = Path(self.file_model.filePath(index))
        if file_path.is_file():
            self.open_editor(file_path)

    def _explorer_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        index = self.explorer.indexAt(pos)
        menu = QMenu(self)
        if index.isValid():
            file_path = Path(self.file_model.filePath(index))
            if file_path.is_file():
                menu.addAction("Open", lambda: self.open_editor(file_path))
                menu.addAction("Ask AI about this file", lambda: self._run_ai_prompt(
                    f"Explain the purpose and structure of {file_path.relative_to(Path(self.settings.project_path or '.'))}"
                ))
                menu.addSeparator()
                menu.addAction("Delete", lambda: self._delete_file_from_explorer(file_path))
        menu.addSeparator()
        menu.addAction("New File…", self._new_file_in_project)
        menu.addAction("Refresh", lambda: self.file_model.setRootPath(self.settings.project_path or str(Path.cwd())))
        menu.exec_(self.explorer.viewport().mapToGlobal(pos))

    def _delete_file_from_explorer(self, path: Path) -> None:
        reply = QMessageBox.question(self, "Delete file",
            f"Delete {path.name}?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                path.unlink()
                self._set_status(f"Deleted {path.name}")
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _new_file_in_project(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        root = self.settings.project_path or str(Path.cwd())
        name, ok = QInputDialog.getText(self, "New File", "File name (relative path):")
        if ok and name:
            full = Path(root) / name
            full.parent.mkdir(parents=True, exist_ok=True)
            full.touch()
            self.open_editor(full)

    # ------------------------------------------------------------------
    # Tests / Linter / Git
    # ------------------------------------------------------------------

    def run_project_tests(self) -> None:
        root = self.settings.project_path or str(Path.cwd())
        self._set_status("Running tests…")
        self._bottom_tabs.setCurrentWidget(self.test_runner_panel)
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short"],
                cwd=root, capture_output=True, text=True, timeout=300,
            )
            output = completed.stdout + completed.stderr
            self.terminal.write(output)
            passed = completed.returncode == 0
            self.test_runner_panel.set_output(output, passed=passed)
            self._set_status("Tests passed." if passed else "Tests failed — see Test Runner panel.")
        except Exception as exc:
            self.terminal.write(f"Test run failed: {exc}\n")
            self.test_runner_panel.set_output(str(exc), passed=False)

    def _run_linter(self) -> None:
        root = self.settings.project_path or str(Path.cwd())
        self._bottom_tabs.setCurrentWidget(self.terminal)
        try:
            res = subprocess.run(["ruff", "check", "."], cwd=root,
                capture_output=True, text=True, timeout=60)
            self.terminal.write(f"$ ruff check .\n{res.stdout}{res.stderr}\n")
            # Parse problems
            problems = []
            for line in res.stdout.splitlines():
                parts = line.split(":")
                if len(parts) >= 4:
                    problems.append({"file": parts[0], "line": parts[1],
                                     "severity": "Warning", "message": ":".join(parts[3:]).strip()})
            self.problems_panel.set_problems(problems)
            self._bottom_tabs.setCurrentWidget(self.problems_panel)
        except FileNotFoundError:
            self.terminal.write("ruff not found. Install with: pip install ruff\n")
        except Exception as exc:
            self.terminal.write(f"Linter error: {exc}\n")

    def _run_formatter(self) -> None:
        root = self.settings.project_path or str(Path.cwd())
        try:
            res = subprocess.run(["ruff", "format", "."], cwd=root,
                capture_output=True, text=True, timeout=60)
            self.terminal.write(f"$ ruff format .\n{res.stdout}{res.stderr}\n")
            self._set_status("Formatter done.")
        except Exception as exc:
            self.terminal.write(f"Formatter error: {exc}\n")

    def refresh_git_status(self) -> None:
        root = self.settings.project_path or str(Path.cwd())
        try:
            status = subprocess.run(["git", "status", "--short"],
                cwd=root, capture_output=True, text=True)
            diff = subprocess.run(["git", "diff", "--"],
                cwd=root, capture_output=True, text=True)
            branch = subprocess.run(["git", "branch", "--show-current"],
                cwd=root, capture_output=True, text=True)
            self.git_panel.set_git_info(
                status.stdout, diff.stdout, branch.stdout.strip() or "main"
            )
        except Exception:
            pass

    def show_git_file_diff(self, filename: str) -> None:
        root = self.settings.project_path or str(Path.cwd())
        try:
            res = subprocess.run(["git", "diff", "--", filename],
                cwd=root, capture_output=True, text=True)
            self.git_panel.diff_view.setPlainText(res.stdout)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def show_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self.settings_store, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            apply_theme(self, dark=self.settings.dark_theme)
            self._refresh_model_selector()
            self.chat_service.model_manager = ModelManager(self.settings)


# ---------------------------------------------------------------------------
# Settings Dialog — full provider + agent + editor configuration
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, store: SettingsStore, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.store = store
        self.setWindowTitle("Vibe Studio Settings")
        self.resize(580, 600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # ── AI Provider tab ────────────────────────────────────────────
        ai_tab = QWidget()
        ai_form = QFormLayout(ai_tab)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["ollama", "openai-compatible"])
        self.provider_combo.setCurrentText(self.settings.default_provider)

        self.ollama_url_edit = QLineEdit()
        ollama_url = "http://127.0.0.1:11434"
        for p in self.settings.providers:
            if p.kind == "ollama":
                ollama_url = p.base_url
        self.ollama_url_edit.setText(ollama_url)

        self.api_url_edit = QLineEdit()
        api_url = "https://api.openai.com/v1"
        for p in self.settings.providers:
            if p.kind == "openai-compatible":
                api_url = p.base_url
        self.api_url_edit.setText(api_url)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-… (leave blank to use OPENAI_API_KEY env var)")
        for p in self.settings.providers:
            if p.kind == "openai-compatible" and p.api_key:
                self.api_key_edit.setText(p.api_key)

        # Model selection dropdown (editable) + Refresh button
        self.model_combo_box = QComboBox()
        self.model_combo_box.setEditable(True)
        self.model_combo_box.setPlaceholderText("Select or type model name...")
        if self.settings.default_model:
            self.model_combo_box.setCurrentText(self.settings.default_model)

        self.refresh_models_btn = QPushButton("🔄 Refresh")
        self.refresh_models_btn.setToolTip("Auto-detect installed models from provider")
        self.refresh_models_btn.clicked.connect(self._fetch_models)

        model_layout = QHBoxLayout()
        model_layout.addWidget(self.model_combo_box, 1)
        model_layout.addWidget(self.refresh_models_btn)

        # Context window spinbox
        from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox
        self.num_ctx_spin = QSpinBox()
        self.num_ctx_spin.setRange(2048, 131072)
        self.num_ctx_spin.setSingleStep(2048)
        self.num_ctx_spin.setSuffix(" tokens")
        current_num_ctx = 32768
        current_temp = 0.2
        current_max_tokens = 4096
        for p in self.settings.providers:
            if p.kind == "ollama":
                current_num_ctx = getattr(p, "num_ctx", 32768)
                current_temp = getattr(p, "temperature", 0.2)
                current_max_tokens = getattr(p, "max_tokens", 4096)
        self.num_ctx_spin.setValue(current_num_ctx)

        # Temperature spinbox (lower = faster & more deterministic)
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 1.0)
        self.temp_spin.setSingleStep(0.05)
        self.temp_spin.setDecimals(2)
        self.temp_spin.setValue(current_temp)

        # Max Tokens spinbox
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(256, 32768)
        self.max_tokens_spin.setSingleStep(512)
        self.max_tokens_spin.setSuffix(" tokens")
        self.max_tokens_spin.setValue(current_max_tokens)

        ai_form.addRow("Provider:", self.provider_combo)
        ai_form.addRow("Ollama URL:", self.ollama_url_edit)
        ai_form.addRow("API Base URL:", self.api_url_edit)
        ai_form.addRow("API Key:", self.api_key_edit)
        ai_form.addRow("Default Model:", model_layout)
        ai_form.addRow("Context Window:", self.num_ctx_spin)
        ai_form.addRow("Temperature:", self.temp_spin)
        ai_form.addRow("Max Output Tokens:", self.max_tokens_spin)

        # Test connection button
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        ai_form.addRow("", test_btn)
        self.conn_result = QLabel("")
        ai_form.addRow("", self.conn_result)
        tabs.addTab(ai_tab, "AI Provider")

        # ── Agent tab ──────────────────────────────────────────────────
        agent_tab = QWidget()
        agent_form = QFormLayout(agent_tab)

        self.max_iter_edit = QLineEdit("15")
        agent_form.addRow("Max iterations:", self.max_iter_edit)

        self.local_only_cb = QCheckBox("Local-only (Ollama, never send code to remote)")
        self.local_only_cb.setChecked(self.settings.local_only)
        agent_form.addRow("", self.local_only_cb)
        tabs.addTab(agent_tab, "Agent")

        # ── Editor tab ─────────────────────────────────────────────────
        editor_tab = QWidget()
        editor_form = QFormLayout(editor_tab)

        self.font_size_edit = QLineEdit(str(self.settings.font_size))
        self.dark_theme_cb = QCheckBox("Dark theme")
        self.dark_theme_cb.setChecked(self.settings.dark_theme)

        editor_form.addRow("Font size:", self.font_size_edit)
        editor_form.addRow("", self.dark_theme_cb)
        tabs.addTab(editor_tab, "Editor")

        layout.addWidget(tabs)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            "QPushButton{background:#3b82f6;color:white;border:none;border-radius:6px;padding:8px 18px;font-weight:bold;}"
        )
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        # Auto-fetch installed models on open
        self._fetch_models()

    def _fetch_models(self) -> None:
        """Fetch installed models from local Ollama or API and update dropdown."""
        from vibe_studio.providers.ollama_provider import OllamaProvider
        from vibe_studio.providers.openai_compatible_provider import OpenAICompatibleProvider
        provider_kind = self.provider_combo.currentText()
        current = self.model_combo_box.currentText().strip()
        models = []
        try:
            if provider_kind == "ollama":
                url = self.ollama_url_edit.text().strip() or "http://127.0.0.1:11434"
                p = OllamaProvider(base_url=url, timeout=3)
                models = [m.name for m in p.list_models()]
            else:
                key = self.api_key_edit.text().strip() or os.getenv("OPENAI_API_KEY", "")
                p = OpenAICompatibleProvider(
                    base_url=self.api_url_edit.text().strip(), api_key=key, timeout=3
                )
                models = [m.name for m in p.list_models()]
        except Exception:
            pass

        if models:
            self.model_combo_box.clear()
            self.model_combo_box.addItems(models)
            if current and current in models:
                self.model_combo_box.setCurrentText(current)
            elif self.settings.default_model and self.settings.default_model in models:
                self.model_combo_box.setCurrentText(self.settings.default_model)

    def _test_connection(self) -> None:
        from vibe_studio.providers.ollama_provider import OllamaProvider
        from vibe_studio.providers.openai_compatible_provider import OpenAICompatibleProvider
        provider_kind = self.provider_combo.currentText()
        try:
            if provider_kind == "ollama":
                p = OllamaProvider(base_url=self.ollama_url_edit.text().strip(), timeout=5)
                ok = p.test_connection()
                models = [m.name for m in p.list_models()] if ok else []
                if models:
                    self.model_combo_box.clear()
                    self.model_combo_box.addItems(models)
                self.conn_result.setText(
                    f"✓ Connected. Found {len(models)} models: {', '.join(models[:3])}" if ok else "✗ Could not connect to Ollama"
                )
            else:
                key = self.api_key_edit.text().strip() or os.getenv("OPENAI_API_KEY", "")
                p = OpenAICompatibleProvider(
                    base_url=self.api_url_edit.text().strip(), api_key=key, timeout=5
                )
                ok = p.test_connection()
                models = [m.name for m in p.list_models()] if ok else []
                if models:
                    self.model_combo_box.clear()
                    self.model_combo_box.addItems(models)
                self.conn_result.setText("✓ Connected to API" if ok else "✗ API connection failed")
        except Exception as e:
            self.conn_result.setText(f"✗ Error: {e}")

    def _reload_open_editors(self, files: list[str] | set[str] | str) -> None:
        """Reload or close open editor tabs matching changed/deleted files on disk."""
        if isinstance(files, str):
            files = [files]
        for f in files:
            if not f:
                continue
            target_name = Path(f).name
            target_path = Path(f).resolve() if Path(f).is_absolute() else None
            for idx in reversed(range(self.editor_tabs.count())):
                w = self.editor_tabs.widget(idx)
                if isinstance(w, EditorWidget) and getattr(w, "path", None):
                    w_path = Path(w.path).resolve()
                    if w_path.name == target_name or (target_path and w_path == target_path):
                        if not w_path.exists():
                            self.editor_tabs.removeTab(idx)
                            w.deleteLater()
                        else:
                            w.reload_from_disk(force=True)

    def _save(self) -> None:
        provider_kind = self.provider_combo.currentText()
        self.settings.default_provider = provider_kind
        self.settings.default_model = self.model_combo_box.currentText().strip()
        self.settings.local_only = self.local_only_cb.isChecked()
        self.settings.dark_theme = self.dark_theme_cb.isChecked()
        try:
            self.settings.font_size = int(self.font_size_edit.text().strip())
        except ValueError:
            pass

        # Rebuild providers list
        providers = []
        providers.append(ProviderConfig(
            name="ollama", kind="ollama",
            base_url=self.ollama_url_edit.text().strip() or "http://127.0.0.1:11434",
            num_ctx=self.num_ctx_spin.value(),
            temperature=self.temp_spin.value(),
            max_tokens=self.max_tokens_spin.value(),
        ))
        api_key = self.api_key_edit.text().strip()
        providers.append(ProviderConfig(
            name="openai-compatible", kind="openai-compatible",
            base_url=self.api_url_edit.text().strip() or "https://api.openai.com/v1",
            api_key=api_key,
            temperature=self.temp_spin.value(),
            max_tokens=self.max_tokens_spin.value(),
        ))
        self.settings.providers = providers
        self.store.save(self.settings)
        self.accept()


# ---------------------------------------------------------------------------
# Changes panel — shows AI-applied diffs with per-file selection and revert
# ---------------------------------------------------------------------------

class _ChangesPanel(QWidget):
    """Shows AI-applied diffs with per-file selection and individual revert functionality."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row
        self.header = QLabel("No changes yet.")
        self.header.setStyleSheet("color:#94a3b8;font-weight:bold;")
        layout.addWidget(self.header)

        # Selector & buttons row
        ctrl_row = QHBoxLayout()
        self.file_combo = QComboBox()
        self.file_combo.setMinimumWidth(180)
        self.file_combo.currentIndexChanged.connect(self._on_file_selected)
        ctrl_row.addWidget(self.file_combo, 1)

        self.revert_selected_btn = QPushButton("↩ Revert Selected File")
        self.revert_selected_btn.setFixedHeight(26)
        self.revert_selected_btn.clicked.connect(self._revert_selected)
        ctrl_row.addWidget(self.revert_selected_btn)

        self.undo_all_btn = QPushButton("↩ Revert All")
        self.undo_all_btn.setFixedHeight(26)
        self.undo_all_btn.clicked.connect(self._undo_all)
        ctrl_row.addWidget(self.undo_all_btn)

        layout.addLayout(ctrl_row)

        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("monospace", 10))
        self.diff_view.setStyleSheet(
            "QTextEdit{background:#0a0e14;color:#d0d7de;border:1px solid #202a36;border-radius:4px;}"
        )
        layout.addWidget(self.diff_view)

        self._snapshots: list = []

    def set_snapshots(self, snapshots: list) -> None:
        self._snapshots = list(snapshots)
        self.file_combo.blockSignals(True)
        self.file_combo.clear()

        if not self._snapshots:
            self.header.setText("No AI changes in this session.")
            self.diff_view.clear()
            self.file_combo.addItem("No changed files")
            self.file_combo.setEnabled(False)
            self.revert_selected_btn.setEnabled(False)
            self.undo_all_btn.setEnabled(False)
            self.file_combo.blockSignals(False)
            return

        self.file_combo.setEnabled(True)
        self.revert_selected_btn.setEnabled(True)
        self.undo_all_btn.setEnabled(True)

        for snap in self._snapshots:
            file_name = Path(snap.path).name
            diff_lines = snap.diff.splitlines() if snap.diff else []
            added = len([l for l in diff_lines if l.startswith("+") and not l.startswith("+++")])
            removed = len([l for l in diff_lines if l.startswith("-") and not l.startswith("---")])
            self.file_combo.addItem(f"📄 {file_name} (+{added}/-{removed})", snap.path)

        self.file_combo.blockSignals(False)
        self.header.setText(f"{len(self._snapshots)} file change(s) by AI:")
        self._on_file_selected(0)

    def _on_file_selected(self, index: int) -> None:
        if index < 0 or index >= len(self._snapshots):
            self.diff_view.clear()
            return

        snap = self._snapshots[index]
        diff = snap.diff or ""
        file_header = f"<b style='color:#38bdf8;'>─── {snap.path} ───</b><br>"
        diff_html = _diff_to_html(diff)
        self.diff_view.setHtml(
            "<pre style='font-family:monospace;font-size:10px;'>"
            + file_header + diff_html
            + "</pre>"
        )

    def _revert_selected(self) -> None:
        selected_path = self.file_combo.currentData()
        if not selected_path:
            return
        main_win = self.window()
        if not hasattr(main_win, "chat_service") or not main_win.chat_service._agent:
            return
        pt = main_win.chat_service._agent.tool_registry.patch_tools
        ok = pt.revert_file_change(selected_path)
        if ok:
            if hasattr(main_win, "_reload_open_editors"):
                main_win._reload_open_editors(selected_path)
            file_name = Path(selected_path).name
            main_win._set_status(f"Reverted AI changes in {file_name}")
            self.set_snapshots(pt.history)
            if hasattr(main_win, "refresh_git_status"):
                main_win.refresh_git_status()

    def _undo_all(self) -> None:
        main_win = self.window()
        if not hasattr(main_win, "chat_service") or not main_win.chat_service._agent:
            return
        pt = main_win.chat_service._agent.tool_registry.patch_tools
        count = 0
        changed_paths = [s.path for s in pt.history]
        while pt.history:
            pt.undo_last_change()
            count += 1
        if hasattr(main_win, "_reload_open_editors"):
            main_win._reload_open_editors(changed_paths)
        self.header.setText(f"Reverted {count} change(s).")
        self.diff_view.clear()
        self.set_snapshots([])
        if hasattr(main_win, "_set_status"):
            main_win._set_status(f"Reverted {count} AI file change(s).")
        if hasattr(main_win, "refresh_git_status"):
            main_win.refresh_git_status()


def _diff_to_html(diff: str) -> str:
    lines = []
    for line in diff.splitlines():
        esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(f'<span style="color:#4ade80;background:#0d2b17;">{esc}</span><br>')
        elif line.startswith("-") and not line.startswith("---"):
            lines.append(f'<span style="color:#f87171;background:#2b0d0d;">{esc}</span><br>')
        elif line.startswith("@@"):
            lines.append(f'<span style="color:#38bdf8;">{esc}</span><br>')
        else:
            lines.append(f'<span style="color:#64748b;">{esc}</span><br>')
    return "".join(lines)
