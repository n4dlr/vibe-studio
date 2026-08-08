"""
Autonomous AI agent — production-hardened state machine with:
  - Robust multi-format tool-call parsing (parser module)
  - Schema validation before execution
  - File conflict detection (read-then-write integrity)
  - Smart output truncation (preserves errors)
  - Error classification + deduplication (no infinite repair loops)
  - Provider capability detection (native vs. compatibility tool-call protocol)
  - Model-aware context budgeting
  - Conversation continuity across turns

State flow:
  IDLE → ANALYZING → PLANNING → [WAITING_APPROVAL] → EXECUTING → OBSERVING
       → VALIDATING → [FIXING → EXECUTING] → REVIEWING → COMPLETED
  Exits: FAILED | CANCELLED | BLOCKED
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vibe_studio.agents.output_processor import (
    ErrorCategory,
    ErrorInfo,
    ErrorTracker,
    classify_error,
    extract_errors,
    truncate_output,
)
from vibe_studio.agents.tool_call_parser import (
    ParsedToolCall,
    parse_tool_calls,
    strip_tool_calls,
    validate_tool_call,
)
from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.core.project_memory import ProjectMemory
from vibe_studio.project.project_scanner import ProjectScanner
from vibe_studio.providers.base import ProviderError
from vibe_studio.providers.capability_detector import (
    ModelCapabilities,
    adapt_context_to_model,
    detect_capabilities,
)
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
    AUTO = "AUTO"   # safe ops auto; dangerous require approval
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
# Agent
# ---------------------------------------------------------------------------

class AutonomousAgent:
    """
    Production autonomous AI agent.

    Key improvements over previous version:
      - Uses tool_call_parser module (multi-format, schema validation)
      - Detects file conflicts before applying patches
      - Classifies and deduplicates errors (ErrorTracker)
      - Adapts context budget to model capabilities
      - Adapts tool-call protocol to model capabilities
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

        # Capability detection (lazy — done once per run)
        self._capabilities: ModelCapabilities | None = None

        # Error deduplication tracker (reset each run)
        self._error_tracker = ErrorTracker(max_repeats=2)

        # File read-hashes for conflict detection: path → hash at time of read
        self._read_hashes: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

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
            f"Understand project structure (detected: {fw_str})",
            "Search for relevant files and symbols",
        ]
        t = task.lower()
        if any(w in t for w in ["background", "arxa fon", "gradient", "color", "css", "style", "dark", "theme"]):
            steps += ["Locate styling file", "Read current styles", "Apply gradient/background change", "Validate changes"]
        elif any(w in t for w in ["test", "pytest", "npm test", "failing", "düzəlt"]):
            steps += ["Run test suite", "Identify failing tests", "Read failing code", "Patch source", "Re-run tests"]
        elif any(w in t for w in ["create", "yarat", "yaz", "new file", "add file"]):
            steps += ["Determine target path", "Create file with content", "Validate syntax"]
        elif any(w in t for w in ["delete", "sil", "remove", "kaldır"]):
            steps += ["Find file references", "Warn if referenced", "Delete file safely"]
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
        self._read_hashes.clear()
        self._error_tracker.reset()
        files_changed: set[str] = set()
        repair_cycle = 0

        plan = self.analyze_and_plan(task)
        if self._cancel_requested:
            return AgentTaskResult(status=AgentState.CANCELLED, task=task, summary="Cancelled.")

        if self.autonomy_mode == AutonomyMode.PLAN and not plan.approved:
            self._set_state(AgentState.WAITING_APPROVAL)
            return AgentTaskResult(
                status=AgentState.WAITING_APPROVAL,
                task=task,
                summary="Plan created and awaiting user approval.",
            )

        # Detect model capabilities once
        self._capabilities = detect_capabilities(self.model)
        if self._capabilities.notes:
            self._emit("capability_detected", {
                "model": self.model,
                "native_tools": self._capabilities.native_tool_calling,
                "context_window": self._capabilities.context_window,
                "notes": self._capabilities.notes,
            })

        # Adapt token budget to model
        raw_budget = 16000
        token_budget = adapt_context_to_model(raw_budget, self._capabilities)

        tool_defs = self.tool_registry.list_tools()
        system_prompt = self._build_system_prompt(tool_defs)

        # Build context
        context_bundle = self.context_engine.build(task, token_budget=token_budget)
        context_text = context_bundle.format_prompt_context()

        # Conversation history (recent turns for follow-up understanding)
        history_text = ""
        if conversation_history and len(conversation_history) > 2:
            recent = conversation_history[-6:]
            history_text = "\nCONVERSATION HISTORY (recent):\n"
            for msg in recent[:-1]:
                role = msg.get("role", "user").upper()
                content = _trunc(msg.get("content", ""), 500)
                history_text += f"[{role}]: {content}\n"

        # Project memory
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

        # Loop-detection: track (tool, args_hash) pairs
        recent_calls: list[tuple[str, str]] = []
        iteration = 0

        while iteration < self.max_iterations:
            if self._cancel_requested:
                return AgentTaskResult(
                    status=AgentState.CANCELLED, task=task,
                    summary="Execution cancelled by user.",
                    files_changed=sorted(files_changed), tool_history=self.history,
                )

            iteration += 1
            obs_history = self._format_obs_history()
            full_prompt = (
                f"{current_prompt}\n"
                f"EXECUTION LOG (step {iteration}/{self.max_iterations}):\n{obs_history}\n\n"
                "What is the next action? Respond with a tool call JSON block or a final summary."
            )

            response_text = self._call_llm(full_prompt, system_prompt)

            if self._cancel_requested:
                return AgentTaskResult(
                    status=AgentState.CANCELLED, task=task,
                    summary="Execution cancelled by user.",
                    files_changed=sorted(files_changed), tool_history=self.history,
                )

            # Parse ALL tool calls from this response
            calls = parse_tool_calls(response_text)
            thought = strip_tool_calls(response_text, calls)

            if not calls:
                # No tool calls → agent is done
                self._set_state(AgentState.REVIEWING)
                self._emit("reviewing", {"summary": thought or response_text})
                final_summary = thought or response_text
                if files_changed:
                    self.memory.record_modification(
                        ", ".join(list(files_changed)[:5]),
                        "agent_task",
                        f"Task: {task[:100]}",
                    )
                self._set_state(AgentState.COMPLETED)
                self._emit("completed", {"summary": final_summary, "files_changed": sorted(files_changed)})
                return AgentTaskResult(
                    status=AgentState.COMPLETED, task=task,
                    summary=final_summary,
                    files_changed=sorted(files_changed), tool_history=self.history,
                )

            # Execute each tool call in sequence
            for call in calls:
                if self._cancel_requested:
                    break

                # Schema validation
                ok, err = validate_tool_call(call, tool_defs)
                if not ok:
                    self._emit("tool_validation_failed", {"tool": call.tool, "error": err})
                    current_prompt += f"\n[VALIDATION ERROR] {err}\nFix the tool call and try again."
                    continue

                # Loop detection
                call_sig = (call.tool, json.dumps(call.args, sort_keys=True))
                if recent_calls.count(call_sig) >= 2:
                    self._emit("loop_detected", {"tool": call.tool, "args": call.args})
                    current_prompt += (
                        f"\n[SYSTEM] Tool '{call.tool}' called with identical args "
                        f"{recent_calls.count(call_sig)} times. Choose a different approach."
                    )
                    continue
                recent_calls.append(call_sig)
                if len(recent_calls) > 12:
                    recent_calls.pop(0)

                # Conflict detection for read_file — record hash
                if call.tool == "read_file" and "path" in call.args:
                    self._record_read_hash(call.args["path"])

                # Conflict detection for patch/write — check if file changed
                if call.tool in {"patch_file", "replace_text", "write_file"} and "path" in call.args:
                    conflict = self._check_conflict(call.args["path"])
                    if conflict:
                        self._emit("conflict_detected", {"path": call.args["path"]})
                        current_prompt += (
                            f"\n[CONFLICT] File '{call.args['path']}' was modified externally "
                            "since it was read. Re-reading now before patching."
                        )
                        self._record_read_hash(call.args["path"])
                        # Re-read the file and inject current content
                        try:
                            fresh = self.tool_registry.execute("read_file", {"path": call.args["path"]})
                            current_prompt += f"\nFRESH CONTENT:\n{truncate_output(fresh.get('stdout', ''), 2000)}"
                        except Exception:
                            pass
                        continue

                # Execute
                self._set_state(AgentState.EXECUTING)
                self._emit("tool_starting", {"tool": call.tool, "args": call.args, "thought": thought})

                t0 = time.monotonic()
                obs = self.tool_registry.execute(call.tool, call.args)
                duration = time.monotonic() - t0

                self._set_state(AgentState.OBSERVING)
                self._emit("tool_finished", {"tool": call.tool, "observation": obs, "duration": duration})

                step = AgentStep(
                    step_number=iteration,
                    action=f"Executed {call.tool}",
                    tool_name=call.tool,
                    tool_args=call.args,
                    observation=obs,
                    status="completed" if obs.get("exit_code") == 0 else "failed",
                    thought=thought,
                    duration=duration,
                )
                self.history.append(step)

                if obs.get("files_changed"):
                    files_changed.update(str(f) for f in obs["files_changed"] if f)

                # After a read_file, record the hash for conflict detection
                if call.tool == "read_file" and "path" in call.args and obs.get("exit_code") == 0:
                    path_key = call.args["path"]
                    content = obs.get("stdout", "")
                    self._read_hashes[path_key] = self.tool_registry.patch_tools._hash(content)

                # Truncate output before feeding back
                stdout_snip = truncate_output(obs.get("stdout", ""), 2000)
                stderr_snip = truncate_output(obs.get("stderr", ""), 1000)
                current_prompt += (
                    f"\n[TOOL RESULT] {call.tool} → exit={obs.get('exit_code', 0)}\n"
                    f"stdout: {stdout_snip}\nstderr: {stderr_snip}\n"
                )

                # Self-correction on failures
                if obs.get("exit_code") != 0 and call.tool in {
                    "run_tests", "run_build", "execute_command", "run_linter"
                }:
                    combined_err = (obs.get("stderr") or "") + (obs.get("stdout") or "")
                    errors = extract_errors(combined_err)
                    primary_error = errors[0] if errors else ErrorInfo(
                        category=classify_error(combined_err),
                        message=combined_err[:200],
                    )

                    if self._error_tracker.is_stuck(primary_error):
                        # Already tried this error — stop banging head
                        stuck_summary = self._error_tracker.summary()
                        current_prompt += (
                            f"\n[BLOCKED] Error '{primary_error.fingerprint}' seen "
                            f"{self._error_tracker.max_repeats} times. {stuck_summary}\n"
                            "Explain what you tried and why it failed, then declare the task complete."
                        )
                    elif repair_cycle < self.max_repair_cycles:
                        repair_cycle += 1
                        self._error_tracker.record(primary_error, action=f"{call.tool}:{call.args}")
                        self._set_state(AgentState.FIXING)
                        self._emit("self_correcting", {
                            "cycle": repair_cycle,
                            "max": self.max_repair_cycles,
                            "category": primary_error.category.value,
                            "error": primary_error.message[:500],
                            "file": primary_error.file,
                        })
                        repair_hint = _repair_hint(primary_error)
                        current_prompt += (
                            f"\n[SELF-CORRECTION {repair_cycle}/{self.max_repair_cycles}] "
                            f"Error category: {primary_error.category.value}. "
                            f"{repair_hint}"
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
            status=AgentState.COMPLETED, task=task, summary=summary,
            files_changed=sorted(files_changed), tool_history=self.history,
        )

    # ------------------------------------------------------------------
    # Conflict detection helpers
    # ------------------------------------------------------------------

    def _record_read_hash(self, path: str) -> None:
        """Record the hash of a file at the time it was read."""
        try:
            target = self.tool_registry.patch_tools._resolve(path)
            if target.exists():
                content = target.read_text(encoding="utf-8", errors="replace")
                self._read_hashes[path] = self.tool_registry.patch_tools._hash(content)
        except Exception:
            pass

    def _check_conflict(self, path: str) -> bool:
        """Return True if the file changed since it was last read by the agent."""
        if path not in self._read_hashes:
            return False
        return self.tool_registry.patch_tools.check_conflict(path, self._read_hashes[path])

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        if not self.provider:
            return self._fallback_deterministic_step(prompt)

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
            out = _trunc(s.observation.get("stdout", ""), 200) if s.observation else ""
            err = _trunc(s.observation.get("stderr", ""), 100) if s.observation else ""
            lines.append(
                f"  [{s.step_number}] {s.tool_name}({json.dumps(s.tool_args)[:80]}) "
                f"→ exit={ec}"
                + (f" | {out[:120]}" if out else "")
                + (f" | ERR:{err[:80]}" if err else "")
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self, tool_defs: list[dict[str, Any]]) -> str:
        tools_json = json.dumps(tool_defs, indent=2)
        caps = self._capabilities
        protocol_note = ""
        if caps and caps.native_tool_calling:
            protocol_note = "This model supports native tool calling. You may also use the JSON block format below."
        else:
            protocol_note = "This model uses compatibility mode. Always use the JSON block format to call tools."

        return f"""You are an autonomous AI coding agent inside Vibe Studio IDE.
{protocol_note}

MISSION: Fulfill the user's request completely by using tools to investigate,
read files, edit files, run tests, fix errors, and validate changes.

STRICT RULES:
1. ALWAYS read_file before editing — never guess file content.
2. NEVER guess file paths — use search_filename or search_text first.
3. Use the SMALLEST possible change to accomplish the goal.
4. After editing, verify with run_tests or execute_command.
5. When tests fail, read the error carefully, find the ROOT CAUSE, fix it.
6. For CSS/style changes: read_file first, then patch_file with exact replacement.
7. If patch_file fails, re-read the file to get the current exact content.
8. Declare task complete only when you have verified the result.

TOOL CALL FORMAT (use EXACTLY this):
```json
{{
  "tool": "tool_name",
  "args": {{
    "param": "value"
  }}
}}
```

For a final summary (no more tool calls), respond in plain text only.

AVAILABLE TOOLS:
{tools_json}
"""

    # ------------------------------------------------------------------
    # Offline deterministic fallback (no LLM provider)
    # ------------------------------------------------------------------

    def _fallback_deterministic_step(self, prompt: str) -> str:
        """Rule-based fallback — handles common patterns without an LLM."""
        task = prompt.lower()
        hist_len = len(self.history)

        # After a successful tool call, declare completion
        if hist_len > 0:
            last = self.history[-1]
            if last.observation and last.observation.get("exit_code") == 0:
                return "Task completed successfully."
            if hist_len >= 2:
                return "Task completed (some steps may have failed without an AI provider)."

        def _tc(name: str, args: dict) -> str:
            return f"```json\n{json.dumps({'tool': name, 'args': args}, ensure_ascii=False)}\n```"

        # Delete
        if any(w in task for w in ["delete", "sil", "remove", "kaldır"]):
            import re
            m = re.search(r"(?:delete|remove|sil)\s+([\w./\\-]+\.\w+)", prompt, re.IGNORECASE)
            if not m:
                m = re.search(r"\b([\w./\\-]+\.(?:txt|py|js|ts|md|json|css|html))\b", prompt, re.IGNORECASE)
            if m and hist_len == 0:
                return _tc("delete_file", {"path": m.group(1)})
            return "Task completed successfully."

        # Create with numbers
        if any(w in task for w in ["create", "make", "yarat", "yaz", "new file", "write", "add"]):
            if ("1 to 20" in task or "1-20" in task or "numbers" in task) and hist_len == 0:
                content = "\n".join(str(i) for i in range(1, 21))
                return _tc("write_file", {"path": "numbers.txt", "content": content})
            import re
            m = re.search(r"([\w./\\-]+\.(?:py|js|ts|txt|md|html|css|json|yaml))", prompt, re.IGNORECASE)
            content = ""
            code = re.search(r"```(?:[A-Za-z0-9_-]+)?\s*(.*?)```", prompt, re.DOTALL)
            if code:
                content = code.group(1).strip()
            if m and hist_len == 0:
                return _tc("write_file", {"path": m.group(1), "content": content})

        # Style / background
        if any(w in task for w in ["background", "arxa fon", "gradient", "login", "style", "css"]):
            target = self._find_style_target()
            if hist_len == 0:
                return _tc("search_filename", {"pattern": "login"})
            if hist_len == 1 and target:
                return _tc("read_file", {"path": target})
            if hist_len >= 2 and target:
                gradient = (
                    "body {\n"
                    "  background: linear-gradient(135deg, #111827 0%, #1e3a5f 50%, #3b82f6 100%);\n"
                    "  color: white;\n"
                    "}\n"
                )
                return _tc("write_file", {"path": target, "content": gradient})

        # Tests
        if any(w in task for w in ["test", "pytest"]) and hist_len == 0:
            return _tc("run_tests", {})

        # Analyze
        if any(w in task for w in ["analyze", "inspect", "explain", "summarize"]) and hist_len == 0:
            return _tc("detect_project_type", {})
        if any(w in task for w in ["analyze", "inspect"]) and hist_len == 1:
            return _tc("tree", {"max_depth": 3})

        return "Task completed successfully."

    def _find_style_target(self) -> str | None:
        for path in sorted(self.project_root.rglob("*")):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name.endswith((".css", ".scss", ".sass")) or "style" in name or "login" in name:
                return path.relative_to(self.project_root).as_posix()
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trunc(text: str, max_chars: int = 2000) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + f"\n…[{len(text) - max_chars} chars]…\n" + text[-half:]


