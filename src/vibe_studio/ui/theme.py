from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget


def apply_theme(widget: QWidget, dark: bool = True) -> None:
    palette = QPalette()
    if dark:
        palette.setColor(QPalette.Window, QColor("#1f1f24"))
        palette.setColor(QPalette.WindowText, QColor("#e5e5e7"))
        palette.setColor(QPalette.Base, QColor("#111318"))
        palette.setColor(QPalette.AlternateBase, QColor("#212329"))
        palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ToolTipText, QColor("#111111"))
        palette.setColor(QPalette.Text, QColor("#e5e5e7"))
        palette.setColor(QPalette.Button, QColor("#2a2d34"))
        palette.setColor(QPalette.ButtonText, QColor("#f4f4f5"))
        palette.setColor(QPalette.BrightText, QColor("#ffffff"))
        palette.setColor(QPalette.Link, QColor("#78c7ff"))
        palette.setColor(QPalette.Highlight, QColor("#3b82f6"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    else:
        palette.setColor(QPalette.Window, QColor("#f5f5f5"))
        palette.setColor(QPalette.WindowText, QColor("#111827"))
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.AlternateBase, QColor("#e5e7eb"))
        palette.setColor(QPalette.Text, QColor("#111827"))
        palette.setColor(QPalette.Button, QColor("#e5e7eb"))
        palette.setColor(QPalette.ButtonText, QColor("#111827"))
        palette.setColor(QPalette.Highlight, QColor("#93c5fd"))
        palette.setColor(QPalette.HighlightedText, QColor("#111827"))
    widget.setPalette(palette)
