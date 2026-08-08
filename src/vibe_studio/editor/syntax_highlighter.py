from __future__ import annotations

import re
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class MultiLanguageHighlighter(QSyntaxHighlighter):
    """Provides syntax highlighting for Python, JS/TS, HTML, CSS, JSON, C/C++, Shell, Markdown."""

    def __init__(self, parent, language: str = "python"):
        super().__init__(parent)
        self.language = language.lower()
        self.highlighting_rules = []
        self._setup_rules()

    def _setup_rules(self):
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6"))
        keyword_format.setFontWeight(QFont.Bold)

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#ce9178"))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6a9955"))
        comment_format.setFontItalic(True)

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#b5cea8"))

        func_format = QTextCharFormat()
        func_format.setForeground(QColor("#dcdcaa"))

        if self.language in ("python", "py"):
            keywords = [
                "and", "as", "assert", "async", "await", "break", "class", "continue",
                "def", "del", "elif", "else", "except", "False", "finally", "for", "from",
                "global", "if", "import", "in", "is", "lambda", "None", "nonlocal", "not",
                "or", "pass", "raise", "return", "True", "try", "while", "with", "yield",
            ]
            for kw in keywords:
                pattern = rf"\b{kw}\b"
                self.highlighting_rules.append((re.compile(pattern), keyword_format))

            self.highlighting_rules.append((re.compile(r"#.*"), comment_format))
            self.highlighting_rules.append((re.compile(r"\"[^\"]*\"|'[^']*'"), string_format))
            self.highlighting_rules.append((re.compile(r"\b\d+\.?\d*\b"), number_format))
            self.highlighting_rules.append((re.compile(r"\bdef\s+([A-Za-z0-9_]+)"), func_format))

        elif self.language in ("javascript", "js", "typescript", "ts", "jsx", "tsx"):
            keywords = [
                "async", "await", "break", "case", "catch", "class", "const", "continue",
                "debugger", "default", "delete", "do", "else", "enum", "export", "extends",
                "false", "finally", "for", "function", "if", "import", "in", "instanceof",
                "interface", "let", "new", "null", "return", "super", "switch", "this",
                "throw", "true", "try", "typeof", "var", "void", "while", "with", "yield",
            ]
            for kw in keywords:
                pattern = rf"\b{kw}\b"
                self.highlighting_rules.append((re.compile(pattern), keyword_format))

            self.highlighting_rules.append((re.compile(r"//.*"), comment_format))
            self.highlighting_rules.append((re.compile(r"\"[^\"]*\"|'[^']*'|`[^`]*`"), string_format))
            self.highlighting_rules.append((re.compile(r"\b\d+\.?\d*\b"), number_format))
            self.highlighting_rules.append((re.compile(r"\bfunction\s+([A-Za-z0-9_]+)"), func_format))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self.highlighting_rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)
