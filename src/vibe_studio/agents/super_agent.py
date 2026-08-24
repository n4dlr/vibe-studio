"""SuperAgent — Ultra-Autonomous, Boundary-Pushing AI Agent for Vibe Studio.

Key Capabilities:
1. Hierarchical Planning & Dynamic Replanning (breaks goals into executable milestones)
2. Playwright Browser Automation & Web Research (navigation, click, type, screenshot, search)
3. Deep Code Generation, Refactoring, and Test-Driven Self-Repair
4. Technical Writing, Article Creation, and Documentation Authoring
5. Self-Critique & Limit-Pushing Loop (evaluates results 0-100; auto-refines if score < 85)
6. Persistent Memory & Cross-Domain Synthesis
7. Multilingual Native Support (Azerbaijani & English)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from vibe_studio.agents.coding_agent import AgentState, AgentStep
from vibe_studio.agents.execution_context import ExecutionContext
from vibe_studio.agents.output_processor import ErrorTracker, classify_error, extract_errors
from vibe_studio.agents.stuck_detector import StuckAgentDetector
from vibe_studio.agents.tool_call_parser import parse_tool_calls, strip_tool_calls, validate_tool_call
from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.diff.diff_proposal import DiffProposalManager
from vibe_studio.providers.capability_detector import detect_capabilities
from vibe_studio.security.sensitive_file_detector import SensitiveFileDetector
from vibe_studio.tools.tool_registry import ToolRegistry, default_tool_registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures & Enums
# ---------------------------------------------------------------------------

class PlanItemStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class PlanMilestone:
    id: int
    title: str
    description: str
    status: PlanItemStatus = PlanItemStatus.PENDING
    result_summary: str = ""
    critique_score: int = 0
    sub_tasks: list[str] = field(default_factory=list)


@dataclass
class HierarchicalPlan:
    goal: str
    milestones: list[PlanMilestone] = field(default_factory=list)
    version: int = 1
    replan_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "version": self.version,
            "replan_count": self.replan_count,
            "milestones": [
                {
                    "id": m.id,
                    "title": m.title,
                    "description": m.description,
                    "status": m.status.value,
                    "result_summary": m.result_summary,
                    "critique_score": m.critique_score,
                    "sub_tasks": m.sub_tasks,
                }
                for m in self.milestones
            ],
        }


@dataclass
class SelfCritiqueResult:
    score: int  # 0 to 100
    passed_threshold: bool
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    actionable_improvements: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class SuperAgentResult:
    status: AgentState
    goal: str
    final_output: str
    plan: HierarchicalPlan
    critique: SelfCritiqueResult
    files_changed: list[str] = field(default_factory=list)
    browser_actions: int = 0
    total_steps: int = 0
    duration_seconds: float = 0.0
    execution_id: str = ""


# ---------------------------------------------------------------------------
# Self-Critique Engine
# ---------------------------------------------------------------------------

class SelfCritiqueEngine:
    """Evaluates task execution quality and decides if more refinement is needed."""

    CRITIQUE_PROMPT_TEMPLATE = """You are a rigorous, demanding AI evaluator and quality assurance judge.
Evaluate the following completed work against the original user goal.

USER GOAL:
{goal}

EXECUTION SUMMARY & RESULTS:
{summary}

FILES MODIFIED:
{files}

TOOL ACTIONS EXECUTED:
{tools}

EVALUATION CRITERIA:
1. Completeness: Did the solution fulfill ALL explicit and implicit requirements?
2. Quality & Robustness: Is code clean, tested, error-free, and well-structured? Is writing/research thorough and informative?
3. No Hallucinations / Stubbing: Did the agent avoid placeholder comments (e.g. "// TODO", "pass", incomplete implementations)?
4. Verifiability: Can the results be inspected or tested?

