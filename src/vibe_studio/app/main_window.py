from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QThread, Qt
from PySide6.QtGui import QKeyEvent
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
from PySide6.QtCore import QObject, Signal, Slot

from vibe_studio.ai.chat_service import ChatService
from vibe_studio.ai.model_manager import ModelManager
from vibe_studio.core.settings import AppSettings, SettingsStore
from vibe_studio.editor.editor_widget import EditorWidget
from vibe_studio.filesystem.project_manager import ProjectManager
from vibe_studio.terminal.terminal_widget import TerminalWidget
from vibe_studio.ui.theme import apply_theme


class ChatWorker(QObject):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, chat_service):
        super().__init__()
        self.chat_service = chat_service

    @Slot(str)
    def process(self, prompt: str) -> None:
        try:
            response = self.chat_service.chat(prompt)
            self.finished.emit(response)
        except Exception as exc:  # pragma: no cover - runtime-specific path
            self.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore, settings: AppSettings):
        super().__init__()
        self.settings_store = settings_store
        self.settings = settings
        self.project_manager = ProjectManager()
        self.model_manager = ModelManager(settings)
        self.chat_service = ChatService(self.model_manager)
        self._chat_thread: QThread | None = None

        self.setWindowTitle("Vibe Studio")
        self.resize(1480, 940)
        apply_theme(self, dark=settings.dark_theme)

        self._setup_menu()
        self._setup_central_layout()
        self._refresh_model_selector()
        self._open_default_project()

    def _setup_menu(self) -> None:
        self.menuBar().addAction("Open Project", self.open_project)
        self.menuBar().addAction("Open File", self.open_file)
        self.menuBar().addAction("Run AI", lambda: self.chat_service.send_system_message("Project opened and ready."))
        self.menuBar().addAction("Settings", self.show_settings)

    def _setup_central_layout(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setStyleSheet("QWidget#titleBar { background: #171d26; border-bottom: 1px solid #2b3341; }")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 8, 12, 8)
        title_label = QLabel("Vibe Studio")
        title_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #eef5ff;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addWidget(title_bar)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(8)
        self.splitter.setStyleSheet("QSplitter::handle { background: #202a36; }")

        left = QWidget()
        left.setObjectName("sidebarPanel")
        left.setStyleSheet("QWidget#sidebarPanel { background: #0d131a; border-right: 1px solid #202a36; }")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        sidebar_title = QLabel("EXPLORER")
        sidebar_title.setStyleSheet("font-size: 11px; letter-spacing: 1px; color: #8c9ab0; font-weight: 600; text-transform: uppercase;")
        left_layout.addWidget(sidebar_title)

        self.explorer = QTreeView()
        self.explorer.setHeaderHidden(True)
        self.explorer.setAnimated(True)
        self.explorer.setSortingEnabled(False)
        self.explorer.setUniformRowHeights(True)
        self.explorer.setAlternatingRowColors(False)
        self.explorer.setStyleSheet("QTreeView { background: #0d131a; color: #e6edf7; border: 1px solid #1f2a36; border-radius: 8px; }")
        self.file_model = QFileSystemModel()
        self.file_model.setReadOnly(True)
        self.file_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.explorer.setModel(self.file_model)
        self.explorer.doubleClicked.connect(self._open_selected_file_from_tree)
        left_layout.addWidget(self.explorer)

        center = QWidget()
        center.setObjectName("editorPanel")
        center.setStyleSheet("QWidget#editorPanel { background: #0b1016; }")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.setDocumentMode(True)
        self.editor_tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #202a36; background: #0d141b; border-top: none; } QTabBar::tab { background: #181f2a; color: #b0bfd3; padding: 9px 14px; border: 1px solid #202a36; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 4px; } QTabBar::tab:selected { background: #0d141b; color: #edf5ff; }")
        self.editor_tabs.tabCloseRequested.connect(self.close_editor_tab)
        center_layout.addWidget(self.editor_tabs)

        right = QWidget()
        right.setObjectName("chatPanel")
        right.setStyleSheet("QWidget#chatPanel { background: #0d131a; border-left: 1px solid #202a36; }")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(8)

        model_row = QWidget()
        model_row.setStyleSheet("background: transparent;")
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(8)
        model_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet("QComboBox { background: #171d26; color: #edf5ff; border: 1px solid #2b3341; border-radius: 8px; padding: 6px 10px; }")
        model_layout.addWidget(self.model_combo)
        self.refresh_models_button = QPushButton("Refresh")
        self.refresh_models_button.setStyleSheet("QPushButton { background: #1d2632; color: #eaf3ff; border: 1px solid #2b3341; border-radius: 8px; padding: 7px 10px; } QPushButton:hover { background: #222e3b; }")
        self.refresh_models_button.clicked.connect(self._refresh_model_selector)
        model_layout.addWidget(self.refresh_models_button)
        right_layout.addWidget(model_row)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("AI assistant")
        self.chat.setStyleSheet("QTextEdit { background: #101821; color: #edf5ff; border: 1px solid #2b3341; border-radius: 10px; padding: 10px; }")
        right_layout.addWidget(self.chat)

        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText("Ask Vibe Studio...")
        self.chat_input.setFixedHeight(110)
        self.chat_input.keyPressEvent = self._chat_key_press
        self.chat_input.setStyleSheet("QTextEdit { background: #101821; color: #edf5ff; border: 1px solid #2b3341; border-radius: 10px; padding: 10px; }")
        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet("QPushButton { background: #3b82f6; color: white; border: none; border-radius: 10px; padding: 10px 16px; font-weight: 600; } QPushButton:hover { background: #2d6fe8; } QPushButton:disabled { background: #475569; color: #dfe9f8; }")
        self.send_button.clicked.connect(self._send_chat_message)

        self.undo_button = QPushButton("Undo")
        self.undo_button.setStyleSheet("QPushButton { background: #1d2632; color: #eaf3ff; border: 1px solid #2b3341; border-radius: 10px; padding: 10px 14px; font-weight: 600; } QPushButton:hover { background: #222e3b; }")
        self.undo_button.clicked.connect(self._undo_last_change)

        input_row = QWidget()
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        input_layout.addWidget(self.chat_input)
        input_layout.addWidget(self.send_button)
        input_layout.addWidget(self.undo_button)
        right_layout.addWidget(input_row)

        bottom = QWidget()
        bottom.setObjectName("bottomPanel")
        bottom.setStyleSheet("QWidget#bottomPanel { background: #0a1016; border-top: 1px solid #202a36; }")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(10, 8, 10, 8)
        self.terminal = TerminalWidget()
        self.terminal.setStyleSheet("QTextEdit { background: #0a1016; color: #dfeaf8; border: 1px solid #2b3341; border-radius: 8px; padding: 8px; }")
        bottom_layout.addWidget(self.terminal)

        self.splitter.addWidget(left)
        self.splitter.addWidget(center)
        self.splitter.addWidget(right)
        self.splitter.setSizes([220, 820, 360])

        layout.addWidget(self.splitter)
        layout.addWidget(bottom)
        layout.setStretch(1, 1)

        self.setStyleSheet("""
            QMainWindow { background: #0b0f15; color: #e6edf7; }
            QWidget { background: transparent; color: #e6edf7; }
            QMenuBar { background: #171d26; color: #e6edf7; border: 1px solid #2b3341; border-radius: 8px; padding: 4px; }
            QMenuBar::item { background: transparent; padding: 6px 10px; border-radius: 6px; }
            QMenuBar::item:selected { background: #1f2a39; }
            QSplitter::handle { background: #1a212c; }
            QLabel { color: #dfeaf8; }
            QComboBox::drop-down { border: none; }
            QTreeView::branch { background: transparent; }
            QTreeView::item:selected { background: #1d2a3a; color: #f0f7ff; border: 1px solid #395a84; }
            QTreeView::item:hover { background: #162230; }
        """)

    def _chat_key_press(self, event: QKeyEvent) -> None:
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Return:
            self._send_chat_message()
            return
        QTextEdit.keyPressEvent(self.chat_input, event)

    def _send_chat_message(self) -> None:
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat.append(f"You: {text}\n")
        self.chat_input.clear()

        model_name = self.model_combo.currentText() if self.model_combo.count() else ""
        if model_name:
            self.settings.default_model = model_name
            self.model_manager.set_default(self.settings.default_provider, model_name)

        if not self.isVisible():
            response = self.chat_service.chat(text)
            self.chat.append(f"AI: {response}\n")
            return

        self.send_button.setEnabled(False)
        self.send_button.setText("Thinking...")

        worker = ChatWorker(self.chat_service)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(lambda: worker.process(text))
        worker.finished.connect(self._handle_chat_response)
        worker.error.connect(self._handle_chat_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        self._chat_thread = thread

    def _handle_chat_response(self, response: str) -> None:
        self.chat.append(f"AI: {response}\n")
        self.send_button.setEnabled(True)
        self.send_button.setText("Send")

    def _handle_chat_error(self, error: str) -> None:
        self.chat.append(f"AI: Error: {error}\n")
        self.send_button.setEnabled(True)
        self.send_button.setText("Send")

    def _undo_last_change(self) -> None:
        if self.chat_service.revert_last_change():
            self.chat.append("AI: Reverted the last file change.\n")
            self.terminal.append("Reverted last AI file change.\n")
        else:
            self.chat.append("AI: No recent file change to undo.\n")

    def _refresh_model_selector(self) -> None:
        self.model_combo.clear()
        models = self.model_manager.list_models()
        items = [item.get("model", "") for item in models if item.get("model")]
        if not items:
            items = ["Ollama unavailable"]
        self.model_combo.addItems(items)
        if self.settings.default_model and self.settings.default_model in items:
            self.model_combo.setCurrentText(self.settings.default_model)
        elif items and items[0] != "Ollama unavailable":
            self.settings.default_model = items[0]
            self.model_manager.set_default(self.settings.default_provider, items[0])
            self.model_combo.setCurrentText(items[0])

    def _open_default_project(self) -> None:
        default_root = self.settings.project_path or str(Path.cwd())
        if Path(default_root).exists():
            self.open_project(Path(default_root))

    def open_project(self, folder: str | Path | None = None) -> None:
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Open project folder")
            if not folder:
                return
        folder = str(Path(folder))
        self.settings.project_path = folder
        self.settings_store.save(self.settings)
        self.project_manager.open_project(Path(folder))

        self.file_model = QFileSystemModel()
        self.file_model.setReadOnly(True)
        self.file_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.file_model.setRootPath(folder)
        self.explorer.setModel(self.file_model)
        self.explorer.setRootIndex(self.file_model.index(folder))
        self.explorer.expandAll()
        for column in range(1, self.file_model.columnCount()):
            self.explorer.hideColumn(column)

    def _open_selected_file_from_tree(self, index) -> None:
        file_path = Path(self.file_model.filePath(index))
        if file_path.is_file():
            self.open_editor(file_path)

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

    def closeEvent(self, event) -> None:
        self.settings_store.save(self.settings)
        if self._chat_thread is not None:
            self._chat_thread.quit()
            self._chat_thread.wait(1000)
        super().closeEvent(event)

    def close_editor_tab(self, index: int) -> None:
        self.editor_tabs.removeTab(index)

    def show_settings(self) -> None:
        QMessageBox.information(self, "Settings", "Settings are stored in ~/.vibe_studio/settings.json")
