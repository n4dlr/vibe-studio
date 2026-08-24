"""KnowledgeGraphPanel — Interactive Physics-Driven 2D Code & Concept Graph Visualizer.

Obsidian-grade force-directed interactive canvas in PySide6 with glowing hub nodes,
zoom/pan, symbol tooltips, and click-to-open editor integration.
"""
from __future__ import annotations

import math
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.knowledge.graph_engine import EdgeType, GraphEdge, GraphNode, KnowledgeGraphEngine, NodeType

# Theme Tokens
_BG_DEEP    = "#0c0d14"
_BG_PANEL   = "#161724"
_BG_RAISED  = "#1d1f30"
_BORDER     = "#26293f"
_TEXT       = "#f1f3f9"
_TEXT_DIM   = "#9ea4be"
_ACCENT     = "#6366f1"
_ACCENT_CYAN= "#06b6d4"

NODE_COLORS = {
    NodeType.FILE:     QColor("#38bdf8"),
    NodeType.CLASS:    QColor("#c084fc"),
    NodeType.FUNCTION: QColor("#818cf8"),
    NodeType.DOC:      QColor("#34d399"),
    NodeType.MODULE:   QColor("#94a3b8"),
    NodeType.CONCEPT:  QColor("#fbbf24"),
}


class NodeGraphicsItem(QGraphicsItem):
    """Interactive visual representation of a code or doc node."""

    def __init__(self, node: GraphNode, on_open_file: Optional[Callable[[str, int], None]] = None):
        super().__init__()
        self.node = node
        self.on_open_file = on_open_file
        self.setPos(node.x, node.y)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self._is_hovered = False
        self._highlighted = False

        radius = max(6.0, 8.0 + node.centrality * 20.0)
        self.radius = radius
        self.setToolTip(f"<b>{node.name}</b><br>Type: {node.node_type.value}<br>Path: {node.path}:{node.line_number}")

    def boundingRect(self) -> QRectF:
        r = self.radius + 8
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        color = NODE_COLORS.get(self.node.node_type, QColor("#6366f1"))

        # Halo for high-centrality or hovered nodes
        if self._is_hovered or self._highlighted or self.node.centrality > 0.15:
            glow_color = QColor(color)
            glow_color.setAlpha(80)
            painter.setBrush(QBrush(glow_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(0, 0), self.radius + 6, self.radius + 6)

        # Core node circle
        painter.setBrush(QBrush(color))
        border_color = QColor("#ffffff") if (self._is_hovered or self._highlighted) else QColor(_BORDER)
        painter.setPen(QPen(border_color, 1.5))
        painter.drawEllipse(QPointF(0, 0), self.radius, self.radius)

        # Label
        if self.radius > 7.0 or self._is_hovered or self._highlighted:
            painter.setPen(QColor(_TEXT if not self._is_hovered else "#ffffff"))
            font = QFont("Inter", 8, QFont.Bold if self.node.centrality > 0.1 else QFont.Normal)
            painter.setFont(font)
            painter.drawText(int(self.radius + 4), 4, self.node.name[:25])

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.node.path and self.on_open_file:
            self.on_open_file(self.node.path, self.node.line_number)
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.node.x = self.x()
            self.node.y = self.y()
        return super().itemChange(change, value)


class KnowledgeGraphView(QGraphicsView):
    """Zoomable, panable viewport for the knowledge graph."""

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(QColor(_BG_DEEP)))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 0.85
        self.scale(factor, factor)


class KnowledgeGraphPanel(QWidget):
    """Complete Knowledge & Code Graph visualizer panel."""

    file_open_requested = Signal(str, int)

    def __init__(self, workspace_root: str = ".", parent=None):
        super().__init__(parent)
        self.engine = KnowledgeGraphEngine(workspace_root)
        self.scene = QGraphicsScene(self)
        self.node_items: dict[str, NodeGraphicsItem] = {}
        self.edge_items: list[QGraphicsLineItem] = []
        self._sim_steps = 0

        self._setup_ui()
        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._on_physics_tick)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Control Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_RAISED};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 4px 8px;
            }}
        """)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(2, 2, 2, 2)
        tb_layout.setSpacing(6)

        title = QLabel("🕸️ Knowledge & Code Graph")
        title.setFont(QFont("Inter", 11, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        tb_layout.addWidget(title)

        tb_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search symbol or file...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {_BG_PANEL};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }}
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        tb_layout.addWidget(self.search_input)

        scan_btn = QPushButton("↻ Rescan")
        scan_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 3px 10px;
                font-weight: bold;
                font-size: 11px;
            }}
        """)
        scan_btn.clicked.connect(self.refresh_graph)
        tb_layout.addWidget(scan_btn)

        layout.addWidget(toolbar)

        # Main Graph View
        self.view = KnowledgeGraphView(self.scene)
        layout.addWidget(self.view, 1)

    def refresh_graph(self) -> None:
        """Scan workspace and populate graph nodes with physics animation."""
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()

        self.engine.scan_workspace()

        # Add edges
        for edge in self.engine.edges:
            line_item = self.scene.addLine(0, 0, 0, 0, QPen(QColor("#26293f"), 1.0))
            self.edge_items.append(line_item)

        # Add nodes
        for node in self.engine.nodes.values():
            item = NodeGraphicsItem(node, on_open_file=self.file_open_requested.emit)
            self.scene.addItem(item)
            self.node_items[node.id] = item

        self._sim_steps = 60
        self._sim_timer.start(25)  # 40 fps physics simulation

    def _on_physics_tick(self) -> None:
        if self._sim_steps <= 0:
            self._sim_timer.stop()
            return

        self.engine.step_physics_simulation(iterations=1)
        self._sim_steps -= 1

        # Update node positions in scene
        for node_id, item in self.node_items.items():
            node = self.engine.nodes.get(node_id)
            if node:
                item.setPos(node.x, node.y)

        # Update edge lines
        for idx, edge in enumerate(self.engine.edges):
            n1 = self.engine.nodes.get(edge.source_id)
            n2 = self.engine.nodes.get(edge.target_id)
            if n1 and n2 and idx < len(self.edge_items):
                self.edge_items[idx].setLine(n1.x, n1.y, n2.x, n2.y)

    def _on_search_changed(self, text: str) -> None:
        q = text.lower().strip()
        for node_id, item in self.node_items.items():
            if not q:
                item._highlighted = False
            else:
                item._highlighted = q in item.node.name.lower() or q in item.node.path.lower()
            item.update()
