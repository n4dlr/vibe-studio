from __future__ import annotations

from PySide6.QtWidgets import QTextEdit


class TerminalWidget(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("Terminal output")
        self.append("Vibe Studio terminal ready.\n")

    def write(self, text: str) -> None:
        self.append(text)
