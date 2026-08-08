"""AgentOrchestrator — unifies specialized sub-agents into a single autonomous pipeline.

Pipeline Flow:
User Prompt -> Intent -> Navigator -> Context -> Coding Agent -> Tools -> Reviewer -> Tests -> Debugger -> Final Report
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vibe_studio.agents.coding_agent import AgentTaskResult, AutonomousAgent, AutonomyMode
from vibe_studio.agents.debug_assistant import DebugAssistant
from vibe_studio.agents.intent_predictor import IntentPredictor
from vibe_studio.agents.navigator_agent import NavigatorAgent
from vibe_studio.agents.reviewer_agent import ReviewerAgent, ReviewResult
from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.tools.patch_tools import PatchTools
from vibe_studio.tools.terminal_tools import TerminalTools


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
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.provider = provider
        self.model = model
        self.stream_callback = stream_callback
        self.progress_callback = progress_callback

        self.intent_predictor = IntentPredictor()
        self.navigator = NavigatorAgent(self.workspace_root)
        self.context_engine = ContextEngine(self.workspace_root)
        self.reviewer = ReviewerAgent()
        self.debug_assistant = DebugAssistant()
        self.patch_tools = PatchTools(self.workspace_root)
        self.terminal_tools = TerminalTools(self.workspace_root)

    def _notify_progress(self, stage: str, data: dict[str, Any]) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(stage, data)
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
