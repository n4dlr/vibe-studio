"""Unit test suite for VibeBench benchmark engine."""
import pytest
from vibe_studio.benchmark.scenarios import BENCHMARK_SCENARIOS
from vibe_studio.benchmark.vibe_bench import VibeBenchEngine, VibeBenchReport


def test_vibe_bench_engine_runs_scenarios():
    engine = VibeBenchEngine()
    report = engine.run_benchmark(max_scenarios=2)

    assert isinstance(report, VibeBenchReport)
    assert report.total_tasks == 2
    assert report.success_rate_pct >= 0.0
    assert len(report.results) == 2

    dashboard = report.print_dashboard()
    assert "VIBE BENCH DASHBOARD" in dashboard
    assert "Tasks Evaluated:" in dashboard