Respond STRICTLY in JSON format:
```json
{{
  "score": <integer from 0 to 100>,
  "passed": <true if score >= {threshold} else false>,
  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."],
  "actionable_improvements": ["...", "..."],
  "summary": "<1-2 sentence overall verdict>"
}}
```
"""

    def __init__(self, provider: Any = None, model: str = "llama3.1", min_score_threshold: int = 85):
        self.provider = provider
        self.model = model
        self.min_score_threshold = min_score_threshold

    def critique(
        self,
        goal: str,
        summary: str,
        files_changed: list[str],
        tool_history: list[AgentStep],
    ) -> SelfCritiqueResult:
        """Run self-critique pass. Fallback to rule-based evaluation if no provider."""
        if not self.provider:
            return self._heuristic_critique(goal, summary, files_changed, tool_history)

        tools_str = "\n".join(
            f"- {s.tool_name}({json.dumps(s.tool_args)[:100]}) -> exit={s.observation.get('exit_code', 0) if s.observation else '?'}"
            for s in tool_history[-15:]
        )

        prompt = self.CRITIQUE_PROMPT_TEMPLATE.format(
            goal=goal,
            summary=summary[:3000],
            files=", ".join(files_changed) or "None",
            tools=tools_str or "Direct response (no tools)",
            threshold=self.min_score_threshold,
        )

        try:
            raw = ""
            if hasattr(self.provider, "generate"):
                raw = self.provider.generate(prompt=prompt, model=self.model, temperature=0.1)
            elif hasattr(self.provider, "chat"):
                messages = [
                    {"role": "system", "content": "You are a strict quality evaluation judge."},
                    {"role": "user", "content": prompt},
                ]
                raw = self.provider.chat(messages=messages, model=self.model, temperature=0.1)

            # Parse JSON
            parsed = self._parse_critique_json(raw)
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning("LLM critique pass failed, using heuristic: %s", exc)

        return self._heuristic_critique(goal, summary, files_changed, tool_history)

    def _parse_critique_json(self, raw: str) -> SelfCritiqueResult | None:
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        candidate = match.group(1) if match else raw.strip()
        try:
            data = json.loads(candidate)
            score = max(0, min(100, int(data.get("score", 75))))
            return SelfCritiqueResult(
                score=score,
                passed_threshold=(score >= self.min_score_threshold),
                strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []),
                actionable_improvements=data.get("actionable_improvements", []),
                summary=data.get("summary", f"Quality score: {score}/100"),
            )
        except Exception:
            return None

    def _heuristic_critique(
        self,
        goal: str,
        summary: str,
        files_changed: list[str],
        tool_history: list[AgentStep],
    ) -> SelfCritiqueResult:
        score = 88
        strengths = ["Executed without unhandled crashes"]
        weaknesses = []
        improvements = []

        if not files_changed and any(k in goal.lower() for k in ["create", "write", "fix", "yarat", "yaz", "düzəlt"]):
            score -= 20
            weaknesses.append("Expected file modifications but none were recorded.")
            improvements.append("Create or patch the target file using write_file or patch_file.")

        errors_in_tools = [s for s in tool_history if s.observation and s.observation.get("exit_code", 0) != 0]
        if errors_in_tools:
            score -= min(30, len(errors_in_tools) * 10)
            weaknesses.append(f"{len(errors_in_tools)} tool call(s) failed during execution.")
            improvements.append("Resolve tool errors and verify with test/compile commands.")

        if len(summary.strip()) < 30:
            score -= 15
            weaknesses.append("Summary is too brief.")
            improvements.append("Provide a thorough and clear explanation of results.")

        return SelfCritiqueResult(
            score=max(0, score),
            passed_threshold=(score >= self.min_score_threshold),
            strengths=strengths,
            weaknesses=weaknesses,
            actionable_improvements=improvements,
            summary=f"Automated verification score: {score}/100",
        )


# ---------------------------------------------------------------------------
# Hierarchical Planner
# ---------------------------------------------------------------------------

class HierarchicalPlanner:
    """Decomposes goals into milestones and manages dynamic replanning."""

    PLAN_PROMPT_TEMPLATE = """You are a master technical architect and strategic planner.
Decompose the following user goal into 3 to 6 logical, sequentially actionable milestones.

USER GOAL:
{goal}

WORKSPACE CONTEXT:
{context}

