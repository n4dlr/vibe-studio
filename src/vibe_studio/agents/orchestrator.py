"""AgentOrchestrator — unifies specialized sub-agents into a single autonomous pipeline.

Pipeline Flow:
User Prompt -> Intent -> Navigator -> Context -> Coding Agent -> Tools -> Reviewer -> Tests -> Debugger -> Final Report
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_studio.agents.coding_agent import AgentTaskResult, AutonomousAgent, AutonomyMode
from vibe_studio.agents.debug_assistant import DebugAssistant
from vibe_studio.agents.intent_predictor import IntentPredictor
from vibe_studio.agents.navigator_agent import NavigatorAgent
from vibe_studio.agents.reviewer_agent import ReviewerAgent, ReviewResult
from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.tools.patch_tools import PatchTools
from vibe_studio.tools.terminal_tools import TerminalTools


@dataclass
class OrchestratedExecutionResult:
    prompt: str
    intent_suggestions: list[str] = field(default_factory=list)
    navigated_files: list[str] = field(default_factory=list)
    execution_result: AgentTaskResult | None = None
    review_result: ReviewResult | None = None
    test_result: dict[str, Any] = field(default_factory=dict)
    summary: str = ""


class AgentOrchestrator:
    """Master agent orchestrator coordinating sub-agents for end-to-end task execution."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.intent_predictor = IntentPredictor()
        self.navigator = NavigatorAgent(self.workspace_root)
        self.context_engine = ContextEngine(self.workspace_root)
        self.reviewer = ReviewerAgent()
        self.debug_assistant = DebugAssistant()
        self.patch_tools = PatchTools(self.workspace_root)
        self.terminal_tools = TerminalTools(self.workspace_root)

    def execute_task(self, prompt: str, active_file: str | None = None) -> OrchestratedExecutionResult:
        # 1. Intent Analysis
        self.intent_predictor.record_command(prompt)
        suggestions = self.intent_predictor.predict_next(prompt)

        # 2. Navigation & File Discovery
        navigated = self.navigator.discover_relevant_files(prompt)

        # 3. Context Engine Ranking
        bundle = self.context_engine.build(
            prompt=prompt,
            active_file=active_file or (navigated[0] if navigated else None),
            token_budget=16000,
        )

        # 4. Coding Agent Execution
        agent = AutonomousAgent(
            project_root=self.workspace_root,
            autonomy_mode=AutonomyMode.AUTO,
        )
        exec_res = agent.run(prompt)

        # 5. Code Review
        diff_text = ""
        if self.patch_tools.history:
            diff_text = self.patch_tools.history[-1].diff
        review_res = self.reviewer.review_diff(diff_text)

        # 6. Test Runner & Self-Repair
        test_res = self.terminal_tools.run_tests()
        if test_res.get("exit_code") != 0 and test_res.get("stderr"):
            tb_analysis = self.debug_assistant.analyze_traceback(test_res["stderr"])
            # Attempt self-repair if error line identified
            if tb_analysis.file_path and Path(self.workspace_root / tb_analysis.file_path).exists():
                agent.run(f"Fix error in {tb_analysis.file_path}: {tb_analysis.error_message}")
                test_res = self.terminal_tools.run_tests()

        # 7. Final Report Synthesis
        summary_lines = [
            f"Task: {prompt}",
            f"Navigation: Found {len(navigated)} relevant files ({', '.join(navigated[:3])})",
            f"Agent Execution: {exec_res.status.value} ({len(exec_res.files_changed)} files changed)",
            f"Code Review: Score {review_res.score}/100 ({'PASSED' if review_res.passed else 'FAILED'})",
            f"Tests: Exit Code {test_res.get('exit_code', 0)}",
        ]

        return OrchestratedExecutionResult(
            prompt=prompt,
            intent_suggestions=suggestions,
            navigated_files=navigated,
            execution_result=exec_res,
            review_result=review_res,
            test_result=test_res,
            summary="\n".join(summary_lines),
        )
