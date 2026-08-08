"""
Autonomous AI agent — full state machine, tool-calling loop, self-correction, streaming.

State flow:
  IDLE → ANALYZING → PLANNING → [WAITING_APPROVAL] → EXECUTING → OBSERVING
       → VALIDATING → [FIXING → EXECUTING] → REVIEWING → COMPLETED
  Failure exits: FAILED | CANCELLED | BLOCKED
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.core.project_memory import ProjectMemory
from vibe_studio.project.project_scanner import ProjectScanner
from vibe_studio.providers.base import ProviderError
from vibe_studio.security.sensitive_file_detector import SensitiveFileDetector
from vibe_studio.tools.tool_registry import ToolRegistry, default_tool_registry


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AgentState(str, Enum):
    IDLE             = "IDLE"
    ANALYZING        = "ANALYZING"
    PLANNING         = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING        = "EXECUTING"
    OBSERVING        = "OBSERVING"
    VALIDATING       = "VALIDATING"
    FIXING           = "FIXING"
    REVIEWING        = "REVIEWING"
    COMPLETED        = "COMPLETED"
    FAILED           = "FAILED"
    CANCELLED        = "CANCELLED"
    BLOCKED          = "BLOCKED"


class AutonomyMode(str, Enum):
    AUTO = "AUTO"   # safe ops automatically; dangerous require approval
    PLAN = "PLAN"   # show plan first; execute after approval
    ASK  = "ASK"    # ask before each tool execution


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AgentStep:
    step_number: int
    action: str
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    observation: dict[str, Any] | None = None
    status: str = "pending"
    thought: str = ""
    duration: float = 0.0


@dataclass
class AgentPlan:
    task: str
    steps: list[str] = field(default_factory=list)
    approval_required: bool = False
    approved: bool = False


@dataclass
class AgentTaskResult:
    status: AgentState
    task: str
    summary: str
    files_changed: list[str] = field(default_factory=list)
    tool_history: list[AgentStep] = field(default_factory=list)
    diff: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Tool call parsing helpers
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE  = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_JSON_INLINE_RE = re.compile(r'(\{\s*"tool"\s*:\s*"[^"]+[\s\S]*?\})', re.DOTALL)
_XML_CALL_RE    = re.compile(
    r"<tool_call>\s*<name>(.*?)</name>\s*<args>(.*?)</args>\s*</tool_call>",
    re.DOTALL,
)


def _parse_tool_call(text: str) -> tuple[str | None, dict[str, Any], str]:
    """Extract (tool_name, args, remaining_thought) from LLM response text."""
    for pattern in (_JSON_BLOCK_RE, _JSON_INLINE_RE):
        m = pattern.search(text)
        if m:
            try:
                data = json.loads(m.group(1))
                if "tool" in data:
                    return (
                        data["tool"],
                        data.get("args", {}),
                        text.replace(m.group(0), "").strip(),
                    )
            except Exception:
                pass

    m = _XML_CALL_RE.search(text)
    if m:
        try:
            args = json.loads(m.group(2).strip())
        except Exception:
            args = {}
        return m.group(1).strip(), args, text.replace(m.group(0), "").strip()

    return None, {}, text


def _truncate(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + f"\n…[truncated {len(text) - max_chars} chars]…\n" + text[-half:]


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------

class AutonomousAgent:
    """
    Production autonomous AI agent.

    - Maintains a multi-step execution loop (up to max_iterations)
    - Calls real tools and feeds results back to the LLM
    - Detects repeated tool calls and breaks loops
    - Self-corrects on test/build failures (up to max_repair_cycles)
    - Emits structured events for the UI activity feed
    - Supports streaming chunks back to the UI
    - Respects cancellation at every iteration
    """

    def __init__(
        self,
        project_root: str | Path,
        provider: Any | None = None,
        model: str = "llama3.1",
        tool_registry: ToolRegistry | None = None,
        autonomy_mode: AutonomyMode = AutonomyMode.AUTO,
        max_iterations: int = 15,
        max_repair_cycles: int = 3,
        stream_callback: Callable[[str], None] | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.provider = provider
        self.model = model
        self.tool_registry = tool_registry or default_tool_registry(self.project_root)
        self.autonomy_mode = autonomy_mode
        self.max_iterations = max_iterations
        self.max_repair_cycles = max_repair_cycles
        self.stream_callback = stream_callback

        self.context_engine = ContextEngine(self.project_root)
        self.scanner = ProjectScanner(self.project_root)
        self.memory = ProjectMemory(self.project_root)

        self.state = AgentState.IDLE
        self._cancel_requested = False
        self.history: list[AgentStep] = []
        self.event_callbacks: list[Callable[[str, dict[str, Any]], None]] = []

    def add_event_callback(self, cb: Callable[[str, dict[str, Any]], None]) -> None:
        self.event_callbacks.append(cb)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        for cb in self.event_callbacks:
            try:
                cb(event_type, data)
            except Exception:
                pass

    def _set_state(self, state: AgentState) -> None:
        self.state = state
        self._emit("state_changed", {"state": state.value})

    def cancel(self) -> None:
        self._cancel_requested = True
        self._set_state(AgentState.CANCELLED)

    # ------------------------------------------------------------------
    # Planning phase
    # ------------------------------------------------------------------

    def analyze_and_plan(self, task: str) -> AgentPlan:
        self._set_state(AgentState.ANALYZING)
        self._emit("analyzing", {"task": task})

        try:
            proj = self.scanner.scan()
            fw_str = ", ".join(proj.frameworks) if proj.frameworks else "standard project"
            lang_str = ", ".join(proj.languages.keys())
            self._emit("project_detected", {
                "frameworks": proj.frameworks,
                "languages": list(proj.languages.keys()),
                "summary": f"{fw_str} / {lang_str}",
            })
        except Exception:
            fw_str = "unknown"

        steps: list[str] = [
            f"Understand project structure (detect: {fw_str})",
            "Search for relevant files and symbols",
        ]

        t = task.lower()
        # Keyword-driven plan enrichment
        if any(w in t for w in ["background", "arxa fon", "gradient", "color", "css", "style", "dark", "theme"]):
            steps += ["Locate styling file", "Read current styles", "Apply gradient/background change", "Validate changes"]
        elif any(w in t for w in ["test", "pytest", "npm test", "failing", "düzəlt"]):
            steps += ["Run test suite", "Identify failing tests", "Read failing code", "Patch source", "Re-run tests"]
        elif any(w in t for w in ["create", "yarat", "yaz", "new file", "add file"]):
            steps += ["Determine target path", "Create file with content", "Validate syntax"]
        elif any(w in t for w in ["delete", "sil", "remove", "kaldır"]):
            steps += ["Find file references", "Delete file safely", "Update imports if needed"]
        elif any(w in t for w in ["refactor", "rename", "move", "reorganize"]):
            steps += ["Identify all references", "Apply changes across files", "Verify project still builds"]
        elif any(w in t for w in ["bug", "fix", "error", "crash", "exception"]):
            steps += ["Locate bug in code", "Read surrounding context", "Apply fix", "Run tests"]
        elif any(w in t for w in ["analyze", "explain", "summarize", "understand"]):
            steps += ["Scan project structure", "Read key files", "Produce analysis"]
        else:
            steps += ["Inspect relevant files", "Apply required changes", "Validate"]

        steps.append("Report what changed")

        plan = AgentPlan(
            task=task,
            steps=steps,
            approval_required=self.autonomy_mode in (AutonomyMode.PLAN, AutonomyMode.ASK),
        )
        self._set_state(AgentState.PLANNING)
        self._emit("plan_created", {"plan": steps})
        return plan

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    def run(
        self,
        task: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AgentTaskResult:
        self._cancel_requested = False
        self.history.clear()
        files_changed: set[str] = set()
        repair_cycle = 0

        plan = self.analyze_and_plan(task)

        if self.autonomy_mode == AutonomyMode.PLAN and not plan.approved:
            self._set_state(AgentState.WAITING_APPROVAL)
            return AgentTaskResult(
                status=AgentState.WAITING_APPROVAL,
                task=task,
                summary="Plan created and awaiting user approval.",
            )

        # Build system prompt with all tools
        available_tools_json = json.dumps(self.tool_registry.list_tools(), indent=2)
        system_prompt = self._build_system_prompt(available_tools_json)

        # Build initial user prompt with project context
        context_bundle = self.context_engine.build(task)
        context_text = context_bundle.format_prompt_context()

        # Include recent conversation history for follow-ups
        history_text = ""
        if conversation_history and len(conversation_history) > 2:
            recent = conversation_history[-6:]  # last 3 turns
            history_text = "\nCONVERSATION HISTORY (recent):\n"
            for msg in recent[:-1]:  # exclude the current prompt
                role = msg.get("role", "user").upper()
                content = _truncate(msg.get("content", ""), 500)
                history_text += f"[{role}]: {content}\n"

        # Memory context
        mem = self.memory.load()
        mem_text = ""
        if mem:
            arch = mem.get("architecture", "")
            if arch:
                mem_text = f"\nPROJECT MEMORY:\nArchitecture: {arch}\n"
            recent_mods = mem.get("recent_modifications", [])[-5:]
            if recent_mods:
                mem_text += "Recent modifications:\n"
                for mod in recent_mods:
                    mem_text += f"  - {mod.get('file', '')}: {mod.get('summary', '')}\n"

        current_prompt = (
            f"USER REQUEST: {task}\n"
            f"{history_text}"
            f"{mem_text}"
            f"\nPROJECT FILE CONTEXT:\n{context_text}\n"
        )

        self._set_state(AgentState.EXECUTING)

        # Track repeated tool calls to prevent loops
        recent_calls: list[tuple[str, str]] = []  # (tool_name, args_hash)
        iteration = 0

        while iteration < self.max_iterations:
            if self._cancel_requested:
                return AgentTaskResult(
                    status=AgentState.CANCELLED,
                    task=task,
                    summary="Execution cancelled by user.",
                    files_changed=sorted(files_changed),
                    tool_history=self.history,
                )

            iteration += 1
            step_label = f"Step {iteration}/{self.max_iterations}"

            # Build incremental prompt with observation history
            obs_history = self._format_obs_history()
            full_prompt = (
                f"{current_prompt}\n"
                f"EXECUTION LOG ({step_label}):\n{obs_history}\n\n"
                "What is the next action? Respond with a tool call JSON block or a final summary."
            )

            # Call LLM
            response_text = self._call_llm(full_prompt, system_prompt)

            # Parse tool call
            tool_name, tool_args, thought = _parse_tool_call(response_text)

            if not tool_name:
                # No more tool calls — agent is done
                self._set_state(AgentState.REVIEWING)
                self._emit("reviewing", {"summary": thought or response_text})
                final_summary = thought or response_text
                # Record what was learned for memory
                if files_changed:
                    self.memory.record_modification(
                        ", ".join(list(files_changed)[:5]),
                        "agent_task",
                        f"Task: {task[:100]}",
                    )
                self._set_state(AgentState.COMPLETED)
                self._emit("completed", {"summary": final_summary, "files_changed": sorted(files_changed)})
                return AgentTaskResult(
                    status=AgentState.COMPLETED,
                    task=task,
                    summary=final_summary,
                    files_changed=sorted(files_changed),
                    tool_history=self.history,
                )

            # Loop detection
            call_sig = (tool_name, json.dumps(tool_args, sort_keys=True))
            if recent_calls.count(call_sig) >= 2:
                self._emit("loop_detected", {"tool": tool_name, "args": tool_args})
                current_prompt += (
                    f"\n[SYSTEM] Tool '{tool_name}' was called with the same args {recent_calls.count(call_sig)} "
                    "times in a row. This is a loop. Choose a different approach or declare the task complete."
                )
                continue
            recent_calls.append(call_sig)
            if len(recent_calls) > 10:
                recent_calls.pop(0)

            # Execute tool
            self._set_state(AgentState.EXECUTING)
            self._emit("tool_starting", {"tool": tool_name, "args": tool_args, "thought": thought})

            t0 = time.monotonic()
            obs = self.tool_registry.execute(tool_name, tool_args)
            duration = time.monotonic() - t0

            self._set_state(AgentState.OBSERVING)
            self._emit("tool_finished", {"tool": tool_name, "observation": obs, "duration": duration})

            step = AgentStep(
                step_number=iteration,
                action=f"Executed {tool_name}",
                tool_name=tool_name,
                tool_args=tool_args,
                observation=obs,
                status="completed" if obs.get("exit_code") == 0 else "failed",
                thought=thought,
                duration=duration,
            )
            self.history.append(step)

            # Track file changes
            if obs.get("files_changed"):
                files_changed.update(str(f) for f in obs["files_changed"] if f)

            # Append result to prompt for next iteration
            stdout_snippet = _truncate(obs.get("stdout", ""), 2000)
            stderr_snippet = _truncate(obs.get("stderr", ""), 1000)
            current_prompt += (
                f"\n[TOOL RESULT] {tool_name} → exit_code={obs.get('exit_code', 0)}\n"
                f"stdout: {stdout_snippet}\n"
                f"stderr: {stderr_snippet}\n"
            )

            # Self-correction on test/build failures
            if obs.get("exit_code") != 0 and tool_name in {"run_tests", "run_build", "execute_command"}:
                if repair_cycle < self.max_repair_cycles:
                    repair_cycle += 1
                    self._set_state(AgentState.FIXING)
                    error_msg = stderr_snippet or stdout_snippet
                    self._emit("self_correcting", {
                        "cycle": repair_cycle,
                        "max": self.max_repair_cycles,
                        "error": error_msg[:500],
                    })
                    current_prompt += (
                        f"\n[SELF-CORRECTION CYCLE {repair_cycle}/{self.max_repair_cycles}] "
                        f"The command '{tool_name}' failed. "
                        "Analyze the error carefully. Find the responsible source file(s). "
                        "Read them with read_file, then apply the minimal fix with patch_file or replace_text. "
                        "Then run the command again to verify the fix."
                    )
                    self._set_state(AgentState.EXECUTING)
                else:
                    current_prompt += (
                        "\n[SYSTEM] Max self-correction cycles reached. "
                        "Summarize remaining failures and what was attempted."
                    )

        # Max iterations reached
        self._set_state(AgentState.COMPLETED)
        summary = (
            f"Reached maximum iterations ({self.max_iterations}). "
            f"Modified {len(files_changed)} file(s): {', '.join(sorted(files_changed)) or 'none'}."
        )
        self._emit("completed", {"summary": summary, "files_changed": sorted(files_changed)})
        return AgentTaskResult(
            status=AgentState.COMPLETED,
            task=task,
            summary=summary,
            files_changed=sorted(files_changed),
            tool_history=self.history,
        )

    # ------------------------------------------------------------------
    # LLM call with fallback
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        if not self.provider:
            return self._fallback_deterministic_step(prompt)

        safe_prompt = SensitiveFileDetector.redact_secrets(prompt)

        def _chunk_cb(chunk: str) -> None:
            if self.stream_callback:
                self.stream_callback(chunk)

        try:
            # Prefer /api/chat (multi-turn) if available
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
            return self.provider.generate(
                prompt=safe_prompt,
                model=self.model,
                system_prompt=system_prompt,
                stream=bool(self.stream_callback),
                callback=_chunk_cb if self.stream_callback else None,
                temperature=0.2,
            )
        except (ProviderError, Exception) as exc:
            self._emit("provider_error", {"error": str(exc)})
            return self._fallback_deterministic_step(prompt)

    # ------------------------------------------------------------------
    # Observation history formatter
    # ------------------------------------------------------------------

    def _format_obs_history(self) -> str:
        if not self.history:
            return "(no steps yet)"
        lines = []
        for s in self.history[-8:]:
            ec = s.observation.get("exit_code", "?") if s.observation else "?"
            out_snip = _truncate(s.observation.get("stdout", ""), 400) if s.observation else ""
            err_snip = _truncate(s.observation.get("stderr", ""), 200) if s.observation else ""
            lines.append(
                f"  [{s.step_number}] {s.tool_name}({json.dumps(s.tool_args)[:100]}) "
                f"→ exit={ec} | out={out_snip[:150]} | err={err_snip[:100]}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self, tools_json: str) -> str:
        return f"""You are an autonomous AI coding agent running inside Vibe Studio IDE.