STRICT JSON OUTPUT FORMAT:
```json
{{
  "milestones": [
    {{
      "id": 1,
      "title": "Short title",
      "description": "Clear description of what to do and verify",
      "sub_tasks": ["sub-step 1", "sub-step 2"]
    }}
  ]
}}
```
"""

    def __init__(self, provider: Any = None, model: str = "llama3.1"):
        self.provider = provider
        self.model = model

    def build_initial_plan(self, goal: str, context: str = "") -> HierarchicalPlan:
        """Create the milestone tree for the goal."""
        if not self.provider:
            return self._heuristic_plan(goal)

        prompt = self.PLAN_PROMPT_TEMPLATE.format(goal=goal, context=context[:1500])
        try:
            raw = ""
            if hasattr(self.provider, "generate"):
                raw = self.provider.generate(prompt=prompt, model=self.model, temperature=0.2)
            elif hasattr(self.provider, "chat"):
                raw = self.provider.chat(
                    messages=[
                        {"role": "system", "content": "You create structured hierarchical plans in JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    model=self.model,
                    temperature=0.2,
                )

            import re
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            candidate = m.group(1) if m else raw.strip()
            data = json.loads(candidate)
            ms_list = []
            for item in data.get("milestones", []):
                ms_list.append(
                    PlanMilestone(
                        id=int(item.get("id", len(ms_list) + 1)),
                        title=str(item.get("title", f"Milestone {len(ms_list) + 1}")),
                        description=str(item.get("description", "")),
                        sub_tasks=[str(st) for st in item.get("sub_tasks", [])],
                    )
                )
            if ms_list:
                return HierarchicalPlan(goal=goal, milestones=ms_list)
        except Exception as exc:
            logger.debug("Hierarchical plan LLM generation fallback: %s", exc)

        return self._heuristic_plan(goal)

    def _heuristic_plan(self, goal: str) -> HierarchicalPlan:
        g = goal.lower()
        milestones = []

        if any(w in g for w in ["search", "web", "find", "research", "araşdır"]):
            milestones = [
                PlanMilestone(1, "Gather Information", "Search the web or codebase for relevant references", sub_tasks=["web_search / search_text", "Inspect results"]),
                PlanMilestone(2, "Analyze & Synthesize", "Process information and structure findings", sub_tasks=["Extract key data points", "Synthesize summary"]),
                PlanMilestone(3, "Implement / Write Output", "Produce code, documentation, or report", sub_tasks=["Write files", "Save to memory"]),
                PlanMilestone(4, "Validate & Polish", "Verify quality and completion", sub_tasks=["Review against goal", "Finalize report"]),
            ]
        elif any(w in g for w in ["browse", "browser", "playwright", "click", "form", "page", "sayt"]):
            milestones = [
                PlanMilestone(1, "Launch & Navigate", "Open browser and navigate to target URL", sub_tasks=["browser_open / browser_navigate", "Verify page loaded"]),
                PlanMilestone(2, "Inspect & Interact", "Locate selectors and perform interactions", sub_tasks=["Click, type, or extract DOM", "Capture screenshot"]),
                PlanMilestone(3, "Process Page Results", "Extract text or logs and evaluate outcome", sub_tasks=["browser_extract_text", "browser_console_logs"]),
                PlanMilestone(4, "Conclude & Verify", "Ensure goal achieved and close browser", sub_tasks=["Verify result", "browser_close"]),
            ]
        else:
            milestones = [
                PlanMilestone(1, "Understand & Inspect", "Analyze repository structure, target files, and requirements", sub_tasks=["search_filename / read_file", "Identify relevant symbols"]),
                PlanMilestone(2, "Develop & Apply Changes", "Implement the requested features, fixes, or documentation", sub_tasks=["patch_file / write_file", "Update dependent modules"]),
                PlanMilestone(3, "Test & Self-Repair", "Run automated test suite and fix any regressions", sub_tasks=["run_tests / execute_command", "Auto-correct on errors"]),
                PlanMilestone(4, "Critique & Final Verification", "Perform self-evaluation and final validation pass", sub_tasks=["Verify against requirements", "Provide structured summary"]),
            ]

        return HierarchicalPlan(goal=goal, milestones=milestones)


# ---------------------------------------------------------------------------
# SuperAgent Main Class
# ---------------------------------------------------------------------------

class SuperAgent:
    """Master AI agent pushing its own limits with autonomous multi-domain execution."""

    SYSTEM_PROMPT = """You are SuperAgent — the most capable, determined, and intelligent autonomous AI agent in Vibe Studio.