def _repair_hint(error: ErrorInfo) -> str:
    hints = {
        ErrorCategory.SYNTAX: (
            "Fix the syntax error in the file indicated. "
            "Read the file, locate the exact bad line, use patch_file to fix it."
        ),
        ErrorCategory.TYPE: (
            "Fix the type error. Read the file, check the function signature and call sites."
        ),
        ErrorCategory.TEST: (
            "Read the failing test and the source it tests. "
            "Fix the source code, not the test, unless the test is wrong."
        ),
        ErrorCategory.BUILD: (
            "Read the build error carefully. Check imports and package.json/Cargo.toml/etc."
        ),
        ErrorCategory.DEPENDENCY: (
            "The module is missing. Check if it needs to be installed or if the import path is wrong."
        ),
        ErrorCategory.LINT: (
            "Fix the lint error in the reported file/line. Use patch_file for minimal change."
        ),
        ErrorCategory.CONFIG: (
            "Check the configuration file for syntax errors or missing required fields."
        ),
        ErrorCategory.RUNTIME: (
            "Read the traceback carefully. Find the source file, read it, fix the runtime error."
        ),
        ErrorCategory.PERMISSION: (
            "Permission denied. Check if the file/directory is accessible."
        ),
        ErrorCategory.NETWORK: (
            "Network error. Check connection or retry."
        ),
    }
    base = hints.get(error.category, "Analyze the error, read the relevant file, apply a minimal fix.")
    if error.file:
        base += f" Target file: {error.file}"
        if error.line:
            base += f" line {error.line}"
    base += " Then re-run to verify."
    return base
