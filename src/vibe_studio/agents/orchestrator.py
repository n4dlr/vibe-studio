"""AgentOrchestrator — unifies specialized sub-agents into a single autonomous pipeline.

Pipeline Flow:
User Prompt -> Intent -> Navigator -> Context -> Coding Agent -> Tools -> Reviewer -> Tests -> Debugger -> Final Report
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from vibe_studio.agents.coding_agent import AgentState, AgentTaskResult, AutonomousAgent, AutonomyMode
from vibe_studio.agents.complexity_classifier import ComplexityClassifier, TaskComplexity
from vibe_studio.agents.debug_assistant import DebugAssistant
from vibe_studio.agents.evolutionary_strategy import StrategyPool
from vibe_studio.agents.intent_predictor import IntentPredictor
from vibe_studio.agents.navigator_agent import NavigatorAgent
from vibe_studio.agents.reviewer_agent import ReviewerAgent, ReviewResult
from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.core.global_memory import GlobalMemory
from vibe_studio.tools.patch_tools import PatchTools
from vibe_studio.tools.terminal_tools import TerminalTools

logger = logging.getLogger(__name__)



@dataclass
class PipelineStageTiming:
    stage_name: str
    duration_seconds: float
    status: str = "success"
    details: str = ""


@dataclass
class OrchestratedExecutionResult:
    prompt: str
    intent_suggestions: list[str] = field(default_factory=list)
    navigated_files: list[str] = field(default_factory=list)
    execution_result: AgentTaskResult | None = None
    review_result: ReviewResult | None = None
    test_result: dict[str, Any] = field(default_factory=dict)
    stage_timings: list[PipelineStageTiming] = field(default_factory=list)
    summary: str = ""


class AgentOrchestrator:
    """Master agent orchestrator coordinating sub-agents for end-to-end task execution."""

    def __init__(
        self,
        workspace_root: str | Path,
        provider: Any | None = None,
        model: str = "llama3.1",
        stream_callback: Callable[[str], None] | None = None,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
        max_iterations: int = 30,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.provider = provider
        self.model = model
        self.stream_callback = stream_callback
        self.progress_callback = progress_callback
        self.max_iterations = max_iterations

        self.intent_predictor = IntentPredictor()
        self.navigator = NavigatorAgent(self.workspace_root)
        self.context_engine = ContextEngine(self.workspace_root)
        self.reviewer = ReviewerAgent()
        self.debug_assistant = DebugAssistant()
        self.patch_tools = PatchTools(self.workspace_root)
        self.terminal_tools = TerminalTools(self.workspace_root)
        # Sütun 2: Evolutionary strategy
        self._strategy_pool = StrategyPool()
        # Sütun 5: Adaptive complexity classifier
        self._complexity_clf = ComplexityClassifier()
        # Sütun 7: Global memory cross-project hints
        self._global_memory = GlobalMemory()

    def _notify_progress(self, stage: str, data: dict[str, Any]) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(stage, data)
            except Exception:
                pass
        try:
            from vibe_studio.api.websocket_server import _ws_instance
            if _ws_instance and _ws_instance.running:
                _ws_instance.broadcast("agent_progress", {"stage": stage, "details": data})
        except Exception:
            pass

    def execute_task(self, prompt: str, active_file: str | None = None) -> OrchestratedExecutionResult:
        timings: list[PipelineStageTiming] = []

        # 1. Intent Analysis
        t0 = time.monotonic()
        self._notify_progress("intent_analysis_start", {"prompt": prompt})
        self.intent_predictor.record_command(prompt)
        suggestions = self.intent_predictor.predict_next(prompt)
        timings.append(PipelineStageTiming("intent_analysis", time.monotonic() - t0, details=f"Predicted {len(suggestions)} actions"))

        # 2. Navigation & File Discovery
        t0 = time.monotonic()
        self._notify_progress("navigation_start", {})
        navigated = self.navigator.discover_relevant_files(prompt)
        timings.append(PipelineStageTiming("navigation", time.monotonic() - t0, details=f"Found {len(navigated)} files"))

        # 2b. Adaptive Turbo Mode (Sütun 5)
        complexity = self._complexity_clf.classify(prompt, active_file, len(navigated))
        self._notify_progress("complexity_classified", {"tier": complexity.name})
        logger.debug("Task complexity: %s", complexity.name)

        # 2c. Global memory hint (Sütun 7)
        global_hint = self._global_memory.build_global_hint(prompt)
        if global_hint:
            logger.debug("Global memory hint available (%d chars)", len(global_hint))

        # 3. Context Engine Ranking
        t0 = time.monotonic()
        self._notify_progress("context_building_start", {})
        bundle = self.context_engine.build(
            prompt=prompt,
            active_file=active_file or (navigated[0] if navigated else None),
            token_budget=16000,
        )
        timings.append(PipelineStageTiming("context_building", time.monotonic() - t0, details=f"Ranked {len(bundle.items)} items ({bundle.total_tokens_est} est tokens)"))

        # 4. Coding Agent Execution
        t0 = time.monotonic()
        self._notify_progress("agent_execution_start", {})
        agent = AutonomousAgent(
            project_root=self.workspace_root,
            provider=self.provider,
            model=self.model,
            autonomy_mode=AutonomyMode.AUTO,
            max_iterations=self.max_iterations,
            stream_callback=self.stream_callback,
        )

        def _agent_event(event_type: str, data: dict[str, Any]):
            self._notify_progress(f"agent_{event_type}", data)

        agent.add_event_callback(_agent_event)
        exec_res = agent.run(prompt)
        timings.append(PipelineStageTiming("agent_execution", time.monotonic() - t0, status=exec_res.status.value, details=f"Changed {len(exec_res.files_changed)} files"))

        # 5. Code Review
        t0 = time.monotonic()
        self._notify_progress("code_review_start", {})
        diff_text = ""
        if self.patch_tools.history:
            diff_text = self.patch_tools.history[-1].diff
        review_res = self.reviewer.review_diff(diff_text)
        timings.append(PipelineStageTiming("code_review", time.monotonic() - t0, status="passed" if review_res.passed else "failed", details=f"Score: {review_res.score}/100"))

        # 6. Test Runner & Self-Repair
        t0 = time.monotonic()
        self._notify_progress("test_runner_start", {})
        test_res = self.terminal_tools.run_tests()
        if test_res.get("exit_code") != 0 and test_res.get("stderr"):
            self._notify_progress("self_repair_triggered", {"stderr": test_res.get("stderr")})
            tb_analysis = self.debug_assistant.analyze_traceback(test_res["stderr"])
            if tb_analysis.file_path and Path(self.workspace_root / tb_analysis.file_path).exists():
                agent.run(f"Fix error in {tb_analysis.file_path}: {tb_analysis.error_message}")
                test_res = self.terminal_tools.run_tests()
        timings.append(PipelineStageTiming("test_validation", time.monotonic() - t0, status="success" if test_res.get("exit_code") == 0 else "failed"))

        # 7. Final Report Synthesis
        summary_lines = [
            f"Task: {prompt}",
            f"Navigation: Found {len(navigated)} relevant files ({', '.join(navigated[:3])})",
            f"Agent Execution: {exec_res.status.value} ({len(exec_res.files_changed)} files changed)",
            f"Code Review: Score {review_res.score}/100 ({'PASSED' if review_res.passed else 'FAILED'})",
            f"Tests: Exit Code {test_res.get('exit_code', 0)}",
            f"Total Duration: {sum(t.duration_seconds for t in timings):.2f}s",
        ]

        self._notify_progress("orchestration_completed", {"summary": "\n".join(summary_lines)})

        return OrchestratedExecutionResult(
            prompt=prompt,
            intent_suggestions=suggestions,
            navigated_files=navigated,
            execution_result=exec_res,
            review_result=review_res,
            test_result=test_res,
            stage_timings=timings,
            summary="\n".join(summary_lines),
        )

    def execute_task_stream(
        self,
        prompt: str,
        active_file: str | None = None,
    ):
        """Execute the full agent pipeline and yield structured stage events.

        Each yielded value is a ``dict`` with keys:
          - ``stage`` (str): stage identifier (e.g. ``"intent_analysis"``)
          - ``status`` (str): ``"start"`` | ``"done"`` | ``"error"``
          - ``data`` (dict): stage-specific payload
          - ``elapsed`` (float): seconds elapsed since pipeline start

        The final yielded event has stage ``"result"`` and data containing the
        full :class:`OrchestratedExecutionResult`.

        Usage::

            for event in orchestrator.execute_task_stream("Add unit tests"):
                if event["stage"] == "result":
                    result = event["data"]["result"]
                else:
                    print(f"[{event['stage']}] {event['status']}")
        """
        _start = time.monotonic()

        def _ev(stage: str, status: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
            return {
                "stage": stage,
                "status": status,
                "data": data or {},
                "elapsed": round(time.monotonic() - _start, 3),
            }

        timings: list[PipelineStageTiming] = []

        # ── Stage 1: Intent Analysis ─────────────────────────────────────
        yield _ev("intent_analysis", "start", {"prompt": prompt})
        t0 = time.monotonic()
        try:
            self.intent_predictor.record_command(prompt)
            suggestions = self.intent_predictor.predict_next(prompt)
            timings.append(PipelineStageTiming("intent_analysis", time.monotonic() - t0))
            yield _ev("intent_analysis", "done", {"suggestions": suggestions})
        except Exception as exc:
            timings.append(PipelineStageTiming("intent_analysis", time.monotonic() - t0, status="error"))
            yield _ev("intent_analysis", "error", {"error": str(exc)})
            suggestions = []

        # ── Stage 2: Navigation ──────────────────────────────────────────
        yield _ev("navigation", "start")
        t0 = time.monotonic()
        try:
            navigated = self.navigator.discover_relevant_files(prompt)
            timings.append(PipelineStageTiming("navigation", time.monotonic() - t0, details=f"Found {len(navigated)} files"))
            yield _ev("navigation", "done", {"files": navigated})
        except Exception as exc:
            timings.append(PipelineStageTiming("navigation", time.monotonic() - t0, status="error"))
            yield _ev("navigation", "error", {"error": str(exc)})
            navigated = []

        # ── Stage 3: Context Building ────────────────────────────────────
        yield _ev("context_building", "start")
        t0 = time.monotonic()
        try:
            bundle = self.context_engine.build(
                prompt=prompt,
                active_file=active_file or (navigated[0] if navigated else None),
                token_budget=16000,
            )
            timings.append(PipelineStageTiming("context_building", time.monotonic() - t0,
                details=f"Ranked {len(bundle.items)} items ({bundle.total_tokens_est} est tokens)"))
            yield _ev("context_building", "done", {"items": len(bundle.items), "tokens_est": bundle.total_tokens_est})
        except Exception as exc:
            timings.append(PipelineStageTiming("context_building", time.monotonic() - t0, status="error"))
            yield _ev("context_building", "error", {"error": str(exc)})
            bundle = None  # type: ignore[assignment]

        # ── Stage 4: Agent Execution ─────────────────────────────────────
        yield _ev("agent_execution", "start", {"prompt": prompt})
        t0 = time.monotonic()
        try:
            agent = AutonomousAgent(
                project_root=self.workspace_root,
                provider=self.provider,
                model=self.model,
                autonomy_mode=AutonomyMode.AUTO,
                max_iterations=self.max_iterations,
                stream_callback=self.stream_callback,
            )
            agent.add_event_callback(lambda etype, d: self._notify_progress(f"agent_{etype}", d))
            exec_res = agent.run(prompt)
            timings.append(PipelineStageTiming("agent_execution", time.monotonic() - t0,
                status=exec_res.status.value, details=f"Changed {len(exec_res.files_changed)} files"))
            yield _ev("agent_execution", "done", {
                "status": exec_res.status.value,
                "files_changed": exec_res.files_changed,
            })
        except Exception as exc:
            timings.append(PipelineStageTiming("agent_execution", time.monotonic() - t0, status="error"))
            yield _ev("agent_execution", "error", {"error": str(exc)})
            exec_res = AgentTaskResult(status=AgentState.FAILED, task=prompt, summary=str(exc))

        # ── Stage 5: Code Review ─────────────────────────────────────────
        yield _ev("code_review", "start")
        t0 = time.monotonic()
        try:
            diff_text = self.patch_tools.history[-1].diff if self.patch_tools.history else ""
            review_res = self.reviewer.review_diff(diff_text)
            timings.append(PipelineStageTiming("code_review", time.monotonic() - t0,
                status="passed" if review_res.passed else "failed", details=f"Score: {review_res.score}/100"))
            yield _ev("code_review", "done", {
                "score": review_res.score,
                "passed": review_res.passed,
                "issue_count": len(review_res.issues),
            })
        except Exception as exc:
            timings.append(PipelineStageTiming("code_review", time.monotonic() - t0, status="error"))
            yield _ev("code_review", "error", {"error": str(exc)})
            review_res = ReviewResult(passed=True, score=100, feedback=[])

        # ── Stage 6: Test Validation + Self-Repair ───────────────────────
        yield _ev("test_validation", "start")
        t0 = time.monotonic()
        try:
            test_res = self.terminal_tools.run_tests()
            if test_res.get("exit_code") != 0 and test_res.get("stderr"):
                yield _ev("self_repair", "start", {"error": test_res.get("stderr", "")[:300]})
                tb_analysis = self.debug_assistant.analyze_traceback(test_res["stderr"])
                if tb_analysis.file_path and Path(self.workspace_root / tb_analysis.file_path).exists():
                    agent.run(f"Fix error in {tb_analysis.file_path}: {tb_analysis.error_message}")
                    test_res = self.terminal_tools.run_tests()
                yield _ev("self_repair", "done", {"exit_code": test_res.get("exit_code")})
            timings.append(PipelineStageTiming("test_validation", time.monotonic() - t0,
                status="success" if test_res.get("exit_code") == 0 else "failed"))
            yield _ev("test_validation", "done", {"exit_code": test_res.get("exit_code", 0)})
        except Exception as exc:
            timings.append(PipelineStageTiming("test_validation", time.monotonic() - t0, status="error"))
            yield _ev("test_validation", "error", {"error": str(exc)})
            test_res = {"exit_code": -1, "stdout": "", "stderr": str(exc)}

        # ── Stage 7: Final Result ────────────────────────────────────────
        summary_lines = [
            f"Task: {prompt}",
            f"Navigation: Found {len(navigated)} relevant files ({', '.join(navigated[:3])})",
            f"Agent Execution: {exec_res.status.value} ({len(exec_res.files_changed)} files changed)",
            f"Code Review: Score {review_res.score}/100 ({'PASSED' if review_res.passed else 'FAILED'})",
            f"Tests: Exit Code {test_res.get('exit_code', 0)}",
            f"Total Duration: {sum(t.duration_seconds for t in timings):.2f}s",
        ]
        final_result = OrchestratedExecutionResult(
            prompt=prompt,
            intent_suggestions=suggestions,
            navigated_files=navigated,
            execution_result=exec_res,
            review_result=review_res,
            test_result=test_res,
            stage_timings=timings,
            summary="\n".join(summary_lines),
        )
        self._notify_progress("orchestration_completed", {"summary": final_result.summary})
        yield _ev("result", "done", {"result": final_result})

    def execute_moa_consensus_task(
        self,
        prompt: str,
        num_candidates: int = 2,
    ) -> OrchestratedExecutionResult:
        """Run Mixture of Agents (MoA) with Evolutionary Strategy selection.

        Sütun 2: Each candidate uses a fitness-selected strategy from StrategyPool.
        The winning strategy is evolved (fitness updated) based on review score.
        """
        import concurrent.futures
        self._notify_progress("moa_consensus_start", {"candidates": num_candidates})

        def _run_proposal(agent_id: int):
            # Select strategy per candidate
            strategy = self._strategy_pool.select(prompt)
            agent = AutonomousAgent(
                project_root=self.workspace_root,
                provider=self.provider,
                model=self.model,
                autonomy_mode=AutonomyMode.AUTO,
            )
            res = agent.run(f"[PROPOSAL #{agent_id+1}] {prompt}")
            diff_text = agent.tool_registry.patch_tools.history[-1].diff if agent.tool_registry.patch_tools.history else ""
            review = self.reviewer.review_diff(diff_text)
            return agent_id, res, review, strategy

        proposals = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_candidates) as executor:
            futures = [executor.submit(_run_proposal, i) for i in range(num_candidates)]
            for f in concurrent.futures.as_completed(futures):
                try:
                    proposals.append(f.result())
                except Exception as exc:
                    logger.warning("MoA proposal execution failed: %s", exc)

        if proposals:
            best_id, best_res, best_review, best_strategy = max(
                proposals, key=lambda p: p[2].score
            )
            # Sütun 2: Evolve the winning strategy
            self._strategy_pool.evolve(best_strategy, score=float(best_review.score), prompt=prompt)
            self._notify_progress("moa_judge_selected", {"best_id": best_id+1, "score": best_review.score})
            return OrchestratedExecutionResult(
                prompt=prompt,
                execution_result=best_res,
                review_result=best_review,
                summary=f"MoA Judge selected Proposal #{best_id+1} (Score: {best_review.score}/100)",
            )

        return self.execute_task(prompt)