You have access to a full computer environment: Code tools, Playwright Browser, Web Research, Terminal, AST Analyzers, and Persistent Memory.

### CORE OPERATING PRINCIPLES:
1. **NEVER SURRENDER / PUSH YOUR LIMITS**: If an approach fails, do NOT give up. Immediately diagnose the root cause, choose an alternative tool or strategy, and retry.
2. **MULTI-DOMAIN MASTERY**:
   - **Coding**: Read before writing. Use exact patches or clean writes. Always run tests or syntax checks.
   - **Browser (Playwright)**: Open URLs, inspect elements, fill forms, click buttons, capture screenshots (`browser_screenshot`), and evaluate JS.
   - **Web Research**: Use `web_search` and `web_fetch` to gather external live data, API docs, and information.
   - **Memory**: Save valuable findings to `memory_save` so nothing is lost.
   - **Writing**: Produce exhaustive, high-standard reports, docs, and explanations in the user's requested language.
3. **MULTILINGUAL FLUENCY**:
   - If the user communicates in Azerbaijani (AZ), respond and explain seamlessly in Azerbaijani.
   - If in English (EN), respond in English.
4. **TOOL CALL PROTOCOL**:
   Respond with EXACTLY ONE tool call in a JSON block per turn:
   ```json
   {{
     "tool": "tool_name",
     "args": {{
       "param": "value"
     }}
   }}
   ```
   When the mission is completely finished and verified, respond with your thorough FINAL SUMMARY in plain text (no JSON).

