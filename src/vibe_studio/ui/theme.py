from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

# ── Dark colour tokens ────────────────────────────────────────────────────────
_BG_DEEP    = "#080d12"
_BG_BASE    = "#0b1016"
_BG_PANEL   = "#101821"
_BG_RAISED  = "#161e2b"
_BG_HOVER   = "#1c2636"
_BG_SELECTED = "#1e3a5f"

_BORDER     = "#1e2d40"
_BORDER_FOC = "#3b82f6"

_TEXT       = "#e6edf7"
_TEXT_DIM   = "#8da1b4"
_TEXT_MUTED = "#4e6178"

_ACCENT     = "#3b82f6"
_ACCENT_HOV = "#2563eb"
_DANGER     = "#ef4444"

# ── Full dark stylesheet ──────────────────────────────────────────────────────
DARK_QSS = f"""
/* ── Global ──────────────────────────────────────────────────── */
QWidget {{
    background-color: {_BG_BASE};
    color: {_TEXT};
    font-family: "Inter", "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}}

/* ── Main Window ─────────────────────────────────────────────── */
QMainWindow {{
    background-color: {_BG_DEEP};
}}

/* ── MenuBar ─────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {_BG_PANEL};
    color: {_TEXT};
    border-bottom: 1px solid {_BORDER};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected,
QMenuBar::item:pressed {{
    background-color: {_BG_HOVER};
    color: {_TEXT};
}}

/* ── Dropdown Menu (right-click / menubar) ───────────────────── */
QMenu {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 4px 0px;
}}
QMenu::item {{
    padding: 7px 28px 7px 14px;
    border-radius: 4px;
    margin: 1px 4px;
}}
QMenu::item:selected {{
    background-color: {_BG_SELECTED};
    color: {_TEXT};
}}
QMenu::item:disabled {{
    color: {_TEXT_MUTED};
}}
QMenu::separator {{
    height: 1px;
    background: {_BORDER};
    margin: 4px 8px;
}}

/* ── ComboBox ────────────────────────────────────────────────── */
QComboBox {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 4px 28px 4px 10px;
    min-height: 24px;
    selection-background-color: {_BG_SELECTED};
}}
QComboBox:hover {{
    border-color: {_BORDER_FOC};
}}
QComboBox:focus {{
    border-color: {_BORDER_FOC};
    outline: none;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid {_BORDER};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: {_BG_RAISED};
}}
QComboBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left:  4px solid transparent;
    border-right: 4px solid transparent;
    border-top:   6px solid {_TEXT_DIM};
}}
/* The popup list of options */
QComboBox QAbstractItemView {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    selection-background-color: {_BG_SELECTED};
    selection-color: {_TEXT};
    outline: none;
    padding: 2px;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 12px;
    min-height: 26px;
    border-radius: 4px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {_BG_HOVER};
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {_BG_SELECTED};
}}

/* ── Scrollbars ──────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {_BG_BASE};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {_BORDER};
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {_BG_BASE};
    height: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {_BORDER};
    min-width: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {_TEXT_MUTED};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── TabWidget ───────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {_BORDER};
    background: {_BG_BASE};
    border-radius: 0px 6px 6px 6px;
}}
QTabBar::tab {{
    background: {_BG_PANEL};
    color: {_TEXT_DIM};
    padding: 7px 16px;
    border: 1px solid {_BORDER};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {_BG_BASE};
    color: {_TEXT};
    border-bottom: 2px solid {_ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {_BG_HOVER};
    color: {_TEXT};
}}

/* ── Buttons ─────────────────────────────────────────────────── */
QPushButton {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {_BG_HOVER};
    border-color: {_BORDER_FOC};
}}
QPushButton:pressed {{
    background-color: {_BG_SELECTED};
}}
QPushButton:disabled {{
    color: {_TEXT_MUTED};
    background-color: {_BG_PANEL};
    border-color: {_BORDER};
}}

/* ── Text/Plain Edits ────────────────────────────────────────── */
QTextEdit, QPlainTextEdit {{
    background-color: {_BG_PANEL};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    selection-background-color: {_BG_SELECTED};
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {_BORDER_FOC};
}}
QLineEdit {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 5px 10px;
    selection-background-color: {_BG_SELECTED};
}}
QLineEdit:focus {{
    border-color: {_BORDER_FOC};
}}

/* ── TreeView / ListView / TableView ────────────────────────── */
QTreeView, QListView, QTableView {{
    background-color: {_BG_BASE};
    color: {_TEXT};
    border: none;
    alternate-background-color: {_BG_PANEL};
    selection-background-color: {_BG_SELECTED};
    selection-color: {_TEXT};
    outline: none;
}}
QTreeView::item, QListView::item {{
    padding: 3px 4px;
    border-radius: 3px;
}}
QTreeView::item:hover, QListView::item:hover {{
    background-color: {_BG_HOVER};
}}
QTreeView::item:selected, QListView::item:selected {{
    background-color: {_BG_SELECTED};
}}
QHeaderView::section {{
    background-color: {_BG_PANEL};
    color: {_TEXT_DIM};
    border: none;
    border-bottom: 1px solid {_BORDER};
    padding: 5px 8px;
}}

/* ── Splitter ────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {_BORDER};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical   {{ height: 1px; }}

/* ── Tooltip ─────────────────────────────────────────────────── */
QToolTip {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* ── StatusBar ───────────────────────────────────────────────── */
QStatusBar {{
    background-color: {_BG_PANEL};
    color: {_TEXT_DIM};
    border-top: 1px solid {_BORDER};
}}

/* ── Dialog ──────────────────────────────────────────────────── */
QDialog {{
    background-color: {_BG_PANEL};
}}

/* ── MessageBox ──────────────────────────────────────────────── */
QMessageBox {{
    background-color: {_BG_PANEL};
    color: {_TEXT};
}}

/* ── GroupBox ────────────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {_BORDER};
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    color: {_TEXT_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {_TEXT_DIM};
}}

/* ── CheckBox / RadioButton ──────────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {_TEXT};
    spacing: 6px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {_BORDER};
    border-radius: 3px;
    background: {_BG_RAISED};
}}
QCheckBox::indicator:checked {{
    background: {_ACCENT};
    border-color: {_ACCENT};
}}

/* ── Label ───────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: {_TEXT};
}}
"""


