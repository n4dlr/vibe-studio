from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget


def apply_theme(widget: QWidget, dark: bool = True) -> None:
    palette = QPalette()
    if dark:
        palette.setColor(QPalette.Window, QColor("#0b0f15"))
        palette.setColor(QPalette.WindowText, QColor("#e6edf7"))
        palette.setColor(QPalette.Base, QColor("#101821"))
        palette.setColor(QPalette.AlternateBase, QColor("#171f2a"))
        palette.setColor(QPalette.ToolTipBase, QColor("#111827"))
        palette.setColor(QPalette.ToolTipText, QColor("#f9fafb"))
        palette.setColor(QPalette.Text, QColor("#e6edf7"))
        palette.setColor(QPalette.Button, QColor("#1a212c"))
        palette.setColor(QPalette.ButtonText, QColor("#f4f7fb"))
        palette.setColor(QPalette.BrightText, QColor("#ffffff"))
        palette.setColor(QPalette.Link, QColor("#7dd3fc"))
        palette.setColor(QPalette.Highlight, QColor("#2563eb"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    else:
        palette.setColor(QPalette.Window, QColor("#f5f7fb"))
        palette.setColor(QPalette.WindowText, QColor("#111827"))
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.AlternateBase, QColor("#e5e7eb"))
        palette.setColor(QPalette.Text, QColor("#111827"))
        palette.setColor(QPalette.Button, QColor("#e5e7eb"))
        palette.setColor(QPalette.ButtonText, QColor("#111827"))
        palette.setColor(QPalette.Highlight, QColor("#93c5fd"))
        palette.setColor(QPalette.HighlightedText, QColor("#111827"))
    widget.setPalette(palette)
