from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ProblemsPanel(QWidget):
    """Problems panel displaying syntax, linter, compiler errors with 'Ask AI to fix' button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        top_row = QHBoxLayout()
        self.count_label = QLabel("0 Problems")
        self.count_label.setStyleSheet("font-weight: bold; color: #94a3b8;")

        self.fix_btn = QPushButton("Ask AI to Fix All Problems")
        self.fix_btn.setStyleSheet("QPushButton { background: #3b82f6; color: white; border: none; border-radius: 6px; padding: 6px 12px; font-weight: bold; } QPushButton:hover { background: #2563eb; }")
        self.fix_btn.clicked.connect(self._trigger_ai_fix)

        top_row.addWidget(self.count_label)
        top_row.addStretch()
        top_row.addWidget(self.fix_btn)
        layout.addLayout(top_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Severity", "Message", "File", "Line"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setStyleSheet("QTableWidget { background: #0a1016; color: #e6edf7; border: 1px solid #202a36; } QHeaderView::section { background: #171d26; color: #94a3b8; border: none; padding: 4px; }")

        layout.addWidget(self.table)

    def set_problems(self, problems: list[dict[str, str]]):
        self.table.setRowCount(0)
        self.count_label.setText(f"{len(problems)} Problems")
        for p in problems:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(p.get("severity", "Error")))
            self.table.setItem(row, 1, QTableWidgetItem(p.get("message", "")))
            self.table.setItem(row, 2, QTableWidgetItem(p.get("file", "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(p.get("line", ""))))

    def _trigger_ai_fix(self):
        main_win = self.window()
        if hasattr(main_win, "trigger_ai_action"):
            main_win.trigger_ai_action("fix_problems", "", "")
