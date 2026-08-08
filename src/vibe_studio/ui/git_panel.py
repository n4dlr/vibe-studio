from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class GitPanel(QWidget):
    """Git panel displaying changed files, diff preview, and commit actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        top_row = QHBoxLayout()
        self.branch_label = QLabel("Branch: main")
        self.branch_label.setStyleSheet("font-weight: bold; color: #38bdf8;")

        self.refresh_btn = QPushButton("Refresh Status")
        self.refresh_btn.setStyleSheet("QPushButton { background: #1d2632; color: #eaf3ff; border: 1px solid #2b3341; border-radius: 6px; padding: 4px 10px; }")
        self.refresh_btn.clicked.connect(self._refresh)

        top_row.addWidget(self.branch_label)
        top_row.addStretch()
        top_row.addWidget(self.refresh_btn)
        layout.addLayout(top_row)

        splitter = QSplitter()
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("QListWidget { background: #0a1016; color: #e6edf7; border: 1px solid #202a36; }")
        self.file_list.itemClicked.connect(self._on_file_selected)

        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFontFamily("monospace")
        self.diff_view.setStyleSheet("QTextEdit { background: #0a1016; color: #e6edf7; border: 1px solid #202a36; }")

        splitter.addWidget(self.file_list)
        splitter.addWidget(self.diff_view)
        splitter.setSizes([200, 500])

        layout.addWidget(splitter)

    def set_git_info(self, status_text: str, diff_text: str, branch: str = "main"):
        self.branch_label.setText(f"Branch: {branch}")
        self.file_list.clear()

        lines = [l.strip() for l in status_text.splitlines() if l.strip()]
        for line in lines:
            self.file_list.addItem(line)

        self.diff_view.setPlainText(diff_text)

    def _on_file_selected(self, item):
        filename = item.text().split()[-1]
        main_win = self.window()
        if hasattr(main_win, "show_git_file_diff"):
            main_win.show_git_file_diff(filename)

    def _refresh(self):
        main_win = self.window()
        if hasattr(main_win, "refresh_git_status"):
            main_win.refresh_git_status()
