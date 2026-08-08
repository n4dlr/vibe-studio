from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class CommandPaletteDialog(QDialog):
    """Command palette dialog for searching and triggering IDE and AI actions."""

    def __init__(self, actions: list[dict[str, str]], parent=None):
        super().__init__(parent)
        self.actions = actions
        self.selected_action: dict[str, str] | None = None

        self.setWindowTitle("Command Palette")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup)
        self.resize(600, 350)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type a command or AI action...")
        self.search_input.setStyleSheet("QLineEdit { background: #171d26; color: #edf5ff; border: 1px solid #3b82f6; border-radius: 6px; padding: 10px; font-size: 14px; }")
        self.search_input.textChanged.connect(self._filter_list)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("QListWidget { background: #0d131a; color: #e6edf7; border: 1px solid #202a36; border-radius: 6px; } QListWidget::item { padding: 8px 12px; } QListWidget::item:selected { background: #1d2e42; color: #60a5fa; }")
        self.list_widget.itemActivated.connect(self._on_item_activated)

        layout.addWidget(self.search_input)
        layout.addWidget(self.list_widget)

        self._populate_list(self.actions)

    def _populate_list(self, items: list[dict[str, str]]):
        self.list_widget.clear()
        for item in items:
            l_item = QListWidgetItem(f"{item.get('category', 'IDE')}: {item.get('title', '')}")
            l_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(l_item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _filter_list(self, text: str):
        query = text.lower()
        filtered = [a for a in self.actions if query in a.get("title", "").lower() or query in a.get("category", "").lower()]
        self._populate_list(filtered)

    def _on_item_activated(self, item: QListWidgetItem):
        self.selected_action = item.data(Qt.UserRole)
        self.accept()
