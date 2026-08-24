"""MemoryGraphPanel — Persistent Agent Memory & ADR Browser.

Displays the agent's cross-session knowledge graph: completed tasks, error fixes,
code patterns, user preferences, and Architecture Decision Records.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.knowledge.memory_graph import ADRRecord, AgentMemoryGraph, MemoryKind

_BG_DEEP    = "#0c0d14"
_BG_PANEL   = "#161724"
_BG_RAISED  = "#1d1f30"
_BORDER     = "#26293f"
_TEXT       = "#f1f3f9"
_TEXT_MUTED = "#9ea4be"
_ACCENT     = "#6366f1"
_SUCCESS    = "#34d399"
_WARNING    = "#fbbf24"
_DANGER     = "#f87171"

KIND_COLORS = {
    MemoryKind.TASK_COMPLETED:  _SUCCESS,
    MemoryKind.ERROR_FIXED:     _DANGER,
    MemoryKind.CODE_PATTERN:    "#38bdf8",
    MemoryKind.ADR:             _WARNING,
    MemoryKind.USER_PREFERENCE: "#c084fc",
    MemoryKind.INSIGHT:         _ACCENT,
    MemoryKind.WORKFLOW_RUN:    "#34d399",
    MemoryKind.BUG_SIGNATURE:   _DANGER,
    MemoryKind.TOOL_USAGE:      _TEXT_MUTED,
}


class MemoryGraphPanel(QWidget):
    """Browse and search the agent's persistent memory graph."""

    def __init__(self, workspace_root: str = ".", parent=None):
        super().__init__(parent)
        self.graph = AgentMemoryGraph(workspace_root)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet(f"QFrame {{ background: {_BG_RAISED}; border: 1px solid {_BORDER}; border-radius: 8px; padding: 4px; }}")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(4, 2, 4, 2)
        tb.setSpacing(6)

        title = QLabel("🧠 Agent Memory Graph")
        title.setFont(QFont("Inter", 11, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        tb.addWidget(title)

        tb.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search memories...")
        self.search_input.setFixedWidth(180)
        self.search_input.setStyleSheet(f"background: {_BG_PANEL}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
        self.search_input.textChanged.connect(self._on_search)
        tb.addWidget(self.search_input)

        self.stats_label = QLabel("0 memories")
        self.stats_label.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 10px;")
        tb.addWidget(self.stats_label)

        layout.addWidget(toolbar)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabBar::tab {{ background: {_BG_PANEL}; color: {_TEXT_MUTED}; padding: 6px 14px; font-size: 11px; }}"
            f"QTabBar::tab:selected {{ color: #ffffff; border-bottom: 2px solid {_ACCENT}; }}"
        )

        tabs.addTab(self._build_memories_tab(), "📚 Memories")
        tabs.addTab(self._build_adrs_tab(), "📋 ADRs")
        tabs.addTab(self._build_add_memory_tab(), "➕ Record")

        layout.addWidget(tabs, 1)

    def _build_memories_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 4, 0, 0)
        l.setSpacing(4)

        splitter = QSplitter(Qt.Vertical)

        self.memory_list = QListWidget()
        self.memory_list.setStyleSheet(f"QListWidget {{ background: {_BG_DEEP}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 6px; font-size: 11px; }} QListWidget::item:selected {{ background: {_ACCENT}; }}")
        self.memory_list.currentItemChanged.connect(self._on_memory_selected)
        splitter.addWidget(self.memory_list)

        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setStyleSheet(f"QTextEdit {{ background: {_BG_PANEL}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 6px; font-size: 11px; padding: 8px; }}")
        splitter.addWidget(self.detail_view)

        l.addWidget(splitter)
        return w

    def _build_adrs_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 4, 0, 0)
        l.setSpacing(4)

        splitter = QSplitter(Qt.Vertical)

        self.adr_list = QListWidget()
        self.adr_list.setStyleSheet(f"QListWidget {{ background: {_BG_DEEP}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 6px; }} QListWidget::item:selected {{ background: {_ACCENT}; }}")
        self.adr_list.currentItemChanged.connect(self._on_adr_selected)
        splitter.addWidget(self.adr_list)

        self.adr_detail = QTextEdit()
        self.adr_detail.setReadOnly(True)
        self.adr_detail.setStyleSheet(f"QTextEdit {{ background: {_BG_PANEL}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 6px; font-family: monospace; font-size: 11px; padding: 8px; }}")
        splitter.addWidget(self.adr_detail)

        l.addWidget(splitter)
        return w

    def _build_add_memory_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        l.setSpacing(8)

        l.addWidget(QLabel("Record a new ADR (Architecture Decision Record):"))

        # ADR Form
        form_style = f"background: {_BG_RAISED}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 4px;"
        self.adr_title = QLineEdit()
        self.adr_title.setPlaceholderText("ADR Title (e.g. Use SQLite for local indexes)")
        self.adr_title.setStyleSheet(form_style)
        l.addWidget(self.adr_title)

        self.adr_context = QTextEdit()
        self.adr_context.setPlaceholderText("Context: Why does this decision need to be made?")
        self.adr_context.setFixedHeight(70)
        self.adr_context.setStyleSheet(form_style)
        l.addWidget(self.adr_context)

        self.adr_decision = QTextEdit()
        self.adr_decision.setPlaceholderText("Decision: What was decided?")
        self.adr_decision.setFixedHeight(70)
        self.adr_decision.setStyleSheet(form_style)
        l.addWidget(self.adr_decision)

        self.adr_consequences = QTextEdit()
        self.adr_consequences.setPlaceholderText("Consequences: Trade-offs, positive and negative?")
        self.adr_consequences.setFixedHeight(70)
        self.adr_consequences.setStyleSheet(form_style)
        l.addWidget(self.adr_consequences)

        save_btn = QPushButton("💾 Save ADR")
        save_btn.setStyleSheet(f"background: {_ACCENT}; color: #fff; border: none; border-radius: 4px; padding: 6px 14px; font-weight: bold;")
        save_btn.clicked.connect(self._save_adr)
        l.addWidget(save_btn)
        l.addStretch()
        return w

    def refresh(self) -> None:
        """Reload memory list from database."""
        entries = self.graph.get_recent(limit=100)
        self.memory_list.clear()
        for entry in entries:
            age = f"{entry.age_hours:.0f}h ago" if entry.age_hours < 48 else f"{entry.age_hours/24:.0f}d ago"
            text = f"[{entry.kind.value.replace('_', ' ')}] {entry.content[:60]}... ({age})"
            item = QListWidgetItem(text)
            color = KIND_COLORS.get(entry.kind, _TEXT_MUTED)
            item.setForeground(QColor(color))
            item.setData(Qt.UserRole, entry)
            self.memory_list.addItem(item)

        adrs = self.graph.get_adrs()
        self.adr_list.clear()
        for i, adr in enumerate(adrs):
            item = QListWidgetItem(f"ADR-{i+1:03d}: {adr['title']}")
            item.setData(Qt.UserRole, adr)
            item.setForeground(QColor(_WARNING))
            self.adr_list.addItem(item)

        stats = self.graph.stats()
        self.stats_label.setText(f"{stats['total_memories']} memories · {stats['adrs']} ADRs")

    def _on_search(self, query: str) -> None:
        if not query.strip():
            self.refresh()
            return
        entries = self.graph.search(query)
        self.memory_list.clear()
        for entry in entries:
            text = f"[{entry.kind.value}] {entry.content[:70]}"
            item = QListWidgetItem(text)
            item.setForeground(QColor(KIND_COLORS.get(entry.kind, _TEXT_MUTED)))
            item.setData(Qt.UserRole, entry)
            self.memory_list.addItem(item)

    def _on_memory_selected(self, current: QListWidgetItem, _) -> None:
        if not current:
            return
        entry = current.data(Qt.UserRole)
        if entry:
            detail = f"Kind: {entry.kind.value}\n"
            detail += f"Time: {time.strftime('%Y-%m-%d %H:%M', time.localtime(entry.timestamp))}\n"
            detail += f"Tags: {', '.join(entry.tags)}\n\n"
            detail += entry.content
            self.detail_view.setPlainText(detail)

    def _on_adr_selected(self, current: QListWidgetItem, _) -> None:
        if not current:
            return
        adr = current.data(Qt.UserRole)
        if adr:
            md = f"# {adr['title']}\n\n"
            md += f"**Status:** {adr['status']}\n\n"
            md += f"## Context\n{adr['context']}\n\n"
            md += f"## Decision\n{adr['decision']}\n\n"
            md += f"## Consequences\n{adr['consequences']}\n"
            self.adr_detail.setPlainText(md)

    def _save_adr(self) -> None:
        title = self.adr_title.text().strip()
        if not title:
            return
        adr = ADRRecord(
            title=title,
            context=self.adr_context.toPlainText(),
            decision=self.adr_decision.toPlainText(),
            consequences=self.adr_consequences.toPlainText(),
        )
        self.graph.record_adr(adr)
        self.adr_title.clear()
        self.adr_context.clear()
        self.adr_decision.clear()
        self.adr_consequences.clear()
        self.refresh()
