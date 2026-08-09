"""Monorepo Stress Test — performance and scaling benchmark for Graph RAG and Parallel Builder."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.context.graph_rag import CodeGraph, _HAS_NX
from vibe_studio.context.parallel_graph_builder import ParallelGraphBuilder
from vibe_studio.context.context_engine import ContextEngine


class TestMonorepoStress:
    @pytest.fixture
    def synthetic_monorepo(self, tmp_path):
        """Generate a synthetic monorepo with 500 Python files and call relationships."""
        repo = tmp_path / "synthetic_monorepo"
        repo.mkdir()

        for i in range(500):
            pkg = repo / f"package_{i % 10}"
            pkg.mkdir(exist_ok=True)
            f = pkg / f"module_{i}.py"
            next_mod = (i + 1) % 500
            f.write_text(
                f"def func_{i}():\n"
                f"    '''Module {i} implementation.'''\n"
                f"    return func_{next_mod}()\n"
            )
        return repo

    def test_parallel_graph_builder_stress(self, synthetic_monorepo):
        if not _HAS_NX:
            pytest.skip("networkx not installed")

        t0 = time.monotonic()
        builder = ParallelGraphBuilder(synthetic_monorepo, max_workers=4)
        cg = builder.build(max_files=500)
        dur = time.monotonic() - t0

        assert cg.available
        assert len(cg.symbol_file_map) > 0
        # Benchmark should complete under 10 seconds for 500 files
        assert dur < 10.0

    def test_context_engine_large_monorepo(self, synthetic_monorepo):
        ce = ContextEngine(synthetic_monorepo, graph_expand=False)
        t0 = time.monotonic()
        bundle = ce.build(prompt="func_42 func_100", token_budget=16000)
        dur = time.monotonic() - t0

        assert len(bundle.items) > 0
        assert bundle.total_tokens_est <= 16000
        assert dur < 5.0
