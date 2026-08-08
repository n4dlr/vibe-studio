from __future__ import annotations

import difflib
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class DiffViewerDialog(QDialog):
    """Visual diff viewer for AI code changes showing added (+), removed (-), and unchanged lines."""

    def __init__(self, file_path: str, old_content: str, new_content: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.old_content = old_content
        self.new_content = new_content
        self.accepted_change = False

        self.setWindowTitle(f"AI Diff Review — {file_path}")
        self.resize(900, 600)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel(f"Reviewing changes for: {self.file_path}")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #edf5ff;")
        layout.addWidget(header)

        self.diff_text = QTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setFontFamily("monospace")
        self.diff_text.setStyleSheet("QTextEdit { background: #0a0e14; color: #d0d7de; border: 1px solid #202a36; border-radius: 6px; padding: 8px; }")

        self._render_diff()
        layout.addWidget(self.diff_text)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.reject_btn = QPushButton("Reject Change")
        self.reject_btn.setStyleSheet("QPushButton { background: #dc2626; color: white; border-radius: 6px; padding: 8px 16px; font-weight: bold; } QPushButton:hover { background: #b91c1c; }")
        self.reject_btn.clicked.connect(self.reject)

        self.accept_btn = QPushButton("Accept Change")
        self.accept_btn.setStyleSheet("QPushButton { background: #16a34a; color: white; border-radius: 6px; padding: 8px 16px; font-weight: bold; } QPushButton:hover { background: #15803d; }")
        self.accept_btn.clicked.connect(self._accept_change)

        button_row.addWidget(self.reject_btn)
        button_row.addWidget(self.accept_btn)
        layout.addLayout(button_row)

    def _render_diff(self):
        diff_lines = list(
            difflib.unified_diff(
                self.old_content.splitlines(keepends=True),
                self.new_content.splitlines(keepends=True),
                fromfile=f"a/{self.file_path}",
                tofile=f"b/{self.file_path}",
            )
        )
        html_lines = []
        for line in diff_lines:
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if line.startswith("+") and not line.startswith("+++"):
                html_lines.append(f'<span style="background-color: #133a20; color: #4af626;">{escaped}</span>')
            elif line.startswith("-") and not line.startswith("---"):
                html_lines.append(f'<span style="background-color: #4a1515; color: #f87171;">{escaped}</span>')
            elif line.startswith("@@"):
                html_lines.append(f'<span style="color: #38bdf8; font-weight: bold;">{escaped}</span>')
            else:
                html_lines.append(f'<span style="color: #94a3b8;">{escaped}</span>')

        self.diff_text.setHtml("<pre style='margin:0; font-family: monospace;'>" + "".join(html_lines) + "</pre>")

    def _accept_change(self):
        self.accepted_change = True
        self.accept()
