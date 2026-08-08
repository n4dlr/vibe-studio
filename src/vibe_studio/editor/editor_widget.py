from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QWidget,
)

from vibe_studio.editor.syntax_highlighter import MultiLanguageHighlighter


class LineNumberArea(QWidget):
    def __init__(self, editor: EditorWidget):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class EditorWidget(QPlainTextEdit):
    """Full-featured code editor with syntax highlighting, line numbers, and inline AI actions.

    Uses QPlainTextEdit for proper block-level API support (firstVisibleBlock,
    blockBoundingGeometry, updateRequest signal, etc.).
    """

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.is_dirty = False
        self.line_number_area = LineNumberArea(self)

        self.setFont(QFont("monospace", 11))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0b1016;
                color: #e6edf7;
                border: none;
                font-family: monospace;
                selection-background-color: #264f78;
            }
        """)

        lang = Path(path).suffix.lstrip(".") or "python"
        self.highlighter = MultiLanguageHighlighter(self.document(), language=lang)

        # QPlainTextEdit has these signals natively
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.textChanged.connect(self._on_text_changed)

        self.update_line_number_area_width(0)
        self._load_file()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _load_file(self) -> None:
        file_path = Path(self.path)
        if file_path.exists():
            text = file_path.read_text(encoding="utf-8", errors="replace")
            self.setPlainText(text)
            self.is_dirty = False

    def _on_text_changed(self):
        self.is_dirty = True

    def save(self) -> None:
        file_path = Path(self.path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(self.toPlainText(), encoding="utf-8")
        self.is_dirty = False

    # ------------------------------------------------------------------
    # Line-number gutter
    # ------------------------------------------------------------------

    def line_number_area_width(self) -> int:
        digits = 1
        max_val = max(1, self.document().blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        space = 15 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(), self.line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#0d131a"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#4e6178"))
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    # ------------------------------------------------------------------
    # Context menu with AI actions
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()

        ai_menu = menu.addMenu("AI Code Actions")
        ai_menu.addAction("Explain Selection", lambda: self.parent_window_action("explain"))
        ai_menu.addAction("Fix Code", lambda: self.parent_window_action("fix"))
        ai_menu.addAction("Refactor", lambda: self.parent_window_action("refactor"))
        ai_menu.addAction("Generate Tests", lambda: self.parent_window_action("tests"))
        ai_menu.addAction("Add Documentation", lambda: self.parent_window_action("docs"))

        menu.exec_(event.globalPos())

    def parent_window_action(self, action_kind: str):
        selection = self.textCursor().selectedText()
        main_win = self.window()
        if hasattr(main_win, "trigger_ai_action"):
            main_win.trigger_ai_action(action_kind, self.path, selection)
