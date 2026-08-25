"""Obsidian-Grade Knowledge & Code Physics Graph Engine.

Constructs an interactive 2D dependency graph of code ASTs, classes, functions,
imports, Obsidian [[WikiLinks]], and Architecture Decision Records (ADRs).
Features Coulomb-Hooke physics layout, PageRank centrality, and cross-file navigation.
"""
from __future__ import annotations

import ast
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class NodeType(str, Enum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    MODULE = "module"
    DOC = "doc"
    ADR = "adr"
    CONCEPT = "concept"


class EdgeType(str, Enum):
    IMPORTS = "imports"
    DEFINES = "defines"
    INHERITS = "inherits"
    CALLS = "calls"
    WIKILINK = "wikilink"
    DEPENDS_ON = "depends_on"


@dataclass
class GraphNode:
    id: str
    name: str
    node_type: NodeType
    path: str
    line_number: int = 1
    degree: int = 0
    centrality: float = 0.0
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["node_type"] = self.node_type.value
        return d


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
        }


class KnowledgeGraphEngine:
    """AST & Markdown Graph Indexer with Coulomb-Hooke Physics and PageRank."""

    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._adj: dict[str, set[str]] = {}

    def scan_workspace(self, max_files: int = 500) -> None:
        """Scan workspace and construct full AST & WikiLink knowledge graph."""
        return self.index_workspace(max_files=max_files)

    def index_workspace(self, max_files: int = 500) -> None:
        """Scan workspace and construct full AST & WikiLink knowledge graph."""

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
                elif p.suffix in (".js", ".jsx", ".ts", ".tsx"):
                    self._index_javascript_typescript_file(p, rel_path)
                    files_scanned += 1
                elif p.suffix == ".go":
                    self._index_golang_file(p, rel_path)
                    files_scanned += 1
                elif p.suffix == ".rs":
                    self._index_rust_file(p, rel_path)
                    files_scanned += 1
                elif p.suffix in (".md", ".markdown"):
                    self._index_markdown_file(p, rel_path)
                    files_scanned += 1
                elif p.suffix in (".json", ".toml", ".yaml", ".yml"):
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

    def _index_javascript_typescript_file(self, path: Path, rel_path: str) -> None:
        """Extract classes, functions, interfaces, and imports from JS/TS files."""
        file_id = f"file:{rel_path}"
        self._add_node(GraphNode(
            id=file_id,
            name=path.name,
            node_type=NodeType.FILE,
            path=rel_path,
            line_number=1,
            metadata={"extension": path.suffix, "size": path.stat().st_size},
        ))

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        # 1. Extract Imports
        for imp in re.finditer(r"(?:import\s+.*?from\s+['\"](.*?)['\"]|require\(['\"](.*?)['\"]\))", content):
            mod_name = imp.group(1) or imp.group(2)
            if mod_name:
                self._add_edge(file_id, f"mod:{mod_name}", EdgeType.IMPORTS)

        # 2. Extract Classes & Interfaces
        for cls in re.finditer(r"(?:export\s+)?(?:class|interface)\s+([A-Za-z0-9_]+)", content):
            cls_name = cls.group(1)
            cls_id = f"class:{rel_path}:{cls_name}"
            line_no = content[:cls.start()].count("\n") + 1
            self._add_node(GraphNode(id=cls_id, name=cls_name, node_type=NodeType.CLASS, path=rel_path, line_number=line_no))
            self._add_edge(file_id, cls_id, EdgeType.DEFINES)

        # 3. Extract Functions
        for fn in re.finditer(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)|(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", content):
            fn_name = fn.group(1) or fn.group(2)
            if fn_name:
                fn_id = f"fn:{rel_path}:{fn_name}"
                line_no = content[:fn.start()].count("\n") + 1
                self._add_node(GraphNode(id=fn_id, name=fn_name, node_type=NodeType.FUNCTION, path=rel_path, line_number=line_no))
                self._add_edge(file_id, fn_id, EdgeType.DEFINES)

    def _index_golang_file(self, path: Path, rel_path: str) -> None:
        """Extract packages, structs, interfaces, and functions from Go files."""
        file_id = f"file:{rel_path}"
        self._add_node(GraphNode(
            id=file_id,
            name=path.name,
            node_type=NodeType.FILE,
            path=rel_path,
            line_number=1,
            metadata={"extension": ".go", "size": path.stat().st_size},
        ))

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        # 1. Imports
        for imp in re.finditer(r"import\s*\((.*?)\)|import\s+\"([^\"]+)\"", content, re.DOTALL):
            if imp.group(2):
                self._add_edge(file_id, f"mod:{imp.group(2)}", EdgeType.IMPORTS)
            elif imp.group(1):
                for single_imp in re.findall(r"\"([^\"]+)\"", imp.group(1)):
                    self._add_edge(file_id, f"mod:{single_imp}", EdgeType.IMPORTS)

        # 2. Structs / Types
        for st in re.finditer(r"type\s+([A-Za-z0-9_]+)\s+(?:struct|interface)", content):
            st_name = st.group(1)
            cls_id = f"class:{rel_path}:{st_name}"
            line_no = content[:st.start()].count("\n") + 1
            self._add_node(GraphNode(id=cls_id, name=st_name, node_type=NodeType.CLASS, path=rel_path, line_number=line_no))
            self._add_edge(file_id, cls_id, EdgeType.DEFINES)

        # 3. Functions & Methods
        for fn in re.finditer(r"func\s+(?:\([^)]+\)\s+)?([A-Za-z0-9_]+)\s*\(", content):
            fn_name = fn.group(1)
            fn_id = f"fn:{rel_path}:{fn_name}"
            line_no = content[:fn.start()].count("\n") + 1
            self._add_node(GraphNode(id=fn_id, name=fn_name, node_type=NodeType.FUNCTION, path=rel_path, line_number=line_no))
            self._add_edge(file_id, fn_id, EdgeType.DEFINES)

    def _index_rust_file(self, path: Path, rel_path: str) -> None:
        """Extract structs, enums, traits, and functions from Rust files."""
        file_id = f"file:{rel_path}"
        self._add_node(GraphNode(
            id=file_id,
            name=path.name,
            node_type=NodeType.FILE,
            path=rel_path,
            line_number=1,
            metadata={"extension": ".rs", "size": path.stat().st_size},
        ))

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        # 1. Use / Imports
        for imp in re.finditer(r"use\s+([^;]+);", content):
            mod_name = imp.group(1).strip()
            self._add_edge(file_id, f"mod:{mod_name}", EdgeType.IMPORTS)

        # 2. Structs & Traits
        for st in re.finditer(r"(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z0-9_]+)", content):
            st_name = st.group(1)
            cls_id = f"class:{rel_path}:{st_name}"
            line_no = content[:st.start()].count("\n") + 1
            self._add_node(GraphNode(id=cls_id, name=st_name, node_type=NodeType.CLASS, path=rel_path, line_number=line_no))
            self._add_edge(file_id, cls_id, EdgeType.DEFINES)

        # 3. Functions
        for fn in re.finditer(r"(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z0-9_]+)\s*(?:<[^>]+>)?\s*\(", content):
            fn_name = fn.group(1)
            fn_id = f"fn:{rel_path}:{fn_name}"
            line_no = content[:fn.start()].count("\n") + 1
            self._add_node(GraphNode(id=fn_id, name=fn_name, node_type=NodeType.FUNCTION, path=rel_path, line_number=line_no))
            self._add_edge(file_id, fn_id, EdgeType.DEFINES)

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
            target_id = f"doc:{clean_link}" if not clean_link.endswith((".py", ".ts", ".js", ".go", ".rs")) else f"file:{clean_link}"
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

    def _compute_centrality(self, damping: float = 0.85, max_iter: int = 50, tol: float = 1e-6) -> None:
        """Compute both Degree Centrality and true iterative PageRank."""
        total_nodes = len(self.nodes)
        if total_nodes == 0:
            return

        # 1. Degree Centrality
        for node_id, node in self.nodes.items():
            deg = len(self._adj.get(node_id, set()))
            node.degree = deg

        # 2. True PageRank (Power Iteration)
        out_degree = {nid: len(self._adj.get(nid, set())) for nid in self.nodes}
        rank = {nid: 1.0 / total_nodes for nid in self.nodes}

        for _ in range(max_iter):
            new_rank = {}
            sink_sum = sum(rank[nid] for nid in self.nodes if out_degree[nid] == 0)
            for nid in self.nodes:
                in_sum = 0.0
                for neighbor_id in self._adj.get(nid, set()):
                    if out_degree[neighbor_id] > 0:
                        in_sum += rank[neighbor_id] / out_degree[neighbor_id]
                new_rank[nid] = (1.0 - damping) / total_nodes + damping * (in_sum + sink_sum / total_nodes)

            err = sum(abs(new_rank[nid] - rank[nid]) for nid in self.nodes)
            rank = new_rank
            if err < tol:
                break

        max_rank = max(rank.values()) if rank else 1.0
        for nid, node in self.nodes.items():
            node.centrality = rank.get(nid, 0.0) / max(1e-9, max_rank)

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

    def to_json(self) -> str:
        """Export graph to JSON for web/visualization."""
        return json.dumps({
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }, indent=2)
