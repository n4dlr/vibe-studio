"""Parallel Graph Builder — Multi-core AST parser for large codebases (100k+ nodes).

Pillar 1 (Performance & Memory Optimization):
  - Uses concurrent.futures.ProcessPoolExecutor to parse Python ASTs across CPU cores.
  - Merges partial edge lists into a unified networkx.DiGraph / CodeGraph.
  - Automatically falls back to single-threaded parsing if CPU count <= 1 or networkx missing.
"""
from __future__ import annotations

import ast
import os
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from vibe_studio.context.graph_rag import CodeGraph, _SymbolVisitor, _should_skip, _HAS_NX

logger = logging.getLogger(__name__)


def _parse_file_worker(args: tuple[str, str]) -> tuple[str, list[tuple[str, str, str]], list[str]]:
    """Worker function executed in separate process.

    args: (file_path_str, root_path_str)
    returns: (rel_path, edges, symbols_in_file)
    """
    file_path_str, root_path_str = args
    py_file = Path(file_path_str)
    root = Path(root_path_str)
    rel = py_file.relative_to(root).as_posix()
    module_name = rel.replace("/", ".").removesuffix(".py").removesuffix(".__init__")

    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except Exception:
        return rel, [], []

    visitor = _SymbolVisitor(module_name)
    visitor.visit(tree)

    syms: list[str] = [src for src, _, _ in visitor.edges]
    return rel, visitor.edges, list(dict.fromkeys(syms))


class ParallelGraphBuilder:
    """Multi-core AST CodeGraph builder for large monorepos."""

    def __init__(self, root: str | Path, max_workers: int | None = None) -> None:
        self.root = Path(root).resolve()
        self.max_workers = max_workers or min(os.cpu_count() or 4, 8)

    def build(self, max_files: int = 50000) -> CodeGraph:
        """Build CodeGraph across CPU cores."""
        if not _HAS_NX:
            logger.debug("networkx not available — ParallelGraphBuilder returning empty CodeGraph")
            return CodeGraph()

        import networkx as nx

        py_files = [p for p in self.root.rglob("*.py") if not _should_skip(p, self.root)][:max_files]
        if not py_files:
            return CodeGraph()

        # For small file counts (< 20), single thread is faster due to IPC overhead
        if len(py_files) < 20 or self.max_workers <= 1:
            return CodeGraph.build_from_root(self.root, max_files=max_files)

        graph = nx.DiGraph()
        symbol_file: dict[str, str] = {}
        file_syms: dict[str, list[str]] = {}

        tasks = [(str(p), str(self.root)) for p in py_files]

        try:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(_parse_file_worker, t) for t in tasks]
                for future in as_completed(futures):
                    try:
                        rel, edges, syms = future.result()
                        if not edges:
                            continue
                        for src, dst, kind in edges:
                            if not graph.has_node(src):
                                graph.add_node(src)
                                symbol_file[src] = rel
                            graph.add_edge(src, dst, kind=kind)
                        if syms:
                            file_syms[rel] = syms
                    except Exception as exc:
                        logger.debug("Worker failed for a file: %s", exc)
        except Exception as exc:
            logger.warning("ProcessPoolExecutor failed (%s), falling back to serial build", exc)
            return CodeGraph.build_from_root(self.root, max_files=max_files)

        logger.info(
            "ParallelGraphBuilder: built graph with %d nodes, %d edges from %d files using %d workers",
            graph.number_of_nodes(), graph.number_of_edges(), len(py_files), self.max_workers,
        )
        return CodeGraph(_graph=graph, symbol_file_map=symbol_file, file_symbols_map=file_syms)
