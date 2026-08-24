"""WorkflowPanel — n8n-Style Interactive Visual Node Canvas & Automation Studio.

Draggable node cards with glowing connection cables, live execution playback,
parameter inspector, and workflow template presets.
"""
from __future__ import annotations

import json
from typing import Optional

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
    QComboBox,
    QFrame,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from vibe_studio.workflow.engine import NodeExecutionStatus, NodeKind, WorkflowEdge, WorkflowNode, WorkflowPipeline

# Theme Constants
_BG_DEEP    = "#0c0d14"
_BG_PANEL   = "#161724"
_BG_RAISED  = "#1d1f30"
_BORDER     = "#26293f"
_TEXT       = "#f1f3f9"
_TEXT_MUTED = "#9ea4be"
_ACCENT     = "#6366f1"
_SUCCESS    = "#34d399"
_DANGER     = "#f87171"
_WARNING    = "#fbbf24"

NODE_KIND_ICONS = {
    NodeKind.MANUAL_TRIGGER:      "⚡ Trigger",
    NodeKind.CRON_TRIGGER:        "⏰ Cron",
    NodeKind.FILE_WATCH_TRIGGER:  "👁 Watcher",
    NodeKind.GIT_HOOK_TRIGGER:    "⎇ Git",
    NodeKind.SUPER_AGENT_ACTION:  "🤖 SuperAgent",
    NodeKind.PLAYWRIGHT_ACTION:   "🌐 Browser",
    NodeKind.PYTHON_SCRIPT:       "🐍 Python",
    NodeKind.SHELL_COMMAND:       "⬛ Shell",
    NodeKind.CONDITION_BRANCH:    "🔀 If / Else",
    NodeKind.NOTIFICATION_ACTION: "🔔 Notify",
}


class NodeCardItem(QGraphicsItem):
    """Draggable visual card representing a workflow step."""

    def __init__(self, node: WorkflowNode, on_select_cb=None):
        super().__init__()
        self.node = node
        self.on_select_cb = on_select_cb
        self.setPos(node.x, node.y)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.width = 180
        self.height = 75

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)

        # Status border color
        if self.node.status == NodeExecutionStatus.RUNNING:
            border_color = QColor(_WARNING)
            glow = True
        elif self.node.status == NodeExecutionStatus.SUCCESS:
            border_color = QColor(_SUCCESS)
            glow = False
        elif self.node.status == NodeExecutionStatus.FAILED:
            border_color = QColor(_DANGER)
            glow = True
        elif self.isSelected():
            border_color = QColor(_ACCENT)
            glow = True
        else:
            border_color = QColor(_BORDER)
            glow = False

        # Card Background
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 8, 8)

        if glow:
            glow_pen = QPen(border_color, 4)
            glow_pen.setColor(QColor(border_color.red(), border_color.green(), border_color.blue(), 100))
            painter.strokePath(path, glow_pen)

        painter.fillPath(path, QBrush(QColor(_BG_RAISED)))
        painter.strokePath(path, QPen(border_color, 1.5))

        # Title bar
        title_path = QPainterPath()
        title_path.addRoundedRect(0, 0, self.width, 24, 8, 8)
        painter.fillPath(title_path, QBrush(QColor(_BG_PANEL)))

        # Header Text
        icon_title = NODE_KIND_ICONS.get(self.node.kind, self.node.name)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Inter", 8, QFont.Bold))
        painter.drawText(8, 16, icon_title)

        # Node Name & Status
        painter.setPen(QColor(_TEXT_MUTED))
        painter.setFont(QFont("Inter", 8))
        painter.drawText(8, 42, self.node.name[:22])

        status_str = f"● {self.node.status.value}"
        if self.node.duration > 0:
            status_str += f" ({self.node.duration}s)"
        painter.setPen(border_color)
        painter.drawText(8, 60, status_str)

        # Ports: Input (left), Output (right)
        painter.setBrush(QBrush(QColor(_ACCENT)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, self.height / 2), 4, 4)
        painter.drawEllipse(QPointF(self.width, self.height / 2), 4, 4)

    def mousePressEvent(self, event):
        if self.on_select_cb:
            self.on_select_cb(self.node)
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.node.x = self.x()
            self.node.y = self.y()
        return super().itemChange(change, value)


