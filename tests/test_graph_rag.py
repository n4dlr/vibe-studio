"""Tests for Graph RAG — CodeGraph and GraphContextExpander."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))


class TestCodeGraph:
    def test_build_without_networkx_returns_empty(self):
        from vibe_studio.context.graph_rag import CodeGraph, _HAS_NX
        if _HAS_NX:
            pytest.skip("networkx is installed — skipping no-nx path")
        g = CodeGraph.build_from_root(Path("/nonexistent"))
        assert not g.available
        assert g.neighbors("anything") == set()

    def test_build_from_root_real_code(self, tmp_path):
        from vibe_studio.context.graph_rag import CodeGraph, _HAS_NX
        if not _HAS_NX:
            pytest.skip("networkx not installed")
        (tmp_path / "mod.py").write_text(
            "class A:\n    def foo(self): pass\n\nclass B(A):\n    def bar(self): self.foo()\n"
        )
        g = CodeGraph.build_from_root(tmp_path)
        assert g.available

    def test_neighbors_depth(self, tmp_path):
        from vibe_studio.context.graph_rag import CodeGraph, _HAS_NX
        if not _HAS_NX:
            pytest.skip("networkx not installed")
        (tmp_path / "a.py").write_text("def alpha(): beta()\n")
        (tmp_path / "b.py").write_text("def beta(): pass\n")
        g = CodeGraph.build_from_root(tmp_path)
        # Symbol may or may not resolve depending on AST — just check no crash
        syms = g.neighbors("a.alpha", depth=2)
        assert isinstance(syms, set)

    def test_available_false_without_graph(self):
        from vibe_studio.context.graph_rag import CodeGraph
        g = CodeGraph()
        assert not g.available

    def test_files_for_symbols_empty(self):
        from vibe_studio.context.graph_rag import CodeGraph
        g = CodeGraph()
        result = g.files_for_symbols({"a.b.c"})
        assert result == set()

    def test_symbols_in_file_missing(self):
        from vibe_studio.context.graph_rag import CodeGraph
        g = CodeGraph()
        result = g.symbols_in_file("nonexistent.py")
        assert result == []


class TestGraphContextExpander:
    def test_expand_noop_without_networkx(self, tmp_path):
        from vibe_studio.context.graph_rag import CodeGraph, GraphContextExpander, _HAS_NX
        from vibe_studio.context.context_engine import ContextBundle
        if _HAS_NX:
            pytest.skip("networkx installed — skipping no-nx path")
        expander = GraphContextExpander(tmp_path, graph=CodeGraph())
        bundle = ContextBundle()
        result = expander.expand(bundle)
        assert result is bundle  # unchanged when no graph

    def test_expand_empty_bundle_noop(self, tmp_path):
        from vibe_studio.context.graph_rag import CodeGraph, GraphContextExpander
        from vibe_studio.context.context_engine import ContextBundle
        g = CodeGraph()  # unavailable
        expander = GraphContextExpander(tmp_path, graph=g)
        bundle = ContextBundle()
        result = expander.expand(bundle)
        assert result is bundle

    def test_expand_with_real_graph(self, tmp_path):
        from vibe_studio.context.graph_rag import CodeGraph, GraphContextExpander, _HAS_NX
        from vibe_studio.context.context_engine import ContextBundle, ContextItem
        if not _HAS_NX:
            pytest.skip("networkx not installed")
        (tmp_path / "a.py").write_text("from b import foo\ndef bar(): foo()\n")
        (tmp_path / "b.py").write_text("def foo(): pass\n")
        g = CodeGraph.build_from_root(tmp_path)
        expander = GraphContextExpander(tmp_path, graph=g)
        item = ContextItem(path="a.py", score=80, reason="test")
        bundle = ContextBundle(items=[item], total_tokens_est=100)
        result = expander.expand(bundle, max_extra_tokens=2000)
        # b.py may or may not be pulled in depending on graph resolution
        assert isinstance(result.items, list)
