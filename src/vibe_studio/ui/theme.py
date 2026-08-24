"""Theme Engine — Cyber-Obsidian & Glassmorphic Design System for Vibe Studio.

Provides an ultra-high-end, modern desktop IDE aesthetic:
- Radiant gradient accents (Indigo -> Electric Violet -> Cyber Cyan)
- Soft glassmorphism borders and high-contrast eye-care typography
- Custom sleek scrollbars, rounded card layouts, and floating HUD chips
- Interactive micro-states for buttons, tree items, tab bars, and dropdowns
- Multi-DPI typography stack: Inter, JetBrains Mono, Fira Code, system-ui
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

# ── Cosmic Obsidian & Glassmorphism Design Tokens ───────────────────────────
_BG_DEEP     = "#0c0d14"  # Main Window deep background
_BG_BASE     = "#11121c"  # Central editor & workspace background
_BG_PANEL    = "#161724"  # Sidebars, toolbars, bottom docks
_BG_RAISED   = "#1d1f30"  # Elevated cards, input fields, dropdown menus
_BG_HOVER    = "#272a42"  # Interactive hover state
_BG_SELECTED = "#343859"  # Active selection highlight
_BG_GLASS    = "rgba(26, 28, 44, 0.75)"

_BORDER      = "#26293f"  # Subtle low-contrast structural border
_BORDER_LIGHT= "#363a59"  # Slightly highlighted border
_BORDER_FOC  = "#7c3aed"  # Electric Violet focus ring
_BORDER_GLOW = "rgba(124, 58, 237, 0.4)"

_TEXT        = "#f1f3f9"  # Crisp primary text
_TEXT_DIM    = "#9ea4be"  # Secondary slate text
_TEXT_MUTED  = "#636985"  # Tertiary / disabled text

# Vibrant Radiant Accents
_ACCENT      = "#6366f1"  # Modern Indigo
_ACCENT_HOV  = "#4f46e5"  # Deep Indigo hover
_ACCENT_VIO  = "#8b5cf6"  # Electric Violet
_ACCENT_CYAN = "#06b6d4"  # Cyber Cyan
_SUCCESS     = "#10b981"  # Emerald Green
_WARN        = "#f59e0b"  # Amber Orange
_DANGER      = "#f43f5e"  # Rose Red

# ── Ultra-Modern Master Stylesheet (QSS) ────────────────────────────────────
DARK_QSS = f"""
/* ── Global Typography & Base ────────────────────────────────── */
QWidget {{
    background-color: {_BG_BASE};
    color: {_TEXT};
    font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
    font-size: 13px;
    font-weight: 400;
}}

/* ── Main Window & Dialogs ───────────────────────────────────── */
QMainWindow, QDialog {{
    background-color: {_BG_DEEP};
}}

/* ── MenuBar ─────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {_BG_DEEP};
    color: {_TEXT_DIM};
    border-bottom: 1px solid {_BORDER};
    padding: 3px 6px;
    font-weight: 500;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 12px;
    border-radius: 6px;
    margin: 1px 2px;
}}
QMenuBar::item:selected,
QMenuBar::item:pressed {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
}}

/* ── Dropdown & Context Menus ────────────────────────────────── */
QMenu {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER_LIGHT};
    border-radius: 8px;
    padding: 6px 4px;
}}
QMenu::item {{
    padding: 7px 30px 7px 14px;
    border-radius: 5px;
    margin: 1px 4px;
    font-size: 12px;
}}
QMenu::item:selected {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_ACCENT}, stop:1 {_ACCENT_VIO});
    color: #ffffff;
    font-weight: 500;
}}
QMenu::item:disabled {{
    color: {_TEXT_MUTED};
}}
QMenu::separator {{
    height: 1px;
    background: {_BORDER};
    margin: 5px 8px;
}}

/* ── ComboBox / Dropdowns ────────────────────────────────────── */
QComboBox {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 5px 30px 5px 12px;
    min-height: 24px;
    font-size: 12px;
}}
QComboBox:hover {{
    border-color: {_BORDER_LIGHT};
    background-color: {_BG_HOVER};
}}
QComboBox:focus {{
    border: 1px solid {_BORDER_FOC};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid {_BORDER};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: transparent;
}}
QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {_TEXT_DIM};
}}
QComboBox QAbstractItemView {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER_LIGHT};
    border-radius: 8px;
    selection-background-color: {_BG_SELECTED};
    selection-color: #ffffff;
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 12px;
    min-height: 26px;
    border-radius: 5px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {_BG_HOVER};
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {_ACCENT};
    color: white;
}}

