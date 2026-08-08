from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QDir, QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.agents.coding_agent import AutonomyMode
from vibe_studio.ai.chat_service import ChatService
from vibe_studio.ai.model_manager import ModelManager
from vibe_studio.core.settings import AppSettings, SettingsStore
from vibe_studio.editor.diff_viewer import DiffViewerDialog
from vibe_studio.editor.editor_widget import EditorWidget
from vibe_studio.filesystem.project_manager import ProjectManager
from vibe_studio.terminal.terminal_widget import TerminalWidget
from vibe_studio.ui.ai_activity_panel import AIActivityPanel
from vibe_studio.ui.command_palette import CommandPaletteDialog
from vibe_studio.ui.git_panel import GitPanel
from vibe_studio.ui.problems_panel import ProblemsPanel
from vibe_studio.ui.test_runner_panel import TestRunnerPanel
from vibe_studio.ui.theme import apply_theme


class AgentWorker(QObject):
    finished = Signal(str)
    error = Signal(str)
    activity = Signal(str, dict)

    def __init__(self, chat_service: ChatService, prompt: str, mode: AutonomyMode):
        super().__init__()
        self.chat_service = chat_service
        self.prompt = prompt
        self.mode = mode

    @Slot()
    def process(self) -> None:
        try:
            def _activity_callback(event_type: str, data: dict):
                self.activity.emit(event_type, data)

            self.chat_service.add_activity_callback(_activity_callback)
            response = self.chat_service.chat(self.prompt, autonomy_mode=self.mode)
            self.finished.emit(response)
        except Exception as exc:
            self.error.emit(str(exc))