class ConnectionCableItem(QGraphicsPathItem):
    """Curved bezier wire connecting two workflow nodes."""

    def __init__(self, source_card: NodeCardItem, target_card: NodeCardItem):
        super().__init__()
        self.source_card = source_card
        self.target_card = target_card
        self.setPen(QPen(QColor(_ACCENT), 2.0))
        self.setZValue(-1)
        self.update_path()

    def update_path(self) -> None:
        p1 = QPointF(self.source_card.x() + self.source_card.width, self.source_card.y() + self.source_card.height / 2)
        p2 = QPointF(self.target_card.x(), self.target_card.y() + self.target_card.height / 2)

        path = QPainterPath(p1)
        dx = max(40.0, abs(p2.x() - p1.x()) * 0.5)
        c1 = QPointF(p1.x() + dx, p1.y())
        c2 = QPointF(p2.x() - dx, p2.y())
        path.cubicTo(c1, c2, p2)
        self.setPath(path)


class WorkflowPanel(QWidget):
    """Complete n8n-Style Workflow Automation Studio."""

    def __init__(self, workspace_root: str = ".", parent=None):
        super().__init__(parent)
        self.workspace_root = workspace_root
        self.pipeline = WorkflowPipeline("CI/CD Auto-Heal Pipeline", workspace_root)
        self.scene = QGraphicsScene(self)
        self.cards: dict[str, NodeCardItem] = {}
        self.cables: list[ConnectionCableItem] = []
        self._selected_node: Optional[WorkflowNode] = None

        self._setup_default_workflow()
        self._setup_ui()

    def _setup_default_workflow(self) -> None:
        """Create a default robust workflow: Trigger -> SuperAgent -> Browser Verify -> Notify."""
        n1 = WorkflowNode(id="n1", name="On Push Trigger", kind=NodeKind.MANUAL_TRIGGER, x=40, y=100)
        n2 = WorkflowNode(id="n2", name="SuperAgent Audit", kind=NodeKind.SUPER_AGENT_ACTION, params={"prompt": "Verify codebase integrity and run tests"}, x=280, y=100)
        n3 = WorkflowNode(id="n3", name="Playwright Check", kind=NodeKind.PLAYWRIGHT_ACTION, params={"url": "http://127.0.0.1:8000"}, x=520, y=100)
        n4 = WorkflowNode(id="n4", name="Notify Status", kind=NodeKind.NOTIFICATION_ACTION, params={"message": "All pipeline checks passed"}, x=760, y=100)

        self.pipeline.add_node(n1)
        self.pipeline.add_node(n2)
        self.pipeline.add_node(n3)
        self.pipeline.add_node(n4)

        self.pipeline.add_edge("n1", "n2")
        self.pipeline.add_edge("n2", "n3")
        self.pipeline.add_edge("n3", "n4")

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Control Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet(f"QFrame {{ background: {_BG_RAISED}; border: 1px solid {_BORDER}; border-radius: 8px; padding: 4px; }}")
        tb_l = QHBoxLayout(toolbar)
        tb_l.setContentsMargins(4, 2, 4, 2)
        tb_l.setSpacing(6)

        title = QLabel("⚡ Visual Automation Studio (n8n Engine)")
        title.setFont(QFont("Inter", 11, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        tb_l.addWidget(title)

        tb_l.addStretch()

        # Add Node dropdown
        self.add_kind_combo = QComboBox()
        for k in NodeKind:
            self.add_kind_combo.addItem(NODE_KIND_ICONS.get(k, k.value), k.value)
        self.add_kind_combo.setStyleSheet(f"background: {_BG_PANEL}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 3px;")
        tb_l.addWidget(self.add_kind_combo)

        add_btn = QPushButton("+ Add Node")
        add_btn.setStyleSheet(f"background: {_BG_PANEL}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 3px 8px; font-weight: bold;")
        add_btn.clicked.connect(self._on_add_node)
        tb_l.addWidget(add_btn)

        run_btn = QPushButton("▶ Run Workflow")
        run_btn.setStyleSheet(f"background: {_ACCENT}; color: #ffffff; border: none; border-radius: 4px; padding: 4px 14px; font-weight: bold;")
        run_btn.clicked.connect(self.execute_workflow)
        tb_l.addWidget(run_btn)

        main_layout.addWidget(toolbar)

        # Splitter: Canvas (left) + Node Inspector (right)
        splitter = QSplitter(Qt.Horizontal)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setBackgroundBrush(QBrush(QColor(_BG_DEEP)))
        splitter.addWidget(self.view)

        # Inspector Panel
        self.inspector = self._create_inspector_panel()
        self.inspector.setFixedWidth(260)
        splitter.addWidget(self.inspector)

        main_layout.addWidget(splitter, 1)

        self._render_graph()

        # Redraw timer for dragging cables
        self.cable_timer = QTimer(self)
        self.cable_timer.timeout.connect(self._update_cables)
        self.cable_timer.start(30)

    def _create_inspector_panel(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"QFrame {{ background: {_BG_PANEL}; border: 1px solid {_BORDER}; border-radius: 8px; }}")
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        l.setSpacing(6)

        hdr = QLabel("⚙️ Node Inspector")
        hdr.setFont(QFont("Inter", 10, QFont.Bold))
        hdr.setStyleSheet("color: #ffffff;")
        l.addWidget(hdr)

        self.ins_name = QLineEdit()
        self.ins_name.setPlaceholderText("Node Name")
        self.ins_name.setStyleSheet(f"background: {_BG_RAISED}; color: {_TEXT}; border: 1px solid {_BORDER}; border-radius: 4px; padding: 4px;")
        self.ins_name.textChanged.connect(self._on_inspector_name_changed)
        l.addWidget(self.ins_name)

        l.addWidget(QLabel("Parameters / Code:"))
        self.ins_params = QPlainTextEdit()
        self.ins_params.setPlaceholderText("JSON parameters or Python code...")
        self.ins_params.setStyleSheet(f"background: {_BG_RAISED}; color: {_TEXT}; font-family: monospace; border: 1px solid {_BORDER}; border-radius: 4px; padding: 4px;")
        self.ins_params.textChanged.connect(self._on_inspector_params_changed)
        l.addWidget(self.ins_params, 1)

        l.addWidget(QLabel("Output / Result:"))
        self.ins_output = QPlainTextEdit()
        self.ins_output.setReadOnly(True)
        self.ins_output.setStyleSheet(f"background: {_BG_DEEP}; color: {_SUCCESS}; font-family: monospace; border: 1px solid {_BORDER}; border-radius: 4px; padding: 4px;")
        l.addWidget(self.ins_output, 1)

        return w

    def _render_graph(self) -> None:
        self.scene.clear()
        self.cards.clear()
        self.cables.clear()

        for node in self.pipeline.nodes.values():
            card = NodeCardItem(node, on_select_cb=self._on_node_selected)
            self.scene.addItem(card)
            self.cards[node.id] = card

        for edge in self.pipeline.edges:
            src = self.cards.get(edge.source_id)
            tgt = self.cards.get(edge.target_id)
            if src and tgt:
                cable = ConnectionCableItem(src, tgt)
                self.scene.addItem(cable)
                self.cables.append(cable)

    def _update_cables(self) -> None:
        for cable in self.cables:
            cable.update_path()

    def _on_node_selected(self, node: WorkflowNode) -> None:
        self._selected_node = node
        self.ins_name.setText(node.name)
        self.ins_params.setPlainText(json.dumps(node.params, indent=2) if node.params else "")
        self.ins_output.setPlainText(str(node.last_output or node.error or "No output yet"))

    def _on_inspector_name_changed(self, text: str) -> None:
        if self._selected_node:
            self._selected_node.name = text
            card = self.cards.get(self._selected_node.id)
            if card:
                card.update()

    def _on_inspector_params_changed(self) -> None:
        if self._selected_node:
            try:
                self._selected_node.params = json.loads(self.ins_params.toPlainText())
            except Exception:
                pass

    def _on_add_node(self) -> None:
        kind_str = self.add_kind_combo.currentData()
        kind = NodeKind(kind_str)
        import uuid
        nid = f"n_{uuid.uuid4().hex[:6]}"
        node = WorkflowNode(id=nid, name=f"New {kind.value}", kind=kind, x=100, y=100)
        self.pipeline.add_node(node)
        self._render_graph()

    def execute_workflow(self) -> None:
        """Run the workflow graph and animate step updates."""
        def _on_progress(nid: str, status: NodeExecutionStatus):
            card = self.cards.get(nid)
            if card:
                card.update()
            if self._selected_node and self._selected_node.id == nid:
                self._on_node_selected(self._selected_node)

        res = self.pipeline.execute(progress_callback=_on_progress)
        self._update_cables()
        self.view.update()
