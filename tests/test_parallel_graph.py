"""Tests for ParallelGraphBuilder."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.context.parallel_graph_builder import ParallelGraphBuilder
from vibe_studio.context.graph_rag import CodeGraph, _HAS_NX


class TestParallelGraphBuilder:
    def test_build_empty_dir(self, tmp_path):
        builder = ParallelGraphBuilder(tmp_path)
        cg = builder.build()
        assert isinstance(cg, CodeGraph)

    def test_build_small_repo(self, tmp_path):
        (tmp_path / "a.py").write_text("class A:\n    def foo(self): pass\n")
        (tmp_path / "b.py").write_text("class B(A):\n    def bar(self): pass\n")

        builder = ParallelGraphBuilder(tmp_path, max_workers=2)
        cg = builder.build()

        if _HAS_NX:
            assert cg.available
        else:
            assert not cg.available
