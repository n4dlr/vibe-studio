"""CanvasEngine — Obsidian-Style Visual Whiteboard & Mindmap Engine.

Supports Obsidian .canvas format with text nodes, file cards, link cards,
and AI-executable reasoning cards.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CanvasNodeType(str, Enum):
    TEXT   = "text"
    FILE   = "file"
    LINK   = "link"
    AI_CARD= "ai_card"


@dataclass
class CanvasNode:
    id: str
    node_type: CanvasNodeType
    x: float
    y: float
    width: float = 240.0
    height: float = 160.0
    text: str = ""
    file: str = ""
    url: str = ""
    color: str = "#6366f1"


@dataclass
class CanvasEdge:
    id: str
    from_node: str
    to_node: str
    from_side: str = "right"
    to_side: str = "left"
    label: str = ""
    color: str = "#4f46e5"


class CanvasDocument:
    """Manages an Obsidian-compatible .canvas file."""

    def __init__(self, path: Optional[str | Path] = None):
        self.path = Path(path) if path else None
        self.nodes: dict[str, CanvasNode] = {}
        self.edges: dict[str, CanvasEdge] = {}

    def add_text_node(self, node_id: str, text: str, x: float, y: float, width: float = 240.0, height: float = 160.0, color: str = "#6366f1") -> CanvasNode:
        node = CanvasNode(id=node_id, node_type=CanvasNodeType.TEXT, x=x, y=y, width=width, height=height, text=text, color=color)
        self.nodes[node_id] = node
        return node

    def add_file_node(self, node_id: str, file_path: str, x: float, y: float, width: float = 260.0, height: float = 180.0) -> CanvasNode:
        node = CanvasNode(id=node_id, node_type=CanvasNodeType.FILE, x=x, y=y, width=width, height=height, file=file_path, color="#38bdf8")
        self.nodes[node_id] = node
        return node

    def add_edge(self, edge_id: str, from_node: str, to_node: str, label: str = "") -> CanvasEdge:
        edge = CanvasEdge(id=edge_id, from_node=from_node, to_node=to_node, label=label)
        self.edges[edge_id] = edge
        return edge

    def to_json(self) -> str:
        data = {
            "nodes": [
                {
                    "id": n.id,
                    "type": n.node_type.value,
                    "x": n.x,
                    "y": n.y,
                    "width": n.width,
                    "height": n.height,
                    "text": n.text,
                    "file": n.file,
                    "color": n.color,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "id": e.id,
                    "fromNode": e.from_node,
                    "fromSide": e.from_side,
                    "toNode": e.to_node,
                    "toSide": e.to_side,
                    "label": e.label,
                    "color": e.color,
                }
                for e in self.edges.values()
            ],
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, json_str: str, path: Optional[str | Path] = None) -> CanvasDocument:
        doc = cls(path=path)
        data = json.loads(json_str)
        for nd in data.get("nodes", []):
            node = CanvasNode(
                id=nd["id"],
                node_type=CanvasNodeType(nd.get("type", "text")),
                x=float(nd.get("x", 0)),
                y=float(nd.get("y", 0)),
                width=float(nd.get("width", 240)),
                height=float(nd.get("height", 160)),
                text=nd.get("text", ""),
                file=nd.get("file", ""),
                color=nd.get("color", "#6366f1"),
            )
            doc.nodes[node.id] = node
        for ed in data.get("edges", []):
            edge = CanvasEdge(
                id=ed["id"],
                from_node=ed["fromNode"],
                from_side=ed.get("fromSide", "right"),
                to_node=ed["toNode"],
                to_side=ed.get("toSide", "left"),
                label=ed.get("label", ""),
                color=ed.get("color", "#4f46e5"),
            )
            doc.edges[edge.id] = edge
        return doc