def apply_theme(widget: QWidget, dark: bool = True) -> None:
    """Apply dark (or light) theme to the entire application via QApplication stylesheet."""
    app = QApplication.instance()

    if dark:
        # Set palette for widgets that don't honour QSS (e.g. native file dialogs)
        palette = QPalette()
        palette.setColor(QPalette.Window,           QColor(_BG_PANEL))
        palette.setColor(QPalette.WindowText,       QColor(_TEXT))
        palette.setColor(QPalette.Base,             QColor(_BG_BASE))
        palette.setColor(QPalette.AlternateBase,    QColor(_BG_RAISED))
        palette.setColor(QPalette.ToolTipBase,      QColor(_BG_RAISED))
        palette.setColor(QPalette.ToolTipText,      QColor(_TEXT))
        palette.setColor(QPalette.Text,             QColor(_TEXT))
        palette.setColor(QPalette.Button,           QColor(_BG_RAISED))
        palette.setColor(QPalette.ButtonText,       QColor(_TEXT))
        palette.setColor(QPalette.BrightText,       QColor("#ffffff"))
        palette.setColor(QPalette.Link,             QColor("#7dd3fc"))
        palette.setColor(QPalette.Highlight,        QColor(_ACCENT))
        palette.setColor(QPalette.HighlightedText,  QColor("#ffffff"))
        if app:
            app.setPalette(palette)
            app.setStyleSheet(DARK_QSS)
        widget.setPalette(palette)
    else:
        # Light mode — minimal stylesheet; rely on system defaults
        if app:
            app.setStyleSheet("")