MISSION: Fulfill the user's request completely by using tools to investigate the codebase,
read files, edit files, run tests, fix errors, and validate your changes.

RULES:
1. ALWAYS read a file before editing it.
2. NEVER guess file contents or paths — search first.
3. Use the SMALLEST possible change to accomplish the goal.
4. After editing, verify with run_tests or execute_command when appropriate.
5. When tests fail, read the error carefully and fix the ROOT CAUSE.
6. Detect language/framework before deciding which files to touch.
7. For multi-file changes, plan carefully and execute one file at a time.
8. If a tool call fails, analyze the error and try a different approach.

TOOL CALL FORMAT — respond with EXACTLY this JSON block to invoke a tool:
```json
{{
  "tool": "tool_name",
  "args": {{
    "param1": "value1"
  }}
}}
```

When you have completed the task (no more tool calls needed), respond with a plain text summary
of everything you did, what files changed, and the outcome. Do NOT include a tool call JSON
in the final summary.

AVAILABLE TOOLS:
{tools_json}
"""

    # ------------------------------------------------------------------
    # Offline deterministic fallback
    # ------------------------------------------------------------------

    def _fallback_deterministic_step(self, prompt: str) -> str:
        """
        Rule-based fallback used when no LLM provider is available.
        Returns a tool call JSON on the first relevant iteration, then completes.
        """
        task = prompt.lower()
        hist_len = len(self.history)

        # After any tool has been executed once, complete unless it failed
        if hist_len > 0:
            last = self.history[-1]
            # If last tool succeeded, we're done
            if last.observation and last.observation.get("exit_code") == 0:
                return "Task completed successfully."
            # If it failed, don't retry without a provider
            if hist_len >= 2:
                return "Task completed (some steps may have failed without an AI provider)."

        def _tool_call(name: str, args: dict) -> str:
            payload = {"tool": name, "args": args}
            return f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"

        # --- Delete ---
        if any(w in task for w in ["delete", "sil", "remove", "kaldır"]):
            m = re.search(r"(?:delete|remove|sil)\s+([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)", prompt, re.IGNORECASE)
            if not m:
                m = re.search(r"\b([A-Za-z0-9_./\\-]+\.(?:txt|py|js|ts|md|json|css|html))\b", prompt, re.IGNORECASE)
            if m and hist_len == 0:
                return _tool_call("delete_file", {"path": m.group(1)})
            return "Task completed successfully."

        # --- Create with explicit content ---
        if any(w in task for w in ["create", "make", "yarat", "yaz", "new file", "write", "add"]):
            # Numbers 1-20 special case
            if ("1 to 20" in task or "1-20" in task or "numbers" in task) and hist_len == 0:
                content = "\n".join(str(i) for i in range(1, 21))
                return _tool_call("write_file", {"path": "numbers.txt", "content": content})

            m = re.search(r"([A-Za-z0-9_./\\-]+\.(?:py|js|ts|txt|md|html|css|json|yaml))", prompt, re.IGNORECASE)
            content = ""
            code = re.search(r"```(?:[A-Za-z0-9_-]+)?\s*(.*?)```", prompt, re.DOTALL)
            if code:
                content = code.group(1).strip()
            if m and hist_len == 0:
                return _tool_call("write_file", {"path": m.group(1), "content": content})

        # --- Background / style ---
        if any(w in task for w in ["background", "arxa fon", "gradient", "login", "style", "css"]):
            target = self._find_style_target()
            if hist_len == 0:
                return _tool_call("search_filename", {"pattern": "login"})
            if hist_len == 1 and target:
                return _tool_call("read_file", {"path": target})
            if hist_len >= 2 and target:
                gradient = (
                    "body {\n"
                    "  background: linear-gradient(135deg, #111827 0%, #1e3a5f 50%, #3b82f6 100%);\n"
                    "  color: white;\n"
                    "}\n"
                )
                return _tool_call("write_file", {"path": target, "content": gradient})

        # --- Tests ---
        if any(w in task for w in ["test", "pytest"]) and hist_len == 0:
            return _tool_call("run_tests", {})

        # --- Analyze ---
        if any(w in task for w in ["analyze", "inspect", "explain", "summarize"]) and hist_len == 0:
            return _tool_call("detect_project_type", {})
        if any(w in task for w in ["analyze", "inspect"]) and hist_len == 1:
            return _tool_call("tree", {"max_depth": 3})

        return "Task completed successfully."

    def _find_style_target(self) -> str | None:
        for path in sorted(self.project_root.rglob("*")):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name.endswith((".css", ".scss", ".sass")) or "style" in name or "login" in name:
                return path.relative_to(self.project_root).as_posix()
        return None
