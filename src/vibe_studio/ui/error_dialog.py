"""ErrorDialog — user-friendly error dialog displaying formatted 'What happened?' + 'What to do?' guidance."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ErrorDialog(QDialog):
    def __init__(
        self,
        title: str,
        what_happened: str,
        what_to_do: str,
        technical_details: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 340)
        self._setup_ui(what_happened, what_to_do, technical_details)

    def _setup_ui(self, what_happened: str, what_to_do: str, technical_details: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel("⚠ Error Occurred")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #f87171;")
        layout.addWidget(header)

        # What happened section
        happened_lbl = QLabel(f"<b>What happened?</b><br>{what_happened}")
        happened_lbl.setWordWrap(True)
        happened_lbl.setStyleSheet("color: #e6edf7; font-size: 13px;")
        layout.addWidget(happened_lbl)

        # What to do section
        todo_lbl = QLabel(f"<b>What to do?</b><br>{what_to_do}")
        todo_lbl.setWordWrap(True)
        todo_lbl.setStyleSheet("color: #60a5fa; font-size: 13px;")
        layout.addWidget(todo_lbl)

        # Technical details toggleable view
        if technical_details:
            details = QTextEdit()
            details.setReadOnly(True)
            details.setPlainText(technical_details)
            details.setFont(QFont("monospace", 9))
            details.setStyleSheet("QTextEdit{background:#0b1016;color:#94a3b8;border:1px solid #202a36;}")
            details.setFixedHeight(90)
            layout.addWidget(details)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(
            "QPushButton{background:#3b82f6;color:white;border:none;border-radius:6px;padding:6px 20px;font-weight:bold;}"
        )
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    @classmethod
    def show_error(
        cls,
        title: str,
        what_happened: str,
        what_to_do: str,
        technical_details: str = "",
        parent: QWidget | None = None,
    ) -> None:
        dlg = cls(title, what_happened, what_to_do, technical_details, parent)
        dlg.exec_()
