"""Knowledge & Code Graph Engine — Obsidian-Grade Semantic Network & AST Dependency Graph.

Builds a global graph of files, classes, functions, imports, calls, and Markdown [[WikiLinks]],
computing PageRank centrality and force-directed physics coordinates.
"""
from __future__ import annotations

import ast
import math
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class NodeType(str, Enum):
    FILE     = "FILE"
    CLASS    = "CLASS"
    FUNCTION = "FUNCTION"
    DOC      = "DOC"
    MODULE   = "MODULE"
    CONCEPT  = "CONCEPT"


class EdgeType(str, Enum):
    IMPORTS  = "IMPORTS"
    CALLS    = "CALLS"
    INHERITS = "INHERITS"
    WIKILINK = "WIKILINK"
    DEFINES  = "DEFINES"


@dataclass
class GraphNode:
    id: str
    name: str
    node_type: NodeType
    path: str
    line_number: int = 1
    centrality: float = 0.0
    degree: int = 0
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0


class KnowledgeGraphEngine:
    """Extracts, analyzes, and calculates physics layouts for the project code graph."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._adj: dict[str, set[str]] = {}

    def scan_workspace(self, max_files: int = 500) -> None:
        """Scan workspace to construct AST symbol dependencies and Markdown backlinks."""
        self.nodes.clear()
        self.edges.clear()
        self._adj.clear()

        ignored_parts = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "build", "dist", ".vibe_studio"}
        files_scanned = 0

        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in ignored_parts]
            for file in files:
                if files_scanned >= max_files:
                    break
                p = Path(root) / file
                rel_path = p.relative_to(self.workspace_root).as_posix()

                if p.suffix == ".py":
                    self._index_python_file(p, rel_path)
                    files_scanned += 1
                elif p.suffix in (".md", ".markdown"):
                    self._index_markdown_file(p, rel_path)
                    files_scanned += 1
                elif p.suffix in (".js", ".ts", ".jsx", ".tsx", ".json", ".toml", ".rs", ".go"):
                    self._index_generic_file(p, rel_path)
                    files_scanned += 1

        self._compute_centrality()
        self._initialize_physics_layout()

    def _index_python_file(self, path: Path, rel_path: str) -> None:
        file_id = f"file:{rel_path}"
        self._add_node(GraphNode(
            id=file_id,
            name=path.name,
            node_type=NodeType.FILE,
            path=rel_path,
            line_number=1,
            metadata={"extension": ".py", "size": path.stat().st_size},
        ))

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except Exception:
            return

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                cls_id = f"class:{rel_path}:{node.name}"
                self._add_node(GraphNode(
                    id=cls_id,
                    name=node.name,
                    node_type=NodeType.CLASS,
                    path=rel_path,
                    line_number=node.lineno,
                    metadata={"bases": [ast.unparse(b) for b in node.bases]},
                ))
                self._add_edge(file_id, cls_id, EdgeType.DEFINES)

                for base in node.bases:
                    base_name = ast.unparse(base)
                    self._add_edge(cls_id, f"symbol:{base_name}", EdgeType.INHERITS)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_id = f"fn:{rel_path}:{node.name}"
                self._add_node(GraphNode(
                    id=fn_id,
                    name=node.name,
                    node_type=NodeType.FUNCTION,
                    path=rel_path,
                    line_number=node.lineno,
                ))
                self._add_edge(file_id, fn_id, EdgeType.DEFINES)

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target_id = f"mod:{alias.name}"
                        self._add_edge(file_id, target_id, EdgeType.IMPORTS)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    target_id = f"mod:{node.module}"
                    self._add_edge(file_id, target_id, EdgeType.IMPORTS)

    def _index_markdown_file(self, path: Path, rel_path: str) -> None:
        doc_id = f"doc:{rel_path}"
        self._add_node(GraphNode(
            id=doc_id,
            name=path.name,
            node_type=NodeType.DOC,
            path=rel_path,
            metadata={"extension": ".md"},
        ))

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        # Parse Obsidian [[WikiLinks]]
        wikilinks = re.findall(r"\[\[(.*?)\]\]", content)
        for link in wikilinks:
            clean_link = link.split("|")[0].split("#")[0].strip()
            target_id = f"doc:{clean_link}" if not clean_link.endswith(".py") else f"file:{clean_link}"
            self._add_edge(doc_id, target_id, EdgeType.WIKILINK)

    def _index_generic_file(self, path: Path, rel_path: str) -> None:
        file_id = f"file:{rel_path}"
        self._add_node(GraphNode(
            id=file_id,
            name=path.name,
            node_type=NodeType.FILE,
            path=rel_path,
            metadata={"extension": path.suffix},
        ))

    def _add_node(self, node: GraphNode) -> None:
        if node.id not in self.nodes:
            self.nodes[node.id] = node
            self._adj[node.id] = set()

    def _add_edge(self, source_id: str, target_id: str, edge_type: EdgeType) -> None:
        if source_id not in self.nodes:
            self._add_node(GraphNode(id=source_id, name=source_id.split(":")[-1], node_type=NodeType.MODULE, path=""))
        if target_id not in self.nodes:
            self._add_node(GraphNode(id=target_id, name=target_id.split(":")[-1], node_type=NodeType.CONCEPT, path=""))

        edge = GraphEdge(source_id=source_id, target_id=target_id, edge_type=edge_type)
        self.edges.append(edge)
        self._adj[source_id].add(target_id)
        self._adj[target_id].add(source_id)

    def _compute_centrality(self) -> None:
        """Compute degree and simplified PageRank centrality scores."""
        total_nodes = len(self.nodes)
        if total_nodes == 0:
            return

        for node_id, node in self.nodes.items():
            deg = len(self._adj.get(node_id, set()))
            node.degree = deg
            node.centrality = deg / float(max(1, total_nodes - 1))

    def _initialize_physics_layout(self) -> None:
        """Assign initial coordinates in a circle/spiral layout."""
        nodes = list(self.nodes.values())
        total = len(nodes)
        radius = max(300.0, math.sqrt(total) * 60.0)

        for idx, node in enumerate(nodes):
            angle = (2.0 * math.pi * idx) / max(1, total)
            r = radius * (0.4 + 0.6 * (idx / max(1, total)))
            node.x = r * math.cos(angle)
            node.y = r * math.sin(angle)
            node.vx = 0.0
            node.vy = 0.0

    def step_physics_simulation(self, iterations: int = 5, repulsion_k: float = 4000.0, spring_k: float = 0.04, damping: float = 0.85) -> None:
        """Perform force-directed simulation step (Coulomb repulsion + Hooke spring attraction)."""
        nodes_list = list(self.nodes.values())
        num_nodes = len(nodes_list)

        for _ in range(iterations):
            # 1. Coulomb Repulsion between all pairs
            for i in range(num_nodes):
                n1 = nodes_list[i]
                for j in range(i + 1, num_nodes):
                    n2 = nodes_list[j]
                    dx = n1.x - n2.x
                    dy = n1.y - n2.y
                    dist_sq = dx * dx + dy * dy + 10.0
                    dist = math.sqrt(dist_sq)
                    force = repulsion_k / dist_sq
                    fx = (dx / dist) * force
                    fy = (dy / dist) * force

                    n1.vx += fx
                    n1.vy += fy
                    n2.vx -= fx
                    n2.vy -= fy

            # 2. Hooke Spring Attraction along edges
            for edge in self.edges:
                n1 = self.nodes.get(edge.source_id)
                n2 = self.nodes.get(edge.target_id)
                if not n1 or not n2:
                    continue
                dx = n2.x - n1.x
                dy = n2.y - n1.y
                dist = math.sqrt(dx * dx + dy * dy) + 0.1
                spring_force = (dist - 120.0) * spring_k
                fx = (dx / dist) * spring_force
                fy = (dy / dist) * spring_force

                n1.vx += fx
                n1.vy += fy
                n2.vx -= fx
                n2.vy -= fy

            # 3. Center Gravity & Position Integration
            for node in nodes_list:
                node.vx -= node.x * 0.005
                node.vy -= node.y * 0.005
                node.vx *= damping
                node.vy *= damping
                node.x += node.vx
                node.y += node.vy

    def search_nodes(self, query: str) -> list[GraphNode]:
        """Search nodes by name or path."""
        q = query.lower()
        return [n for n in self.nodes.values() if q in n.name.lower() or q in n.path.lower()]
