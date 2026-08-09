"""Interactive Visual Code Graph Widget — PySide6 QGraphicsView visualizer.

Pillar 4 (UX - Visual Code Graph):
  Renders AST symbol nodes and call/inheritance edges visually.
  Allows interactive graph navigation and highlights active agent traversal paths.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.context.graph_rag import CodeGraph


class GraphVisualizerWidget(QWidget):
    """Interactive visual representation of the AST CodeGraph."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHints(self.view.renderHints())

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        self.status_label = QLabel("Visual Code Graph: Ready")
        self.status_label.setStyleSheet("font-weight: bold; color: #a78bfa;")
        toolbar.addWidget(self.status_label)
        toolbar.addStretch()

        refresh_btn = QPushButton("Refresh Graph")
        refresh_btn.setFixedHeight(24)
        refresh_btn.clicked.connect(self.refresh_from_workspace)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        layout.addWidget(self.view)

    def load_graph(self, code_graph: CodeGraph, highlighted_symbols: set[str] | None = None) -> None:
        """Render CodeGraph nodes and edges in the scene."""
        self.scene.clear()

        if not code_graph.available or not code_graph.symbol_file_map:
            self.status_label.setText("Visual Code Graph: No symbols indexed")
            txt = self.scene.addText("No AST Code Graph available for this workspace.\nRun indexing or install networkx.")
            txt.setDefaultTextColor(QColor("#94a3b8"))
            return

        highlighted_symbols = highlighted_symbols or set()
        symbols = list(code_graph.symbol_file_map.keys())[:40]  # Limit visible nodes for performance

        node_items: dict[str, QGraphicsItem] = {}

        # Circular layout math
        count = len(symbols)
        radius = max(150.0, count * 15.0)
        center_x, center_y = 300.0, 300.0

        for i, sym in enumerate(symbols):
            angle = (2.0 * math.pi * i) / count
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)

            short_name = sym.split(".")[-1]
            is_highlighted = sym in highlighted_symbols

            bg_color = QColor("#818cf8") if is_highlighted else QColor("#1e293b")
            pen_color = QColor("#fbbf24") if is_highlighted else QColor("#475569")
            text_color = QColor("#ffffff") if is_highlighted else QColor("#cbd5e1")

            rect_item = self.scene.addRect(x, y, 120, 35, QPen(pen_color, 2), QBrush(bg_color))

            text_item = self.scene.addText(short_name[:14])
            text_item.setPos(x + 5, y + 5)
            text_item.setDefaultTextColor(text_color)
            text_item.setFont(QFont("monospace", 9))

            node_items[sym] = rect_item

        self.scene.setSceneRect(0, 0, center_x * 2 + radius, center_y * 2 + radius)
        self.status_label.setText(f"Visual Code Graph: {len(symbols)} nodes rendered")

    def refresh_from_workspace(self, workspace_root: str | Path | None = None) -> None:
        ws = Path(workspace_root or Path.cwd()).resolve()
        cg = CodeGraph.build_from_root(ws)
        self.load_graph(cg)