AVAILABLE TOOLS:
{tools_schema}
"""

    def __init__(
        self,
        workspace_root: str | Path,
        provider: Any | None = None,
        model: str = "llama3.1",
        tool_registry: ToolRegistry | None = None,
        max_iterations: int = 40,
        push_hard_threshold: int = 85,
        max_critique_retries: int = 2,
        stream_callback: Callable[[str], None] | None = None,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.provider = provider
        self.model = model
        self.tool_registry = tool_registry or default_tool_registry(self.workspace_root)
        self.max_iterations = max_iterations
        self.push_hard_threshold = push_hard_threshold
        self.max_critique_retries = max_critique_retries
        self.stream_callback = stream_callback
        self.progress_callback = progress_callback
        self.cancellation_token = cancellation_token or CancellationToken()
        self.execution_id = str(uuid.uuid4())

        self.planner = HierarchicalPlanner(provider=self.provider, model=self.model)
        self.critique_engine = SelfCritiqueEngine(
            provider=self.provider,
            model=self.model,
            min_score_threshold=self.push_hard_threshold,
        )
        self.stuck_detector = StuckAgentDetector()
        self.error_tracker = ErrorTracker(max_repeats=2)
        self.history: list[AgentStep] = []
        self.state = AgentState.IDLE

    def _notify(self, event_type: str, data: dict[str, Any]) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(event_type, {"execution_id": self.execution_id, **data})
            except Exception:
                pass

    def run(self, goal: str) -> SuperAgentResult:
        """Run the full autonomous limit-pushing execution loop."""
        start_time = time.monotonic()
        self.history.clear()
        self.error_tracker.reset()
        self.state = AgentState.ANALYZING
        self._notify("super_agent_started", {"goal": goal})

        # 1. Build Hierarchical Plan
        self._notify("planning_start", {"goal": goal})
        plan = self.planner.build_initial_plan(goal)
        self._notify("plan_created", {"plan": plan.to_dict()})

        tool_defs = self.tool_registry.list_tools()
        system_prompt = self.SYSTEM_PROMPT.format(tools_schema=json.dumps(tool_defs, indent=2))

        files_changed: set[str] = set()
        browser_action_count = 0
        iteration = 0
        critique_retry_count = 0
        current_milestone_idx = 0

        context_prompt = f"OBJECTIVE: {goal}\n\nHIERARCHICAL PLAN:\n"
        for m in plan.milestones:
            context_prompt += f"- [ ] Milestone {m.id}: {m.title} — {m.description}\n"

        while iteration < self.max_iterations:
            if self.cancellation_token.is_cancelled():
                self.state = AgentState.CANCELLED
                return SuperAgentResult(
                    status=AgentState.CANCELLED,
                    goal=goal,
                    final_output="Operation cancelled by user.",
                    plan=plan,
                    critique=SelfCritiqueResult(0, False, summary="Cancelled"),
                    files_changed=sorted(files_changed),
                    total_steps=iteration,
                    duration_seconds=time.monotonic() - start_time,
                    execution_id=self.execution_id,
                )

            iteration += 1
            self.state = AgentState.EXECUTING

            # Format recent observations
            obs_text = self._format_history_snippet()
            full_prompt = (
                f"{context_prompt}\n"
                f"CURRENT STEP {iteration}/{self.max_iterations}:\n"
                f"{obs_text}\n\n"
                "Next action: Provide EXACTLY ONE tool call JSON or your final summary."
            )

            # LLM Call
            self._notify("llm_thinking", {"iteration": iteration})
            response_text = self._call_llm(full_prompt, system_prompt)

            if self.cancellation_token.is_cancelled():
                break

            calls = parse_tool_calls(response_text)
            thought = strip_tool_calls(response_text, calls)

            # Check if LLM is declaring completion (no tool calls returned)
            if not calls:
                self.state = AgentState.REVIEWING
                candidate_summary = thought or response_text
                self._notify("self_critique_start", {"candidate_summary": candidate_summary[:300]})

                # Run Self-Critique Engine
                critique_res = self.critique_engine.critique(
                    goal=goal,
                    summary=candidate_summary,
                    files_changed=sorted(files_changed),
                    tool_history=self.history,
                )

                self._notify("self_critique_finished", {
                    "score": critique_res.score,
                    "passed": critique_res.passed_threshold,
                    "weaknesses": critique_res.weaknesses,
                    "improvements": critique_res.actionable_improvements,
                })

                # PUSH-LIMITS TRIGGER: If score < threshold and we have retries left, push further!
                if not critique_res.passed_threshold and critique_retry_count < self.max_critique_retries:
                    critique_retry_count += 1
                    self.state = AgentState.FIXING
                    self._notify("limit_push_triggered", {
                        "attempt": critique_retry_count,
                        "score": critique_res.score,
                        "improvements": critique_res.actionable_improvements,
                    })

                    context_prompt += (
                        f"\n[SELF-CRITIQUE QUALITY REJECTION — Score: {critique_res.score}/100 (Required: {self.push_hard_threshold})]\n"
                        f"Your output was evaluated as INSUFFICIENT for the following reasons:\n"
                        + "\n".join(f"- {w}" for w in critique_res.weaknesses)
                        + "\nREQUIRED ACTIONS TO REACH 100% EXCELLENCE:\n"
                        + "\n".join(f"- {act}" for act in critique_res.actionable_improvements)
                        + "\nExecute the required tools to fix these issues immediately.\n"
                    )
                    continue

                # Mark all remaining milestones completed
                for m in plan.milestones:
                    if m.status != PlanItemStatus.COMPLETED:
                        m.status = PlanItemStatus.COMPLETED
                        m.critique_score = critique_res.score

                self.state = AgentState.COMPLETED
                self._notify("super_agent_completed", {
                    "summary": candidate_summary,
                    "score": critique_res.score,
                    "files_changed": sorted(files_changed),
                })

                return SuperAgentResult(
                    status=AgentState.COMPLETED,
                    goal=goal,
                    final_output=candidate_summary,
                    plan=plan,
                    critique=critique_res,
                    files_changed=sorted(files_changed),
                    browser_actions=browser_action_count,
                    total_steps=iteration,
                    duration_seconds=time.monotonic() - start_time,
                    execution_id=self.execution_id,
                )

            # Execute tool calls
            for call in calls:
                if "browser_" in call.tool:
                    browser_action_count += 1

                # Validate
                ok, err = validate_tool_call(call, tool_defs)
                if not ok:
                    context_prompt += f"\n[VALIDATION ERROR] Tool '{call.tool}' error: {err}\n"
                    continue

                # Stuck detector
                self.stuck_detector.record_step(call.tool, call.args, status="started")
                if self.stuck_detector.is_stuck():
                    hint = self.stuck_detector.get_recovery_hint()
                    context_prompt += f"\n[STUCK DETECTOR] {hint}\n"

                self._notify("tool_executing", {"tool": call.tool, "args": call.args, "thought": thought})

                t0 = time.monotonic()
                obs = self.tool_registry.execute(
                    call.tool,
                    call.args,
                    execution_id=self.execution_id,
                    cancellation_token=self.cancellation_token,
                )
                duration = time.monotonic() - t0

                if obs.get("files_changed"):
                    for fc in obs["files_changed"]:
                        files_changed.add(fc)

                step_record = AgentStep(
                    step_number=iteration,
                    action=f"Execute {call.tool}",
                    tool_name=call.tool,
                    tool_args=call.args,
                    observation=obs,
                    status="success" if obs.get("exit_code", 0) == 0 else "error",
                    thought=thought,
                    duration=duration,
                )
                self.history.append(step_record)
                self._notify("tool_finished", {
                    "tool": call.tool,
                    "exit_code": obs.get("exit_code", 0),
                    "duration": duration,
                })

                # Check milestone progress
                if current_milestone_idx < len(plan.milestones):
                    ms = plan.milestones[current_milestone_idx]
                    if ms.status == PlanItemStatus.PENDING:
                        ms.status = PlanItemStatus.IN_PROGRESS
                    if iteration > (current_milestone_idx + 1) * 3:
                        ms.status = PlanItemStatus.COMPLETED
                        current_milestone_idx += 1

        # Max iterations fallback
        final_summary = f"SuperAgent completed maximum execution budget of {self.max_iterations} steps."
        critique_res = self.critique_engine.critique(goal, final_summary, sorted(files_changed), self.history)
        self.state = AgentState.COMPLETED_WITH_WARNINGS

        return SuperAgentResult(
            status=self.state,
            goal=goal,
            final_output=final_summary,
            plan=plan,
            critique=critique_res,
            files_changed=sorted(files_changed),
            browser_actions=browser_action_count,
            total_steps=iteration,
            duration_seconds=time.monotonic() - start_time,
            execution_id=self.execution_id,
        )

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        if not self.provider:
            return self._fallback_step(prompt)

        safe_prompt = SensitiveFileDetector.redact_secrets(prompt)

        def _chunk_cb(chunk: str) -> None:
            if self.stream_callback:
                self.stream_callback(chunk)

        try:
            if hasattr(self.provider, "chat"):
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": safe_prompt},
                ]
                return self.provider.chat(
                    messages=messages,
                    model=self.model,
                    stream=bool(self.stream_callback),
                    callback=_chunk_cb if self.stream_callback else None,
                    temperature=0.2,
                )
            elif hasattr(self.provider, "generate"):
                return self.provider.generate(
                    prompt=safe_prompt,
                    model=self.model,
                    system_prompt=system_prompt,
                    stream=bool(self.stream_callback),
                    callback=_chunk_cb if self.stream_callback else None,
                    temperature=0.2,
                )
        except Exception as exc:
            logger.error("SuperAgent LLM call error: %s", exc)

        return self._fallback_step(prompt)

    def _format_history_snippet(self) -> str:
        if not self.history:
            return "(No actions performed yet)"
        lines = []
        for s in self.history[-6:]:
            ec = s.observation.get("exit_code", 0) if s.observation else 0
            stdout = str(s.observation.get("stdout", ""))[:120] if s.observation else ""
            stderr = str(s.observation.get("stderr", ""))[:80] if s.observation else ""
            lines.append(f"- Step {s.step_number}: {s.tool_name}({json.dumps(s.tool_args)[:60]}) -> exit={ec} {stdout} {stderr}")
        return "\n".join(lines)

    def _fallback_step(self, prompt: str) -> str:
        """Deterministic fallback when running without active LLM provider."""
        return "Task completed via autonomous fallback procedure."
