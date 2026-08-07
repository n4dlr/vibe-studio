from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.ai.chat_service import ChatService
from vibe_studio.ai.model_manager import ModelManager
from vibe_studio.core.settings import AppSettings, SettingsStore
from vibe_studio.editor.editor_widget import EditorWidget
from vibe_studio.filesystem.project_manager import ProjectManager
from vibe_studio.terminal.terminal_widget import TerminalWidget
from vibe_studio.ui.theme import apply_theme


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore, settings: AppSettings):
        super().__init__()
        self.settings_store = settings_store
        self.settings = settings
        self.project_manager = ProjectManager()
        self.model_manager = ModelManager(settings)
        self.chat_service = ChatService(self.model_manager)

        self.setWindowTitle("Vibe Studio")
        self.resize(1480, 940)
        apply_theme(self, dark=settings.dark_theme)

        self._setup_menu()
        self._setup_central_layout()

    def _setup_menu(self) -> None:
        self.menuBar().addAction("Open Project", self.open_project)
        self.menuBar().addAction("Open File", self.open_file)
        self.menuBar().addAction("Run AI", lambda: self.chat_service.send_system_message("Project opened and ready."))
        self.menuBar().addAction("Settings", self.show_settings)

    def _setup_central_layout(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.explorer = QTextEdit()
        self.explorer.setReadOnly(True)
        self.explorer.setPlaceholderText("Project explorer")
        left_layout.addWidget(self.explorer)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self.close_editor_tab)
        center_layout.addWidget(self.editor_tabs)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("AI assistant")
        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText("Ask Vibe Studio...")
        self.chat_input.setFixedHeight(110)
        self.chat_input.keyPressEvent = self._chat_key_press
        right_layout.addWidget(self.chat)
        right_layout.addWidget(self.chat_input)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        self.terminal = TerminalWidget()
        bottom_layout.addWidget(self.terminal)

        self.splitter.addWidget(left)
        self.splitter.addWidget(center)
        self.splitter.addWidget(right)
        self.splitter.setSizes([220, 720, 420])

        layout.addWidget(self.splitter)
        layout.addWidget(bottom)
        layout.setStretch(0, 1)

    def _chat_key_press(self, event: QKeyEvent) -> None:
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Return:
            text = self.chat_input.toPlainText().strip()
            if text:
                self.chat.append(f"You: {text}\n")
                self.chat_input.clear()
                response = self.chat_service.chat(text)
                self.chat.append(f"AI: {response}\n")
            return
        QTextEdit.keyPressEvent(self.chat_input, event)

    def open_project(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open project folder")
        if not folder:
            return
        self.settings.project_path = folder
        self.settings_store.save(self.settings)
        self.project_manager.open_project(Path(folder))
        files = self.project_manager.list_files()
        self.explorer.clear()
        self.explorer.setPlainText("\n".join(files)[:8000])

    def open_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File")
        if not file_name:
            return
        self.open_editor(Path(file_name))

    def open_editor(self, path: Path) -> None:
        for index in range(self.editor_tabs.count()):
            widget = self.editor_tabs.widget(index)
            if getattr(widget, "path", None) == str(path):
                self.editor_tabs.setCurrentIndex(index)
                return
        editor = EditorWidget(str(path))
        self.editor_tabs.addTab(editor, path.name)
        self.editor_tabs.setCurrentIndex(self.editor_tabs.count() - 1)

    def close_editor_tab(self, index: int) -> None:
        self.editor_tabs.removeTab(index)

    def show_settings(self) -> None:
        QMessageBox.information(self, "Settings", "Settings are stored in ~/.vibe_studio/settings.json")

    def closeEvent(self, event) -> None:
        self.settings_store.save(self.settings)
        super().closeEvent(event)
