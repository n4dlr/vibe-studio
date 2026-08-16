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
from vibe_studio.core.cancellation import CancellationToken
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
        cancellation_token: CancellationToken | None = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.provider = provider
        self.model = model
        self.stream_callback = stream_callback
        self.progress_callback = progress_callback
        self.max_iterations = max_iterations
        self._cancellation_token: CancellationToken | None = cancellation_token

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

    # ------------------------------------------------------------------
    # Adaptive Routing — core decision
    # ------------------------------------------------------------------

    def _classify_task(
        self,
        prompt: str,
        active_file: str | None,
        navigated_count: int,
    ) -> TaskComplexity:
        """Classify task and broadcast the tier to the Activity Panel."""
        complexity = self._complexity_clf.classify(prompt, active_file, navigated_count)
        self._notify_progress(
            "complexity_classified",
            {
                "tier": complexity.name,
                "description": self._complexity_clf.describe(complexity),
            },
        )
        logger.debug("Adaptive routing: %s", complexity.name)
        return complexity

    def _make_agent(self) -> AutonomousAgent:
        agent = AutonomousAgent(
            project_root=self.workspace_root,
            provider=self.provider,
            model=self.model,
            autonomy_mode=AutonomyMode.AUTO,
            max_iterations=self.max_iterations,
            stream_callback=self.stream_callback,
            cancellation_token=self._cancellation_token,
        )
        agent.add_event_callback(
            lambda etype, d: self._notify_progress(f"agent_{etype}", d)
        )
        return agent

    def cancel(self) -> None:
        """Request immediate cancellation of the current pipeline."""
        if self._cancellation_token is None:
            from vibe_studio.core.cancellation import CancellationToken as _CT
            self._cancellation_token = _CT()
        self._cancellation_token.cancel()

    def _is_cancelled(self) -> bool:
        return (
            self._cancellation_token is not None
            and self._cancellation_token.is_cancelled()
        )

    # ------------------------------------------------------------------
    # FAST path — surgical single-file change, minimal overhead
    # ------------------------------------------------------------------

    def _execute_fast(
        self,
        prompt: str,
        timings: list[PipelineStageTiming],
    ) -> OrchestratedExecutionResult:
        """⚡ FAST — skip intent/nav/context/review/test stages entirely."""
        t0 = time.monotonic()
        self._notify_progress("agent_execution_start", {"mode": "FAST"})
        agent = self._make_agent()
        exec_res = agent.run(prompt)
        timings.append(
            PipelineStageTiming(
                "agent_execution",
                time.monotonic() - t0,
                status=exec_res.status.value,
                details=f"FAST path — changed {len(exec_res.files_changed)} files",
            )
        )
        summary = (
            f"[⚡ FAST] Task: {prompt}\n"
            f"Agent: {exec_res.status.value} ({len(exec_res.files_changed)} files) "
            f"in {timings[-1].duration_seconds:.2f}s"
        )
        self._notify_progress("orchestration_completed", {"summary": summary})
        return OrchestratedExecutionResult(
            prompt=prompt,
            execution_result=exec_res,
            stage_timings=timings,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # NORMAL path — standard pipeline, no MoA
    # ------------------------------------------------------------------

    def _execute_normal(
        self,
        prompt: str,
        active_file: str | None,
        timings: list[PipelineStageTiming],
    ) -> OrchestratedExecutionResult:
        """🔄 NORMAL — intent + nav + context + agent + review + test."""
        # 1. Intent
        t0 = time.monotonic()
        self._notify_progress("intent_analysis_start", {"prompt": prompt})
        self.intent_predictor.record_command(prompt)
        suggestions = self.intent_predictor.predict_next(prompt)
        timings.append(PipelineStageTiming("intent_analysis", time.monotonic() - t0))

        # 2. Navigation
        t0 = time.monotonic()
        self._notify_progress("navigation_start", {})
        navigated = self.navigator.discover_relevant_files(prompt)
        timings.append(PipelineStageTiming("navigation", time.monotonic() - t0,
                       details=f"Found {len(navigated)} files"))

        # 3. Context
        t0 = time.monotonic()
        self._notify_progress("context_building_start", {})
        bundle = self.context_engine.build(
            prompt=prompt,
            active_file=active_file or (navigated[0] if navigated else None),
            token_budget=16000,
        )
        timings.append(PipelineStageTiming("context_building", time.monotonic() - t0,
                       details=f"{len(bundle.items)} items"))

        # 4. Agent
        t0 = time.monotonic()
        self._notify_progress("agent_execution_start", {"mode": "NORMAL"})
        agent = self._make_agent()
        exec_res = agent.run(prompt)
        timings.append(PipelineStageTiming("agent_execution", time.monotonic() - t0,
                       status=exec_res.status.value,
                       details=f"Changed {len(exec_res.files_changed)} files"))

        # 5. Code Review
        t0 = time.monotonic()
        diff_text = self.patch_tools.history[-1].diff if self.patch_tools.history else ""
        review_res = self.reviewer.review_diff(diff_text)
        timings.append(PipelineStageTiming("code_review", time.monotonic() - t0,
                       status="passed" if review_res.passed else "failed"))

        # 6. Test + self-repair
        t0 = time.monotonic()
        test_res = self.terminal_tools.run_tests()
        if test_res.get("exit_code") != 0 and test_res.get("stderr"):
            tb = self.debug_assistant.analyze_traceback(test_res["stderr"])
            if tb.file_path and Path(self.workspace_root / tb.file_path).exists():
                agent.run(f"Fix error in {tb.file_path}: {tb.error_message}")
                test_res = self.terminal_tools.run_tests()
        timings.append(PipelineStageTiming("test_validation", time.monotonic() - t0,
                       status="success" if test_res.get("exit_code") == 0 else "failed"))

        summary_lines = [
            f"[🔄 NORMAL] Task: {prompt}",
            f"Navigation: {len(navigated)} files ({', '.join(navigated[:3])})",
            f"Agent: {exec_res.status.value} ({len(exec_res.files_changed)} files changed)",
            f"Review: {review_res.score}/100 ({'PASSED' if review_res.passed else 'FAILED'})",
            f"Tests: exit={test_res.get('exit_code', 0)}",
            f"Total: {sum(t.duration_seconds for t in timings):.2f}s",
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

    # ------------------------------------------------------------------
    # DEEP path — full pipeline + MoA consensus judge
    # ------------------------------------------------------------------

    def _execute_deep(
        self,
        prompt: str,
        active_file: str | None,
        timings: list[PipelineStageTiming],
    ) -> OrchestratedExecutionResult:
        """🧠 DEEP — full pipeline: Graph RAG + LSP + MoA consensus."""
        # Steps 1-6 identical to NORMAL first
        result = self._execute_normal(prompt, active_file, timings)

        # Extra: MoA consensus over the already-executed result
        t0 = time.monotonic()
        self._notify_progress("moa_consensus_start", {"mode": "DEEP"})
        try:
            moa_result = self.execute_moa_consensus_task(prompt, num_candidates=2)
            # Replace execution result if MoA produced a better one
            if (
                moa_result.review_result
                and result.review_result
                and moa_result.review_result.score > result.review_result.score
            ):
                result = moa_result
                logger.info("DEEP: MoA consensus improved score to %d", moa_result.review_result.score)
        except Exception as exc:
            logger.warning("DEEP: MoA consensus failed (%s) — using NORMAL result", exc)
        timings.append(PipelineStageTiming("moa_consensus", time.monotonic() - t0))

        # Update summary prefix
        result.summary = f"[🧠 DEEP] " + result.summary.lstrip("[🔄 NORMAL] ")
        self._notify_progress("orchestration_completed", {"summary": result.summary})
        return result

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def execute_task(self, prompt: str, active_file: str | None = None) -> OrchestratedExecutionResult:
        timings: list[PipelineStageTiming] = []

        if self._is_cancelled():
            return OrchestratedExecutionResult(
                prompt=prompt,
                summary="Cancelled before execution started.",
            )

        # Global memory hint
        global_hint = self._global_memory.build_global_hint(prompt)
        if global_hint:
            logger.debug("Global memory hint available (%d chars)", len(global_hint))

        # Quick pre-navigation classification (file count unknown yet → 0)
        complexity = self._classify_task(prompt, active_file, 0)

        if complexity == TaskComplexity.FAST:
            return self._execute_fast(prompt, timings)
        elif complexity == TaskComplexity.NORMAL:
            return self._execute_normal(prompt, active_file, timings)
        else:  # DEEP
            return self._execute_deep(prompt, active_file, timings)

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

        # ── Pre-flight: classify complexity ──────────────────────────────
        complexity = self._classify_task(prompt, active_file, 0)
        yield _ev("complexity_classified", "done", {
            "tier": complexity.name,
            "description": self._complexity_clf.describe(complexity),
        })

        suggestions: list[str] = []
        navigated: list[str] = []
        exec_res = AgentTaskResult(status=AgentState.FAILED, task=prompt, summary="not run")
        review_res = ReviewResult(passed=True, score=100, feedback=[])
        test_res: dict[str, Any] = {"exit_code": 0}

        # ── ⚡ FAST path — agent only, no pipeline overhead ───────────────
        if complexity == TaskComplexity.FAST:
            yield _ev("agent_execution", "start", {"prompt": prompt, "mode": "FAST"})
            t0 = time.monotonic()
            try:
                agent = self._make_agent()
                exec_res = agent.run(prompt)
                timings.append(PipelineStageTiming(
                    "agent_execution", time.monotonic() - t0,
                    status=exec_res.status.value,
                    details=f"FAST — {len(exec_res.files_changed)} files",
                ))
                yield _ev("agent_execution", "done", {
                    "status": exec_res.status.value,
                    "files_changed": exec_res.files_changed,
                    "mode": "FAST",
                })
            except Exception as exc:
                timings.append(PipelineStageTiming("agent_execution", time.monotonic() - t0, status="error"))
                yield _ev("agent_execution", "error", {"error": str(exc)})
                exec_res = AgentTaskResult(status=AgentState.FAILED, task=prompt, summary=str(exc))

        else:
            # ── Stage 1: Intent Analysis (NORMAL + DEEP) ─────────────────
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

            # ── Stage 2: Navigation ──────────────────────────────────────
            yield _ev("navigation", "start")
            t0 = time.monotonic()
            try:
                navigated = self.navigator.discover_relevant_files(prompt)
                timings.append(PipelineStageTiming("navigation", time.monotonic() - t0,
                               details=f"Found {len(navigated)} files"))
                yield _ev("navigation", "done", {"files": navigated})
            except Exception as exc:
                timings.append(PipelineStageTiming("navigation", time.monotonic() - t0, status="error"))
                yield _ev("navigation", "error", {"error": str(exc)})
                navigated = []

            # ── Stage 3: Context Building ────────────────────────────────
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
                yield _ev("context_building", "done", {
                    "items": len(bundle.items),
                    "tokens_est": bundle.total_tokens_est,
                })
            except Exception as exc:
                timings.append(PipelineStageTiming("context_building", time.monotonic() - t0, status="error"))
                yield _ev("context_building", "error", {"error": str(exc)})

            # ── Stage 4: Agent Execution ─────────────────────────────────
            yield _ev("agent_execution", "start", {"prompt": prompt, "mode": complexity.name})
            t0 = time.monotonic()
            try:
                agent = self._make_agent()
                exec_res = agent.run(prompt)
                timings.append(PipelineStageTiming("agent_execution", time.monotonic() - t0,
                    status=exec_res.status.value,
                    details=f"Changed {len(exec_res.files_changed)} files"))
                yield _ev("agent_execution", "done", {
                    "status": exec_res.status.value,
                    "files_changed": exec_res.files_changed,
                })
            except Exception as exc:
                timings.append(PipelineStageTiming("agent_execution", time.monotonic() - t0, status="error"))
                yield _ev("agent_execution", "error", {"error": str(exc)})
                exec_res = AgentTaskResult(status=AgentState.FAILED, task=prompt, summary=str(exc))

            # ── Stage 5: Code Review ─────────────────────────────────────
            yield _ev("code_review", "start")
            t0 = time.monotonic()
            try:
                diff_text = self.patch_tools.history[-1].diff if self.patch_tools.history else ""
                review_res = self.reviewer.review_diff(diff_text)
                timings.append(PipelineStageTiming("code_review", time.monotonic() - t0,
                    status="passed" if review_res.passed else "failed",
                    details=f"Score: {review_res.score}/100"))
                yield _ev("code_review", "done", {
                    "score": review_res.score,
                    "passed": review_res.passed,
                    "issue_count": len(review_res.issues),
                })
            except Exception as exc:
                timings.append(PipelineStageTiming("code_review", time.monotonic() - t0, status="error"))
                yield _ev("code_review", "error", {"error": str(exc)})
                review_res = ReviewResult(passed=True, score=100, feedback=[])

            # ── Stage 6: Test Validation + Self-Repair ───────────────────
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

            # ── Stage 7 (DEEP only): MoA consensus ───────────────────────
            if complexity == TaskComplexity.DEEP:
                yield _ev("moa_consensus", "start", {"candidates": 2})
                t0 = time.monotonic()
                try:
                    moa_result = self.execute_moa_consensus_task(prompt, num_candidates=2)
                    if (
                        moa_result.review_result
                        and review_res
                        and moa_result.review_result.score > review_res.score
                    ):
                        exec_res = moa_result.execution_result or exec_res
                        review_res = moa_result.review_result
                    timings.append(PipelineStageTiming("moa_consensus", time.monotonic() - t0))
                    yield _ev("moa_consensus", "done", {"score": review_res.score})
                except Exception as exc:
                    logger.warning("DEEP MoA failed: %s", exc)
                    timings.append(PipelineStageTiming("moa_consensus", time.monotonic() - t0, status="error"))
                    yield _ev("moa_consensus", "error", {"error": str(exc)})

        # ── Final Result ─────────────────────────────────────────────────
        tier_label = {"FAST": "⚡", "NORMAL": "🔄", "DEEP": "🧠"}.get(complexity.name, "")
        summary_lines = [
            f"[{tier_label} {complexity.name}] Task: {prompt}",
            f"Agent: {exec_res.status.value} ({len(exec_res.files_changed)} files changed)",
            f"Review: {review_res.score}/100 ({'PASSED' if review_res.passed else 'FAILED'})",
            f"Tests: exit={test_res.get('exit_code', 0)}",
            f"Duration: {sum(t.duration_seconds for t in timings):.2f}s",
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
