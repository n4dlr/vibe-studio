"""CanvasPanel — Obsidian-Style Interactive Whiteboard & Markdown Mindmap Studio.

Provides an infinite 2D canvas with draggable cards, rich Markdown notes,
file cards, connecting arrows, and AI mindmap generation.
"""
from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.knowledge.canvas_engine import CanvasDocument, CanvasEdge, CanvasNode, CanvasNodeType

# Theme tokens
_BG_DEEP    = "#0c0d14"
_BG_PANEL   = "#161724"
_BG_RAISED  = "#1d1f30"
_BORDER     = "#26293f"
_TEXT       = "#f1f3f9"
_TEXT_MUTED = "#9ea4be"
_ACCENT     = "#6366f1"
_CYAN       = "#38bdf8"
_EMERALD    = "#34d399"


class CanvasCardItem(QGraphicsItem):
    """Interactive visual card on the infinite whiteboard."""

    def __init__(self, node: CanvasNode, on_edit_cb=None):
        super().__init__()
        self.node = node
        self.on_edit_cb = on_edit_cb
        self.setPos(node.x, node.y)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.node.width, self.node.height)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.node.width, self.node.height, 8, 8)

        border_color = QColor(_ACCENT) if self.isSelected() else QColor(_BORDER)
        painter.fillPath(path, QBrush(QColor(_BG_RAISED)))
        painter.strokePath(path, QPen(border_color, 1.5))

        # Title bar with color
        top_bar = QPainterPath()
        top_bar.addRoundedRect(0, 0, self.node.width, 22, 8, 8)
        painter.fillPath(top_bar, QBrush(QColor(self.node.color)))

        # Header Text
        icon = "📝 Note" if self.node.node_type == CanvasNodeType.TEXT else "📄 File"
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Inter", 8, QFont.Bold))
        painter.drawText(8, 15, icon)

        # Body Text
        painter.setPen(QColor(_TEXT))
        painter.setFont(QFont("Inter", 8))
        text_rect = QRectF(8, 28, self.node.width - 16, self.node.height - 34)
        painter.drawText(text_rect, Qt.TextWordWrap, self.node.text or self.node.file)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.node.x = self.x()
            self.node.y = self.y()
        return super().itemChange(change, value)


class CanvasArrowItem(QGraphicsPathItem):
    """Curved connector arrow between whiteboard cards."""

    def __init__(self, src_item: CanvasCardItem, tgt_item: CanvasCardItem):
        super().__init__()
        self.src_item = src_item
        self.tgt_item = tgt_item
        self.setPen(QPen(QColor(_ACCENT), 2.0))
        self.setZValue(-1)
        self.update_path()

    def update_path(self) -> None:
        p1 = QPointF(self.src_item.x() + self.src_item.node.width, self.src_item.y() + self.src_item.node.height / 2)
        p2 = QPointF(self.tgt_item.x(), self.tgt_item.y() + self.tgt_item.node.height / 2)

        path = QPainterPath(p1)
        dx = max(30.0, abs(p2.x() - p1.x()) * 0.5)
        path.cubicTo(QPointF(p1.x() + dx, p1.y()), QPointF(p2.x() - dx, p2.y()), p2)
        self.setPath(path)


class CanvasPanel(QWidget):
    """Complete Obsidian Whiteboard / Mindmap Panel."""

    def __init__(self, workspace_root: str = ".", parent=None):
        super().__init__(parent)
        self.workspace_root = workspace_root
        self.doc = CanvasDocument()
        self.scene = QGraphicsScene(self)
        self.card_items: dict[str, CanvasCardItem] = {}
        self.arrows: list[CanvasArrowItem] = []

        self._setup_default_mindmap()
        self._setup_ui()

    def _setup_default_mindmap(self) -> None:
        n1 = self.doc.add_text_node("c1", "# Project Architecture\n- Core Agent Pipeline\n- Real-time LSP client\n- Self-Repair Verification", x=50, y=100, color="#6366f1")
        n2 = self.doc.add_text_node("c2", "# Obsidian Graph Engine\n- AST Dependency Graph\n- WikiLinks & Physics Canvas", x=340, y=50, color="#38bdf8")
        n3 = self.doc.add_text_node("c3", "# n8n Automation Engine\n- DAG Node Pipelines\n- Triggers & Playwright Actions", x=340, y=240, color="#34d399")
        self.doc.add_edge("e1", "c1", "c2")
        self.doc.add_edge("e2", "c1", "c3")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        toolbar = QFrame()
        toolbar.setStyleSheet(f"QFrame {{ background: {_BG_RAISED}; border: 1px solid {_BORDER}; border-radius: 8px; padding: 4px; }}")
        tb_l = QHBoxLayout(toolbar)
        tb_l.setContentsMargins(4, 2, 4, 2)
        tb_l.setSpacing(6)

        title = QLabel("📋 Visual Whiteboard Canvas (Obsidian Format)")
        title.setFont(QFont("Inter", 11, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        tb_l.addWidget(title)

        tb_l.addStretch()

        add_note_btn = QPushButton("+ Sticky Note")
        add_note_btn.setStyleSheet(f"background: {_BG_PANEL}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 3px 8px; font-weight: bold;")
        add_note_btn.clicked.connect(self._add_sticky_note)
        tb_l.addWidget(add_note_btn)

        layout.addWidget(toolbar)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setBackgroundBrush(QBrush(QColor(_BG_DEEP)))
        layout.addWidget(self.view, 1)

        self._render_canvas()

    def _render_canvas(self) -> None:
        self.scene.clear()
        self.card_items.clear()
        self.arrows.clear()

        for node in self.doc.nodes.values():
            item = CanvasCardItem(node)
            self.scene.addItem(item)
            self.card_items[node.id] = item

        for edge in self.doc.edges.values():
            src = self.card_items.get(edge.from_node)
            tgt = self.card_items.get(edge.to_node)
            if src and tgt:
                arrow = CanvasArrowItem(src, tgt)
                self.scene.addItem(arrow)
                self.arrows.append(arrow)

    def _add_sticky_note(self) -> None:
        nid = f"note_{uuid.uuid4().hex[:6]}"
        self.doc.add_text_node(nid, "New thinking note...", x=120, y=120)
        self._render_canvas()
