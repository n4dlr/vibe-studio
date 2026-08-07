from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QTextEdit


class EditorWidget(QTextEdit):
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.setPlaceholderText("Editor")
        self._load_file()

    def _load_file(self) -> None:
        file_path = Path(self.path)
        if file_path.exists():
            text = file_path.read_text(encoding="utf-8", errors="replace")
            self.setPlainText(text)

    def save(self) -> None:
        file_path = Path(self.path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(self.toPlainText(), encoding="utf-8")
