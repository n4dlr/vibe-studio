from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QRect, QSize, QStringListModel, QTimer, Qt, Slot
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QCompleter,
    QPlainTextEdit,
    QToolTip,
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
    """Full-featured code editor with syntax highlighting, line numbers, autocomplete,
    LSP document synchronization, and inline AI actions.
    """

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.is_dirty = False
        self.document_version = 1
        self.line_number_area = LineNumberArea(self)
        self._code_intelligence = None  # Set externally via set_code_intelligence()

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

        # Autocomplete setup
        self._completer = QCompleter(self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.activated.connect(self._insert_completion)
        self._completion_model = QStringListModel(self)
        self._completer.setModel(self._completion_model)
        self._completer.popup().setStyleSheet(
            "QListView { background: #0d1926; color: #e6edf7; border: 1px solid #2d4a66; }"
            "QListView::item:selected { background: #1e3a5f; }"
        )

        # Debounce timer (200ms) for sending LSP didChange notifications
        self._lsp_sync_timer = QTimer(self)
        self._lsp_sync_timer.setSingleShot(True)
        self._lsp_sync_timer.setInterval(200)
        self._lsp_sync_timer.timeout.connect(self._sync_lsp_document)

        # Signals
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.textChanged.connect(self._on_text_changed)

        self.update_line_number_area_width(0)
        self._load_file()

    def closeEvent(self, event):
        """Notify LSP client when document is closed."""
        if self._code_intelligence and hasattr(self._code_intelligence, "get_lsp_client"):
            lang = Path(self.path).suffix.lstrip(".") or "python"
            client = self._code_intelligence.get_lsp_client(lang)
            if client:
                client.did_close(self.path)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Code Intelligence & LSP Sync
    # ------------------------------------------------------------------

    def set_code_intelligence(self, engine) -> None:
        """Attach a CodeIntelligenceEngine instance for completions and navigation."""
        self._code_intelligence = engine

        # Send initial didOpen to LSP if available
        if engine and hasattr(engine, "get_lsp_client"):
            lang = Path(self.path).suffix.lstrip(".") or "python"
            client = engine.get_lsp_client(lang)
            if client:
                client.did_open(self.path, self.toPlainText(), language_id=lang)

    def _sync_lsp_document(self) -> None:
        """Debounced handler sending LSP didChange notification with monotonic version increment."""
        if not self._code_intelligence or not hasattr(self._code_intelligence, "get_lsp_client"):
            return

        lang = Path(self.path).suffix.lstrip(".") or "python"
        client = self._code_intelligence.get_lsp_client(lang)
        if client:
            content = self.toPlainText()
            self.document_version = client.did_change(self.path, content)

    def _current_word(self) -> str:
        cursor = self.textCursor()
        cursor.select(cursor.WordUnderCursor)
        return cursor.selectedText()

    def _get_cursor_line_col(self) -> tuple[int, int]:
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber()
        return line, col

    def _trigger_autocomplete(self) -> None:
        if self._code_intelligence is None:
            return

        prefix = self._current_word()
        if len(prefix) < 2:
            self._completer.popup().hide()
            return

        line, col = self._get_cursor_line_col()
        req_version = self.document_version

        completions = self._code_intelligence.get_completions(
            prefix=prefix,
            current_file=self.path,
            line=line,
            column=col,
        )

        # Stale response guard: if user typed while completions were being fetched, verify
        if self.document_version != req_version:
            return

        if not completions:
            self._completer.popup().hide()
            return

        labels = [c.label if hasattr(c, "label") else str(c) for c in completions]
        self._completion_model.setStringList(labels)
        self._completer.setCompletionPrefix(prefix)

        cr = self.cursorRect()
        cr.setWidth(
            self._completer.popup().sizeHintForColumn(0)
            + self._completer.popup().verticalScrollBar().sizeHint().width()
        )
        self._completer.complete(cr)

    def _insert_completion(self, text: str) -> None:
        cursor = self.textCursor()
        prefix = self._completer.completionPrefix()
        for _ in range(len(prefix)):
            cursor.deletePreviousChar()
        cursor.insertText(text)
        self.setTextCursor(cursor)

    def go_to_definition(self) -> None:
        """F12: navigate to the definition of the symbol under cursor using LSP or fallback."""
        if self._code_intelligence is None:
            return
        symbol = self._current_word()
        if not symbol:
            return

        line, col = self._get_cursor_line_col()
        results = self._code_intelligence.find_definition(
            symbol=symbol,
            file_path=self.path,
            line=line,
            column=col,
        )
        if not results:
            return

        best = results[0]
        main_win = self.window()
        if hasattr(main_win, "open_editor"):
            workspace = getattr(self._code_intelligence, "workspace_root", None)
            if workspace:
                full_path = workspace / best.file
                if full_path.exists():
                    main_win.open_editor(full_path, goto_line=best.line)

    def show_hover(self) -> None:
        """Show hover documentation tooltip at cursor position."""
        if self._code_intelligence is None:
            return
        symbol = self._current_word()
        if not symbol:
            return

        line, col = self._get_cursor_line_col()
        hover_res = self._code_intelligence.get_hover_info(
            symbol=symbol,
            file_path=self.path,
            line=line,
            column=col,
        )
        if hover_res and hover_res.docstring:
            QToolTip.showText(self.mapToGlobal(self.cursorRect().bottomRight()), hover_res.docstring, self)

    # ------------------------------------------------------------------
    # Key handling: Ctrl+Space for autocomplete, F12 for definition
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._completer.popup().isVisible():
            if event.key() in (
                Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape,
                Qt.Key_Tab, Qt.Key_Backtab,
            ):
                event.ignore()
                return

        if event.key() == Qt.Key_F12:
            self.go_to_definition()
            return

        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Space:
            self._trigger_autocomplete()
            return

        super().keyPressEvent(event)

        if not event.text():
            return
        if self._completer.popup().isVisible():
            self._trigger_autocomplete()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _load_file(self) -> None:
        file_path = Path(self.path)
        if file_path.exists():
            text = file_path.read_text(encoding="utf-8", errors="replace")
            self.setPlainText(text)
            self.is_dirty = False
            self.document_version = 1

    def reload_from_disk(self) -> None:
        """Reload content from disk if the file has NOT been modified by the user."""
        if not self.is_dirty:
            self._load_file()

    def _on_text_changed(self) -> None:
        # Start debounced LSP sync timer
        self._lsp_sync_timer.start()

        if not self.is_dirty:
            self.is_dirty = True
            # Mark tab title with dot
            tabs = self.parent()
            if tabs is None:
                return
            tab_widget = None
            w = tabs
            while w is not None:
                from PySide6.QtWidgets import QTabWidget
                if isinstance(w, QTabWidget):
                    tab_widget = w
                    break
                w = w.parent()
            if tab_widget:
                for i in range(tab_widget.count()):
                    if tab_widget.widget(i) is self:
                        title = tab_widget.tabText(i)
                        if not title.startswith("●"):
                            tab_widget.setTabText(i, "● " + title)
                        break

    def save(self) -> None:
        file_path = Path(self.path)
        if str(file_path) == "untitled":
            return
        content = self.toPlainText()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        self.is_dirty = False

        # Notify LSP of save
        if self._code_intelligence and hasattr(self._code_intelligence, "get_lsp_client"):
            lang = Path(self.path).suffix.lstrip(".") or "python"
            client = self._code_intelligence.get_lsp_client(lang)
            if client:
                client.did_save(self.path, content)

    def go_to_line(self, line_number: int) -> None:
        """Move cursor to a specific line number (1-indexed)."""
        doc = self.document()
        block = doc.findBlockByLineNumber(max(0, line_number - 1))
        cursor = self.textCursor()
        cursor.setPosition(block.position())
        self.setTextCursor(cursor)
        self.centerCursor()

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
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#0d121a"))

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(QColor("#4b5563"))
                painter.drawText(
                    0, top, self.line_number_area.width() - 5, self.fontMetrics().height(),
                    Qt.AlignRight, number
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1