class MainWindow(QMainWindow):
    """VS Code-like Desktop AI IDE main window interface."""

    def __init__(self, settings_store: SettingsStore, settings: AppSettings):
        super().__init__()
        self.settings_store = settings_store
        self.settings = settings
        self.project_manager = ProjectManager()
        self.model_manager = ModelManager(settings)
        self.chat_service = ChatService(self.model_manager)
        self._agent_thread: QThread | None = None

        self.setWindowTitle("Vibe Studio — AI Desktop IDE")
        self.resize(1550, 960)
        apply_theme(self, dark=settings.dark_theme)

        self._setup_menu()
        self._setup_central_layout()
        self._refresh_model_selector()
        self._open_default_project()

    def _setup_menu(self) -> None:
        mb = self.menuBar()

        # File Menu
        file_menu = mb.addMenu("&File")
        file_menu.addAction("Open Project...", self.open_project)
        file_menu.addAction("Open File...", self.open_file)
        file_menu.addAction("Save Current", self._save_current_editor, "Ctrl+S")
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # Edit Menu
        edit_menu = mb.addMenu("&Edit")
        edit_menu.addAction("Command Palette...", self.show_command_palette, "Ctrl+Shift+P")
        edit_menu.addAction("Undo AI Change", self._undo_last_change, "Ctrl+Z")

        # AI & Run Menu
        ai_menu = mb.addMenu("&AI & Run")
        ai_menu.addAction("Analyze Project", lambda: self._run_ai_prompt("Analyze this project and summarize architecture."))
        ai_menu.addAction("Run Tests & Fix", lambda: self.trigger_ai_action("run_tests_and_fix", "", ""))
        ai_menu.addAction("Run Build & Fix", lambda: self.trigger_ai_action("run_build_and_fix", "", ""))
        ai_menu.addAction("Code Review", lambda: self.trigger_ai_action("code_review", "", ""))

        # Settings
        mb.addAction("Settings", self.show_settings)

    def _setup_central_layout(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top Bar
        top_bar = QWidget()
        top_bar.setStyleSheet("background: #171d26; border-bottom: 1px solid #2b3341;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 6, 12, 6)

        title = QLabel("Vibe Studio AI IDE")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #edf5ff;")
        top_layout.addWidget(title)
        top_layout.addStretch()

        self.cmd_palette_btn = QPushButton("Ctrl+Shift+P  Command Palette")
        self.cmd_palette_btn.setStyleSheet("QPushButton { background: #0d131a; color: #94a3b8; border: 1px solid #2b3341; border-radius: 6px; padding: 5px 12px; font-size: 12px; } QPushButton:hover { border-color: #3b82f6; color: #edf5ff; }")
        self.cmd_palette_btn.clicked.connect(self.show_command_palette)
        top_layout.addWidget(self.cmd_palette_btn)

        layout.addWidget(top_bar)

        # Main Splitter (Left Sidebar | Editor Center | Right AI Panel)
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(6)
        self.main_splitter.setStyleSheet("QSplitter::handle { background: #202a36; }")

        # Left Sidebar (Explorer / Search / Git)
        left_tabs = QTabWidget()
        left_tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #202a36; background: #0d131a; } QTabBar::tab { background: #171d26; color: #94a3b8; padding: 8px; border: 1px solid #202a36; } QTabBar::tab:selected { background: #0d131a; color: #edf5ff; }")

        self.explorer = QTreeView()
        self.explorer.setHeaderHidden(True)
        self.explorer.setStyleSheet("QTreeView { background: #0d131a; color: #e6edf7; border: none; }")
        self.file_model = QFileSystemModel()
        self.file_model.setReadOnly(True)
        self.file_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.explorer.setModel(self.file_model)
        self.explorer.doubleClicked.connect(self._open_selected_file_from_tree)

        self.git_panel = GitPanel()

        left_tabs.addTab(self.explorer, "Explorer")
        left_tabs.addTab(self.git_panel, "Git")

        # Center Panel (Editor Tabs)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.setDocumentMode(True)
        self.editor_tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #202a36; background: #0b1016; } QTabBar::tab { background: #181f2a; color: #b0bfd3; padding: 8px 14px; border: 1px solid #202a36; border-top-left-radius: 6px; border-top-right-radius: 6px; } QTabBar::tab:selected { background: #0b1016; color: #edf5ff; }")
        self.editor_tabs.tabCloseRequested.connect(self.close_editor_tab)
        center_layout.addWidget(self.editor_tabs)

        # Right Panel (AI Agent Workspace)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        # Model & Mode Selector Header
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        model_row.addWidget(self.model_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Auto Mode", "Plan Mode", "Ask Mode"])
        model_row.addWidget(self.mode_combo)
        right_layout.addLayout(model_row)

        # AI Tabs (Chat / Live Activity)
        ai_tabs = QTabWidget()
        ai_tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #202a36; background: #0d131a; } QTabBar::tab { background: #171d26; color: #94a3b8; padding: 6px; } QTabBar::tab:selected { background: #0d131a; color: #edf5ff; }")

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("AI Assistant Response Log")
        self.chat.setStyleSheet("QTextEdit { background: #101821; color: #edf5ff; border: 1px solid #2b3341; border-radius: 6px; padding: 8px; }")

        self.activity_panel = AIActivityPanel()

        ai_tabs.addTab(self.chat, "Chat")
        ai_tabs.addTab(self.activity_panel, "AI Activity Feed")
        right_layout.addWidget(ai_tabs)

        # Prompt Input Row
        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText("Ask Vibe Studio (e.g. 'Login page-in backgroundunu dəyiş')...")
        self.chat_input.setFixedHeight(90)
        self.chat_input.setStyleSheet("QTextEdit { background: #101821; color: #edf5ff; border: 1px solid #2b3341; border-radius: 6px; padding: 8px; }")
        self.chat_input.keyPressEvent = self._chat_key_press

        btn_row = QHBoxLayout()
        self.send_btn = QPushButton("Send Task")
        self.send_btn.setStyleSheet("QPushButton { background: #3b82f6; color: white; border: none; border-radius: 6px; padding: 8px 14px; font-weight: bold; } QPushButton:hover { background: #2563eb; }")
        self.send_btn.clicked.connect(self._send_chat_message)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("QPushButton { background: #ef4444; color: white; border: none; border-radius: 6px; padding: 8px 12px; font-weight: bold; } QPushButton:hover { background: #dc2626; }")
        self.stop_btn.clicked.connect(self._stop_agent)

        self.undo_btn = QPushButton("Undo Change")
        self.undo_btn.setStyleSheet("QPushButton { background: #1d2632; color: #eaf3ff; border: 1px solid #2b3341; border-radius: 6px; padding: 8px 12px; } QPushButton:hover { background: #222e3b; }")
        self.undo_btn.clicked.connect(self._undo_last_change)

        btn_row.addWidget(self.send_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.undo_btn)

        right_layout.addWidget(self.chat_input)
        right_layout.addLayout(btn_row)

        self.main_splitter.addWidget(left_tabs)
        self.main_splitter.addWidget(center_widget)
        self.main_splitter.addWidget(right_widget)
        self.main_splitter.setSizes([240, 850, 460])

        # Bottom Splitter (Main Splitter | Terminal / Problems / Tests)
        vertical_splitter = QSplitter(Qt.Vertical)
        vertical_splitter.addWidget(self.main_splitter)

        bottom_tabs = QTabWidget()
        bottom_tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #202a36; background: #0a1016; } QTabBar::tab { background: #171d26; color: #94a3b8; padding: 6px 12px; } QTabBar::tab:selected { background: #0a1016; color: #edf5ff; }")

        self.terminal = TerminalWidget()
        self.problems_panel = ProblemsPanel()
        self.test_runner_panel = TestRunnerPanel()

        bottom_tabs.addTab(self.terminal, "Terminal")
        bottom_tabs.addTab(self.problems_panel, "Problems")
        bottom_tabs.addTab(self.test_runner_panel, "Test Runner")

        vertical_splitter.addWidget(bottom_tabs)
        vertical_splitter.setSizes([720, 240])

        layout.addWidget(vertical_splitter)

    def _chat_key_press(self, event: QKeyEvent) -> None:
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Return:
            self._send_chat_message()
            return
        QTextEdit.keyPressEvent(self.chat_input, event)

    def _send_chat_message(self) -> None:
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self._run_ai_prompt(text)

    def _run_ai_prompt(self, prompt: str) -> None:
        self.chat.append(f"<b>You:</b> {prompt}\n")
        self.chat_input.clear()

        mode_str = self.mode_combo.currentText()
        mode = AutonomyMode.AUTO
        if "Plan" in mode_str:
            mode = AutonomyMode.PLAN
        elif "Ask" in mode_str:
            mode = AutonomyMode.ASK

        if not self.isVisible():
            response = self.chat_service.chat(prompt, autonomy_mode=mode)
            self.chat.append(f"<b>AI:</b> {response}\n")
            return

        self.send_btn.setEnabled(False)
        self.send_btn.setText("Agent Running...")

        worker = AgentWorker(self.chat_service, prompt, mode)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.process)
        worker.activity.connect(self.activity_panel.add_activity_event)
        worker.finished.connect(self._handle_agent_response)
        worker.error.connect(self._handle_agent_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()
        self._agent_thread = thread

    def _handle_agent_response(self, response: str) -> None:
        self.chat.append(f"<b>AI:</b> {response}\n")
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send Task")

    def _handle_agent_error(self, error: str) -> None:
        self.chat.append(f"<b>AI Error:</b> {error}\n")
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send Task")

    def _stop_agent(self) -> None:
        self.chat_service.cancel_current_agent()
        self.chat.append("<b>System:</b> Agent execution stop requested.\n")

    def _undo_last_change(self) -> None:
        if self.chat_service.revert_last_change():
            self.chat.append("<b>AI:</b> Reverted last AI change.\n")
            self.terminal.write("Reverted last file edit.\n")
        else:
            self.chat.append("<b>AI:</b> No recent edit to undo.\n")

    def trigger_ai_action(self, action_kind: str, file_path: str, selection: str):
        prompts = {
            "explain": f"Explain this code snippet in {file_path}:\n```\n{selection}\n```",
            "fix": f"Fix issues in this code snippet in {file_path}:\n```\n{selection}\n```",
            "refactor": f"Refactor and improve code snippet in {file_path}:\n```\n{selection}\n```",
            "tests": f"Generate unit tests for this code snippet in {file_path}:\n```\n{selection}\n```",
            "docs": f"Add documentation comments to code snippet in {file_path}:\n```\n{selection}\n```",
            "run_tests_and_fix": "Run the project tests and automatically fix any failing tests.",
            "run_build_and_fix": "Run the project build and automatically fix any build errors.",
            "code_review": "Inspect the Git diff and perform a comprehensive AI code review.",
            "fix_problems": "Inspect current problems list and fix all errors in the project.",
        }
        prompt = prompts.get(action_kind, f"Perform {action_kind} on {file_path}")
        self._run_ai_prompt(prompt)

    def show_command_palette(self):
        actions = [
            {"category": "AI", "title": "Analyze Project"},
            {"category": "AI", "title": "Run Tests & Fix"},
            {"category": "AI", "title": "Run Build & Fix"},
            {"category": "AI", "title": "Code Review"},
            {"category": "IDE", "title": "Open Project"},
            {"category": "IDE", "title": "Open File"},
            {"category": "IDE", "title": "Save File"},
            {"category": "IDE", "title": "Undo AI Change"},
        ]
        dlg = CommandPaletteDialog(actions, parent=self)
        if dlg.exec_() == CommandPaletteDialog.Accepted and dlg.selected_action:
            title = dlg.selected_action.get("title", "")
            if title == "Open Project":
                self.open_project()
            elif title == "Open File":
                self.open_file()
            elif title == "Save File":
                self._save_current_editor()
            elif title == "Undo AI Change":
                self._undo_last_change()
            elif title == "Analyze Project":
                self._run_ai_prompt("Analyze this project.")
            elif title == "Run Tests & Fix":
                self.trigger_ai_action("run_tests_and_fix", "", "")

    def _refresh_model_selector(self) -> None:
        self.model_combo.clear()
        models = self.model_manager.list_models()
        items = [m.get("model", "") for m in models if m.get("model")]
        if not items:
            items = ["Ollama unavailable"]
        self.model_combo.addItems(items)

    def _open_default_project(self) -> None:
        default_root = self.settings.project_path or str(Path.cwd())
        if Path(default_root).exists():
            self.open_project(Path(default_root))

    def open_project(self, folder: str | Path | None = None) -> None:
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Open Project Folder")
            if not folder:
                return
        folder = str(Path(folder))
        self.settings.project_path = folder
        self.settings_store.save(self.settings)
        self.project_manager.open_project(Path(folder))

        self.file_model.setRootPath(folder)
        self.explorer.setRootIndex(self.file_model.index(folder))

    def open_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File")
        if not file_name:
            return
        self.open_editor(Path(file_name))

    def open_editor(self, path: Path) -> None:
        for idx in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(idx)
            if getattr(w, "path", None) == str(path):
                self.editor_tabs.setCurrentIndex(idx)
                return
        editor = EditorWidget(str(path))
        self.editor_tabs.addTab(editor, path.name)
        self.editor_tabs.setCurrentIndex(self.editor_tabs.count() - 1)

    def close_editor_tab(self, index: int) -> None:
        self.editor_tabs.removeTab(index)

    def _save_current_editor(self):
        curr = self.editor_tabs.currentWidget()
        if isinstance(curr, EditorWidget):
            curr.save()

    def _open_selected_file_from_tree(self, index):
        file_path = Path(self.file_model.filePath(index))
        if file_path.is_file():
            self.open_editor(file_path)

    def run_project_tests(self):
        root = self.settings.project_path or str(Path.cwd())
        self.terminal.write("Running tests...\n")

    def refresh_git_status(self):
        pass

    def show_settings(self) -> None:
        QMessageBox.information(self, "Settings", "Vibe Studio settings saved in ~/.vibe_studio/settings.json")
