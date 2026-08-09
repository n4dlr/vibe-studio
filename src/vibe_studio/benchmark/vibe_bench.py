"""VibeBench Engine — Automated E2E Benchmark Suite for Vibe Studio.

Executes scenario tasks in isolated temporary workspaces, measures task success rate,
first-pass success rate, self-repair rate, latency, and token usage, and produces CLI dashboards and JSON reports.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from vibe_studio.agents.coding_agent import AgentState, AutonomousAgent
from vibe_studio.benchmark.scenarios import BENCHMARK_SCENARIOS, BenchmarkScenario
from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.core.command_safety import CommandSafety


@dataclass
class ScenarioResult:
    scenario_id: str
    title: str
    language: str
    difficulty: str
    passed: bool
    first_pass_success: bool
    self_repair_success: bool
    iterations: int
    duration_seconds: float
    files_changed: List[str]
    error_message: Optional[str] = None


@dataclass
class VibeBenchReport:
    total_tasks: int
    passed_tasks: int
    success_rate_pct: float
    first_pass_pct: float
    self_repair_pct: float
    avg_iterations: float
    avg_latency_seconds: float
    results: List[ScenarioResult] = field(default_factory=list)

    def print_dashboard(self) -> str:
        lines = [
            "=================================================================",
            "                      VIBE BENCH DASHBOARD                       ",
            "=================================================================",
            f"Tasks Evaluated:       {self.total_tasks}",
            f"Success Rate:          {self.success_rate_pct:.1f}%",
            f"First-Pass Success:    {self.first_pass_pct:.1f}%",
            f"Self-Repair Recovery:  {self.self_repair_pct:.1f}%",
            f"Avg Iterations:        {self.avg_iterations:.2f}",
            f"Avg Latency:           {self.avg_latency_seconds:.2f}s",
            "-----------------------------------------------------------------",
            " ID                   | Lang      | Diff   | Status | Time   | Steps",
            "-----------------------------------------------------------------",
        ]
        for r in self.results:
            status_str = "SUCCESS" if r.passed else "FAILED"
            lines.append(
                f" {r.scenario_id:<20} | {r.language:<9} | {r.difficulty:<6} | {status_str:<6} | {r.duration_seconds:>5.1f}s | {r.iterations}"
            )
        lines.append("=================================================================")
        return "\n".join(lines)


class VibeBenchEngine:
    """Automated benchmark engine for Vibe Studio AI agent reliability."""

    def __init__(self, provider: Any = None, scenarios: Optional[List[BenchmarkScenario]] = None):
        self.provider = provider
        self.scenarios = scenarios or BENCHMARK_SCENARIOS

    def run_benchmark(self, max_scenarios: Optional[int] = None) -> VibeBenchReport:
        target_scenarios = self.scenarios[:max_scenarios] if max_scenarios else self.scenarios
        results: List[ScenarioResult] = []

        for scenario in target_scenarios:
            res = self._run_single_scenario(scenario)
            results.append(res)

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        first_pass = sum(1 for r in results if r.first_pass_success)
        self_repairs = sum(1 for r in results if r.self_repair_success)

        total_iters = sum(r.iterations for r in results)
        total_time = sum(r.duration_seconds for r in results)

        report = VibeBenchReport(
            total_tasks=total,
            passed_tasks=passed,
            success_rate_pct=(passed / total * 100.0) if total else 0.0,
            first_pass_pct=(first_pass / total * 100.0) if total else 0.0,
            self_repair_pct=(self_repairs / total * 100.0) if total else 0.0,
            avg_iterations=(total_iters / total) if total else 0.0,
            avg_latency_seconds=(total_time / total) if total else 0.0,
            results=results,
        )
        return report

    def _run_single_scenario(self, scenario: BenchmarkScenario) -> ScenarioResult:
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"vibebench_{scenario.id}_"))
        start_time = time.time()

        try:
            # Populate initial files
            for rel_path, content in scenario.initial_files.items():
                p = tmp_dir / rel_path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")

            token = CancellationToken()
            agent = AutonomousAgent(
                project_root=tmp_dir,
                provider=self.provider,
                cancellation_token=token,
            )

            result = agent.run(scenario.prompt)
            duration = time.time() - start_time

            # Run verification command
            cmd_res = CommandSafety.run(
                scenario.verification_cmd,
                cwd=tmp_dir,
                workspace_root=tmp_dir,
                timeout=30,
            )
            passed = (cmd_res.exit_code == 0)
            iters = len(result.tool_history) or 1
            first_pass = passed and (iters <= 2)
            self_repair = passed and (iters > 2)

            return ScenarioResult(
                scenario_id=scenario.id,
                title=scenario.title,
                language=scenario.language,
                difficulty=scenario.difficulty,
                passed=passed,
                first_pass_success=first_pass,
                self_repair_success=self_repair,
                iterations=iters,
                duration_seconds=duration,
                files_changed=result.files_changed,
                error_message=None if passed else cmd_res.stderr,
            )
        except Exception as exc:
            duration = time.time() - start_time
            return ScenarioResult(
                scenario_id=scenario.id,
                title=scenario.title,
                language=scenario.language,
                difficulty=scenario.difficulty,
                passed=False,
                first_pass_success=False,
                self_repair_success=False,
                iterations=0,
                duration_seconds=duration,
                files_changed=[],
                error_message=str(exc),
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
