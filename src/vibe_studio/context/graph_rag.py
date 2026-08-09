"""Graph RAG — AST-based code call/inheritance graph for structural context expansion.

Sütun 1 (Graph RAG):
  - CodeGraph  : builds a networkx.DiGraph from all Python files in a project root.
                 Nodes are fully-qualified symbol names (module.ClassName.method_name).
                 Edges represent:
                   • CALLS  : function A calls function/class B
                   • INHERITS: class A extends class B
  - GraphContextExpander: given a ContextBundle, finds graph neighbours of high-score
                 symbols and pulls their source into the bundle, respecting token budget.

Dependencies:
  networkx>=3.3  (optional — graceful fallback to noop if not installed)
"""
from __future__ import annotations

import ast
import logging
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibe_studio.context.context_engine import ContextBundle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional networkx import (graceful degradation)
# ---------------------------------------------------------------------------

try:
    import networkx as nx  # type: ignore[import]
    _HAS_NX = True
except ImportError:
    nx = None  # type: ignore[assignment]
    _HAS_NX = False

_ALWAYS_SKIP_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__", "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".vibe_studio",
}


def _should_skip(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
        return any(p in _ALWAYS_SKIP_DIRS for p in rel_parts)
    except ValueError:
        return True


# ---------------------------------------------------------------------------
# AST visitor — extracts calls and inheritance edges
# ---------------------------------------------------------------------------

class _SymbolVisitor(ast.NodeVisitor):
    """Extract call and inheritance edges from a single Python module."""

    def __init__(self, module_name: str) -> None:
        self.module = module_name
        self.edges: list[tuple[str, str, str]] = []
        self._scope: list[str] = [module_name]

    @property
    def _current_scope(self) -> str:
        return ".".join(self._scope)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_fqn = f"{self._current_scope}.{node.name}"
        for base in node.bases:
            try:
                base_name = ast.unparse(base).strip()
                if base_name and base_name not in {"object"}:
                    self.edges.append((class_fqn, base_name, "INHERITS"))
            except Exception:
                pass
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        try:
            callee = ast.unparse(node.func).strip()
            if callee:
                self.edges.append((self._current_scope, callee, "CALLS"))
        except Exception:
            pass
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# CodeGraph
# ---------------------------------------------------------------------------

@dataclass
class CodeGraph:
    """Directed graph of symbol relationships across a Python project."""

    _graph: object = field(default=None, repr=False)
    symbol_file_map: dict[str, str] = field(default_factory=dict)
    file_symbols_map: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def build_from_root(cls, root: Path, max_files: int = 500) -> "CodeGraph":
        """Parse all Python files under root and build the call/inheritance graph."""
        if not _HAS_NX:
            logger.debug("networkx not available — Graph RAG disabled")
            return cls()

        graph = nx.DiGraph()
        symbol_file: dict[str, str] = {}
        file_syms: dict[str, list[str]] = {}

        py_files = [p for p in root.rglob("*.py") if not _should_skip(p, root)][:max_files]

        for py_file in py_files:
            rel = py_file.relative_to(root).as_posix()
            module_name = rel.replace("/", ".").removesuffix(".py").removesuffix(".__init__")
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(py_file))
            except Exception:
                continue

            visitor = _SymbolVisitor(module_name)
            visitor.visit(tree)

            syms_in_file: list[str] = []
            for src, dst, kind in visitor.edges:
                if not graph.has_node(src):
                    graph.add_node(src)
                    symbol_file[src] = rel
                    syms_in_file.append(src)
                graph.add_edge(src, dst, kind=kind)

            if syms_in_file:
                file_syms[rel] = syms_in_file

        logger.debug(
            "Graph RAG: %d nodes, %d edges from %d files",
            graph.number_of_nodes(), graph.number_of_edges(), len(py_files),
        )
        return cls(_graph=graph, symbol_file_map=symbol_file, file_symbols_map=file_syms)

    def neighbors(self, symbol: str, depth: int = 2) -> set[str]:
        """Return symbols reachable from symbol within depth hops (BFS, bidirectional)."""
        if not _HAS_NX or self._graph is None:
            return set()
        visited: set[str] = set()
        frontier = {symbol}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for node in frontier:
                if node not in visited:
                    visited.add(node)
                    if self._graph.has_node(node):
                        next_frontier.update(self._graph.successors(node))
                        next_frontier.update(self._graph.predecessors(node))
            frontier = next_frontier - visited
        return visited - {symbol}

    def files_for_symbols(self, symbols: set[str]) -> set[str]:
        return {self.symbol_file_map[s] for s in symbols if s in self.symbol_file_map}

    def symbols_in_file(self, rel_path: str) -> list[str]:
        return self.file_symbols_map.get(rel_path, [])

    @property
    def available(self) -> bool:
        return _HAS_NX and self._graph is not None


# ---------------------------------------------------------------------------
# GraphContextExpander
# ---------------------------------------------------------------------------

class GraphContextExpander:
    """Expand a ContextBundle by following graph edges from high-scoring files."""

    def __init__(self, root: Path, graph: CodeGraph | None = None) -> None:
        self.root = root
        self._graph = graph or CodeGraph.build_from_root(root)

    def expand(
        self,
        bundle: "ContextBundle",
        top_n: int = 3,
        graph_depth: int = 2,
        max_extra_tokens: int = 4000,
    ) -> "ContextBundle":
        """Return a new ContextBundle with graph-neighbour files appended."""
        if not self._graph.available:
            return bundle

        from vibe_studio.context.context_engine import ContextItem

        existing_paths = {item.path for item in bundle.items}
        seed_items = bundle.items[:top_n]

        candidate_paths: set[str] = set()
        for item in seed_items:
            syms = self._graph.symbols_in_file(item.path)
            for sym in syms[:20]:
                neighbour_syms = self._graph.neighbors(sym, depth=graph_depth)
                candidate_paths.update(self._graph.files_for_symbols(neighbour_syms))

        candidate_paths -= existing_paths

        added_tokens = 0
        new_items: list[ContextItem] = []

        for rel in sorted(candidate_paths):
            if added_tokens >= max_extra_tokens:
                break
            full_path = self.root / rel
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
                if len(content) > 3000:
                    content = content[:2500] + "\n...[graph-expanded, truncated]..."
                est_tokens = max(1, len(content) // 4)
                if added_tokens + est_tokens > max_extra_tokens:
                    continue
                added_tokens += est_tokens
                new_items.append(ContextItem(
                    path=rel,
                    score=0.0,
                    reason="graph-neighbour",
                    kind="file",
                    content_snippet=content,
                    line_count=content.count("\n"),
                ))
            except Exception:
                continue

        if new_items:
            logger.debug(
                "Graph RAG: expanded bundle by %d files (+%d est tokens)",
                len(new_items), added_tokens,
            )

        expanded = copy(bundle)
        expanded.items = list(bundle.items) + new_items
        expanded.total_tokens_est = bundle.total_tokens_est + added_tokens
        return expanded