/* ── Sleek Custom Scrollbars ─────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 7px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {_BORDER_LIGHT};
    min-height: 32px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 7px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {_BORDER_LIGHT};
    min-width: 32px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {_TEXT_MUTED};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Tab Bar & Tab Widgets ───────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {_BORDER};
    background: {_BG_BASE};
    border-radius: 0px 8px 8px 8px;
}}
QTabBar::tab {{
    background: {_BG_PANEL};
    color: {_TEXT_DIM};
    padding: 8px 16px;
    border: 1px solid {_BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
    font-weight: 500;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background: {_BG_BASE};
    color: #ffffff;
    border-top: 2px solid {_ACCENT};
    border-bottom: 1px solid {_BG_BASE};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: {_BG_HOVER};
    color: {_TEXT};
}}
QTabBar::close-button {{
    image: none;
    subcontrol-position: right;
    margin-left: 6px;
    border-radius: 3px;
    padding: 2px;
}}
QTabBar::close-button:hover {{
    background-color: {_DANGER};
}}

/* ── Push Buttons & Action Triggers ──────────────────────────── */
QPushButton {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {_BG_HOVER};
    border-color: {_BORDER_LIGHT};
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: {_BG_SELECTED};
}}
QPushButton:disabled {{
    color: {_TEXT_MUTED};
    background-color: {_BG_PANEL};
    border-color: {_BORDER};
}}

/* ── Text Edits, PlainTextEdits, LineEdits ───────────────────── */
QTextEdit, QPlainTextEdit {{
    background-color: {_BG_PANEL};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 8px;
    selection-background-color: {_BG_SELECTED};
    selection-color: #ffffff;
    font-family: "JetBrains Mono", "Fira Code", monospace;
    font-size: 12px;
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {_BORDER_FOC};
}}
QLineEdit {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    selection-background-color: {_BG_SELECTED};
    font-size: 12px;
}}
QLineEdit:focus {{
    border: 1px solid {_BORDER_FOC};
}}

/* ── TreeView / TableView / File Explorer ────────────────────── */
QTreeView, QListView, QTableView {{
    background-color: {_BG_BASE};
    color: {_TEXT};
    border: none;
    alternate-background-color: {_BG_PANEL};
    selection-background-color: {_BG_SELECTED};
    selection-color: #ffffff;
    outline: none;
    font-size: 12px;
}}
QTreeView::item, QListView::item {{
    padding: 4px 6px;
    border-radius: 4px;
    margin: 1px 2px;
}}
QTreeView::item:hover, QListView::item:hover {{
    background-color: {_BG_HOVER};
}}
QTreeView::item:selected, QListView::item:selected {{
    background-color: {_BG_SELECTED};
    color: #ffffff;
}}
QHeaderView::section {{
    background-color: {_BG_PANEL};
    color: {_TEXT_DIM};
    border: none;
    border-bottom: 1px solid {_BORDER};
    padding: 6px 10px;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* ── Splitters ───────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {_BORDER};
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 2px;
}}
QSplitter::handle:hover {{
    background-color: {_ACCENT};
}}

/* ── Tooltips ────────────────────────────────────────────────── */
QToolTip {{
    background-color: {_BG_RAISED};
    color: {_TEXT};
    border: 1px solid {_BORDER_LIGHT};
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
}}

/* ── Status Bar ──────────────────────────────────────────────── */
QStatusBar {{
    background-color: {_BG_DEEP};
    color: {_TEXT_DIM};
    border-top: 1px solid {_BORDER};
    font-size: 11px;
    font-weight: 500;
}}

/* ── GroupBox & Cards ────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {_BORDER};
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 12px;
    color: {_TEXT_DIM};
    font-weight: 600;
    font-size: 11px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    background-color: transparent;
    color: {_TEXT};
}}

/* ── CheckBox & RadioButton ──────────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {_TEXT};
    spacing: 8px;
    font-size: 12px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {_BORDER_LIGHT};
    border-radius: 4px;
    background: {_BG_RAISED};
}}
QCheckBox::indicator:hover {{
    border-color: {_ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {_ACCENT};
    border-color: {_ACCENT};
}}

/* ── Progress Bar ────────────────────────────────────────────── */
QProgressBar {{
    background: {_BG_RAISED};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    text-align: center;
    font-size: 10px;
    font-weight: bold;
    color: #ffffff;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_ACCENT}, stop:1 {_ACCENT_CYAN});
    border-radius: 3px;
}}
"""


def apply_theme(widget: QWidget, dark: bool = True) -> None:
    """Apply Cyber-Obsidian dark theme across all application windows and widgets."""
    app = QApplication.instance()

    if dark:
        palette = QPalette()
        palette.setColor(QPalette.Window,          QColor(_BG_PANEL))
        palette.setColor(QPalette.WindowText,      QColor(_TEXT))
        palette.setColor(QPalette.Base,            QColor(_BG_BASE))
        palette.setColor(QPalette.AlternateBase,   QColor(_BG_RAISED))
        palette.setColor(QPalette.ToolTipBase,     QColor(_BG_RAISED))
        palette.setColor(QPalette.ToolTipText,     QColor(_TEXT))
        palette.setColor(QPalette.Text,            QColor(_TEXT))
        palette.setColor(QPalette.Button,          QColor(_BG_RAISED))
        palette.setColor(QPalette.ButtonText,      QColor(_TEXT))
        palette.setColor(QPalette.BrightText,      QColor("#ffffff"))
        palette.setColor(QPalette.Link,            QColor(_ACCENT_CYAN))
        palette.setColor(QPalette.Highlight,       QColor(_ACCENT))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))

        if app:
            app.setPalette(palette)
            app.setStyleSheet(DARK_QSS)
        widget.setPalette(palette)
    else:
        if app:
            app.setStyleSheet("")
