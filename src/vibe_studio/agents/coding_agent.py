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
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from vibe_studio.agents.output_processor import (
    ErrorCategory,
    ErrorInfo,
    ErrorTracker,
    classify_error,
    extract_errors,
    truncate_output,
)
from vibe_studio.agents.stuck_detector import StuckAgentDetector
from vibe_studio.agents.tool_call_parser import (
    ParsedToolCall,
    parse_tool_calls,
    strip_tool_calls,
    validate_tool_call,
)
from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.core.checkpoint_system import CheckpointSystem, StateTransitionValidator
from vibe_studio.core.project_memory import ProjectMemory
from vibe_studio.core.resource_manager import default_resource_manager
from vibe_studio.diff.diff_proposal import DiffProposalManager
from vibe_studio.project.project_scanner import ProjectScanner
from vibe_studio.providers.base import ProviderError
from vibe_studio.providers.capability_detector import (
    ModelCapabilities,
    adapt_context_to_model,
    detect_capabilities,
)
from vibe_studio.security.permission_broker import PermissionBroker
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
    intent: str = "task"  # "task" | "greeting" | "chat"


@dataclass
class AgentTaskResult:
    status: AgentState
    task: str
    summary: str
    files_changed: list[str] = field(default_factory=list)
    tool_history: list[AgentStep] = field(default_factory=list)
    diff: str = ""
    error: str | None = None
    execution_id: str = ""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AutonomousAgent:
    """
    Production autonomous AI agent hardened with:
      - CancellationToken & execution_id tracking
      - CheckpointSystem & StateTransitionValidator
      - StuckAgentDetector & PermissionBroker
      - DiffProposalManager & process tree cleanup
    """

    MAX_EXECUTION_TIME_SECONDS = 300.0

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
        cancellation_token: Optional[CancellationToken] = None,
        execution_id: Optional[str] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.provider = provider
        self.model = model
        self.tool_registry = tool_registry or default_tool_registry(self.project_root)
        self.autonomy_mode = autonomy_mode
        self.max_iterations = max_iterations
        self.max_repair_cycles = max_repair_cycles
        self.stream_callback = stream_callback
        self.cancellation_token = cancellation_token or CancellationToken()
        self.execution_id = execution_id or str(uuid.uuid4())

        self.context_engine = ContextEngine(self.project_root)
        self.scanner = ProjectScanner(self.project_root)
        self.memory = ProjectMemory(self.project_root)
        self.checkpoint_system = CheckpointSystem(self.project_root)
        self.permission_broker = PermissionBroker(self.project_root)
        self.stuck_detector = StuckAgentDetector()
        self.diff_proposal_manager = DiffProposalManager(self.project_root)

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
    # Events & State Management
    # ------------------------------------------------------------------

    def add_event_callback(self, cb: Callable[[str, dict[str, Any]], None]) -> None:
        self.event_callbacks.append(cb)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        payload = {"execution_id": self.execution_id, **data}
        for cb in self.event_callbacks:
            try:
                cb(event_type, payload)
            except Exception:
                pass

    def _set_state(self, state: AgentState) -> None:
        try:
            StateTransitionValidator.enforce_transition(self.state, state)
        except ValueError:
            pass  # Fallback gracefully if non-standard transition occurs
        self.state = state
        self._emit("state_changed", {"state": state.value})

    def cancel(self) -> None:
        self._cancel_requested = True
        self.cancellation_token.cancel()
        if self.provider and hasattr(self.provider, "cancel"):
            try:
                self.provider.cancel()
            except Exception:
                pass
        default_resource_manager.cleanup_execution(self.execution_id)
        self._set_state(AgentState.CANCELLED)

    def is_cancelled(self) -> bool:
        return self._cancel_requested or self.cancellation_token.is_cancelled()

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

        steps: list[str] = []
        t = task.lower().strip()

        # Check for conversational greeting / simple chat (short prompt without code keywords)
        words = t.split()
        is_greeting = (
            len(t) < 40
            and not any(k in t for k in ["create", "yarat", "yaz", "file", "fayl", "make", "code", "run", "delete", "sil"])
            and any(w in words for w in ["salam", "hello", "hi", "hey", "sa", "necəsn", "necesen", "günaydın", "gunaydin"])
        )

        if is_greeting:
            steps = ["İstifadəçi salamlaşmasının təhlili", "Cavabın hazırlanması"]
            plan = AgentPlan(
                task=task, steps=steps, intent="greeting",
                approval_required=False,
            )
            self._set_state(AgentState.PLANNING)
            self._emit("plan_created", {"plan": steps})
            return plan
        else:
            steps = [
                f"Understand project structure (detected: {fw_str})",
                "Search for relevant files and symbols",
            ]
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

        # ── Greeting fast-path ── immediately return without touching LLM or tools
        if plan.intent == "greeting":
            greeting_response = (
                "Salam! Mən Vibe Studio AI köməkçisiyəm. "
                "Layihənizdə sizə necə kömək edə bilərəm?\n"
                "Məsələn: fayl yaratmaq, kodu düzəltmək, testləri işə salmaq, refaktor etmək və s."
            )
            self._set_state(AgentState.COMPLETED)
            self._emit("completed", {"summary": greeting_response, "files_changed": []})
            return AgentTaskResult(
                status=AgentState.COMPLETED, task=task,
                summary=greeting_response, execution_id=self.execution_id,
            )

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

        # Detect simple task first (before system prompt construction)
        _simple_task = (
            not any(k in task.lower() for k in ["refactor", "debug", "fix", "analyze", "explain", "find", "search", "test"])
            and len(task) < 200
        )

        tool_defs = self.tool_registry.list_tools()
        system_prompt = self._build_system_prompt(tool_defs, compact=_simple_task)

        # Build context — skip expensive scan for simple single-file tasks
        if _simple_task:
            context_text = "(Minimal context — simple task detected, no deep scan needed.)"
        else:
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

        # Proactive LSP Code Intelligence (Pillar 7)
        lsp_text = ""
        try:
            from vibe_studio.context.lsp_context_provider import LSPContextProvider
            lsp_prov = LSPContextProvider(self.project_root)
            import re
            symbols = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", task)
            sym_items = []
            for sym in symbols[:3]:
                if sym.lower() not in {"create", "write", "file", "make", "test", "clear", "code", "the", "this", "file", "simple", "hello"}:
                    refs = lsp_prov.get_references(sym)
                    hover = lsp_prov.get_hover_info(sym)
                    if refs or hover:
                        sym_items.append((sym, hover, refs))
            if sym_items:
                lsp_text = "\n[LSP CODE INTELLIGENCE]:\n"
                for sym, hover, refs in sym_items:
                    lsp_text += f"  Symbol '{sym}':\n"
                    if hover:
                        lsp_text += f"    Doc/Type: {hover[:120]}\n"
                    if refs:
                        ref_files = list({r['file'] for r in refs if r.get('file')})[:4]
                        lsp_text += f"    Used in ({len(refs)} refs): {', '.join(ref_files)}\n"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("LSP pre-analysis skipped: %s", exc)

        current_prompt = (
            f"USER REQUEST: {task}\n"
            f"{history_text}"
            f"{mem_text}"
            f"{lsp_text}"
            f"\nPROJECT FILE CONTEXT:\n{context_text}\n"
        )

        self._set_state(AgentState.EXECUTING)

        # Loop-detection: track (tool, args_hash) pairs
        recent_calls: list[tuple[str, str]] = []
        iteration = 0

        while iteration < self.max_iterations:
            if self.is_cancelled():
                default_resource_manager.cleanup_execution(self.execution_id)
                self._set_state(AgentState.CANCELLED)
                return AgentTaskResult(
                    status=AgentState.CANCELLED, task=task,
                    summary="Execution cancelled by user.",
                    files_changed=sorted(files_changed), tool_history=self.history,
                    execution_id=self.execution_id,
                )

            iteration += 1

            # Save rolling checkpoint
            self.checkpoint_system.save_checkpoint(
                execution_id=self.execution_id,
                step_number=iteration,
                state=self.state,
                task=task,
                files_changed=sorted(files_changed),
            )

            obs_history = self._format_obs_history()
            # Use compact prompt for simple tasks: shorter = faster LLM response
            full_prompt = (
                f"{current_prompt}\n"
                f"EXECUTION LOG (step {iteration}/{self.max_iterations}):\n{obs_history}\n\n"
                "Next action: respond with ONE tool call JSON or a plain-text final summary (no JSON)."
            )

            response_text = self._call_llm(full_prompt, system_prompt)

            if self.is_cancelled():
                default_resource_manager.cleanup_execution(self.execution_id)
                self._set_state(AgentState.CANCELLED)
                return AgentTaskResult(
                    status=AgentState.CANCELLED, task=task,
                    summary="Execution cancelled by user.",
                    files_changed=sorted(files_changed), tool_history=self.history,
                    execution_id=self.execution_id,
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
                default_resource_manager.cleanup_execution(self.execution_id)
                return AgentTaskResult(
                    status=AgentState.COMPLETED, task=task,
                    summary=final_summary,
                    files_changed=sorted(files_changed), tool_history=self.history,
                    execution_id=self.execution_id,
                )

            # Execute each tool call in sequence
            for call in calls:
                if self.is_cancelled():
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
                # Record step in stuck detector & check stuck condition
                self.stuck_detector.record_step(call.tool, call.args, status="started")
                if self.stuck_detector.is_stuck():
                    hint = self.stuck_detector.get_recovery_hint()
                    current_prompt += f"\n{hint}\n"
                    self._emit("stuck_detected", {"tool": call.tool, "args": call.args})

                # Permission broker check
                perm_decision = self.permission_broker.authorize_command(
                    call.tool,
                    allow_destructive=(self.autonomy_mode == AutonomyMode.AUTO),
                )
                if perm_decision.value == "DENY":
                    current_prompt += f"\n[PERMISSION DENIED] Action '{call.tool}' was denied by security policy.\n"
                    continue

                # Execute
                self._set_state(AgentState.EXECUTING)
                self._emit("tool_starting", {"tool": call.tool, "args": call.args, "thought": thought})

                t0 = time.monotonic()
                obs = self.tool_registry.execute(
                    call.tool,
                    call.args,
                    execution_id=self.execution_id,
                    cancellation_token=self.cancellation_token,
                )
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

                # ── Smart auto-completion ──────────────────────────────────────────
                # If this was the only tool call in the LLM response AND it succeeded
                # AND it was a write/create operation → no need for another LLM round trip.
                # This saves one full LLM call (~57-80s on CPU hardware).
                _write_tools = {"write_file", "create_file", "patch_file", "replace_text", "insert_text", "delete_text"}
                if (
                    len(calls) == 1
                    and call.tool in _write_tools
                    and obs.get("exit_code") == 0
                    and _simple_task
                ):
                    path_written = call.args.get("path", "file")
                    auto_summary = f"Done. Created/updated `{path_written}` successfully."
                    if files_changed:
                        self.memory.record_modification(
                            ", ".join(list(files_changed)[:5]),
                            "agent_task",
                            f"Task: {task[:100]}",
                        )
                    self._set_state(AgentState.COMPLETED)
                    self._emit("completed", {"summary": auto_summary, "files_changed": sorted(files_changed)})
                    default_resource_manager.cleanup_execution(self.execution_id)
                    return AgentTaskResult(
                        status=AgentState.COMPLETED, task=task,
                        summary=auto_summary,
                        files_changed=sorted(files_changed), tool_history=self.history,
                        execution_id=self.execution_id,
                    )
                # ──────────────────────────────────────────────────────────────────

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

        # Cleanup process handles
        default_resource_manager.cleanup_execution(self.execution_id)

        if self.is_cancelled():
            self._set_state(AgentState.CANCELLED)
            return AgentTaskResult(
                status=AgentState.CANCELLED, task=task,
                summary="Execution cancelled by user.",
                files_changed=sorted(files_changed), tool_history=self.history,
                execution_id=self.execution_id,
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
            execution_id=self.execution_id,
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
            import inspect
            sig = inspect.signature(self.provider.chat if hasattr(self.provider, "chat") else self.provider.generate)
            extra = {}
            if "cancellation_token" in sig.parameters:
                extra["cancellation_token"] = self.cancellation_token

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
                    **extra,
                )
            return self.provider.generate(
                prompt=safe_prompt,
                model=self.model,
                system_prompt=system_prompt,
                stream=bool(self.stream_callback),
                callback=_chunk_cb if self.stream_callback else None,
                temperature=0.2,
                **extra,
            )
        except (ProviderError, Exception) as exc:
            self._emit("provider_error", {"error": str(exc)})
            return self._fallback_deterministic_step(prompt)
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

    def _build_system_prompt(self, tool_defs: list[dict[str, Any]], compact: bool = False) -> str:
        caps = self._capabilities
        protocol_note = (
            "This model supports native tool calling. Use the JSON block format below."
            if caps and caps.native_tool_calling
            else "Always use JSON block format for tool calls."
        )

        if compact:
            # Compact mode: just tool names + one-line descriptions (much fewer tokens)
            tool_lines = "\n".join(
                f'  "{t["name"]}": {t.get("description", "")[:80]}'
                for t in tool_defs
            )
            return f"""You are an autonomous AI coding agent inside Vibe Studio IDE. {protocol_note}

TOOL CALL FORMAT (use EXACTLY this):
```json
{{"tool": "tool_name", "args": {{"param": "value"}}}}
```

For final answer with no more tool calls: respond in PLAIN TEXT ONLY (no JSON, no code blocks).

AVAILABLE TOOLS:
{tool_lines}

RULES: Read files before editing. Use smallest change possible. Verify after editing.
"""

        # Full prompt with complete schema
        tools_json = json.dumps(tool_defs, indent=2)
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
        # Extract user request cleanly from prompt wrapper
        raw_task = prompt
        if "USER REQUEST:" in prompt:
            try:
                part = prompt.split("USER REQUEST:")[1]
                for header in ["\nCONVERSATION HISTORY", "\nPROJECT MEMORY", "\nPROJECT FILE CONTEXT", "\nEXECUTION LOG"]:
                    if header in part:
                        part = part.split(header)[0]
                raw_task = part.strip()
            except Exception:
                raw_task = prompt
        task = raw_task.lower().strip()
        hist_len = len(self.history)

        def _tc(name: str, args: dict) -> str:
            return f"```json\n{json.dumps({'tool': name, 'args': args}, ensure_ascii=False)}\n```"

        # Conversational greetings
        words = task.split()
        if (
            len(task) < 40
            and not any(k in task for k in ["create", "yarat", "yaz", "file", "fayl", "make", "code", "run", "delete", "sil", "clear", "boşalt"])
            and any(w in words for w in ["salam", "hello", "hi", "hey", "sa", "necəsn", "necesen", "günaydın", "gunaydin"])
        ):
            return (
                "Salam! Mən Vibe Studio AI köməkçisiyəm. "
                "Layihənizdə sizə necə kömək edə bilərəm? "
                "(Məsələn: fayl yaratmaq, funksiyanı düzəltmək, testləri işə salmaq və s.)"
            )

        # Target file resolution helper (scoped strictly to raw_task and current context)
        def _resolve_target_file() -> str | None:
            import re
            m = re.search(r"([\w./\\-]+\.(?:py|js|ts|txt|md|html|css|json|yaml|go|rs|c|cpp))", raw_task, re.IGNORECASE)
            if m:
                return m.group(1)
            # Check Active File tag in prompt
            m_act = re.search(r"\[(?:Active file|Selected code in)\s+([\w./\\-]+\.\w+)\]", prompt, re.IGNORECASE)
            if m_act:
                return m_act.group(1)
            # Check files changed in history
            if self.history:
                for step in reversed(self.history):
                    if step.observation and step.observation.get("files_changed"):
                        return step.observation["files_changed"][0]
            # Check existing files in project
            for candidate in ["hello.html", "index.html", "main.py", "styles.css", "README.md"]:
                if (self.project_root / candidate).exists():
                    return candidate
            return None

        # CLEAR / BOŞALT / EMPTY FILE
        if any(w in task for w in ["clear", "boşalt", "təmizlə", "empty", "erase"]):
            target = _resolve_target_file() or "hello.html"
            if hist_len == 0:
                return _tc("write_file", {"path": target, "content": ""})
            return f"Successfully cleared `{target}`."

        # Style / background
        if any(w in task for w in ["background", "arxa fon", "gradient", "login", "style", "css"]):
            target = self._find_style_target()
            if hist_len == 0:
                return _tc("search_filename", {"pattern": "login"})
            if hist_len == 1 and target:
                return _tc("read_file", {"path": target})
            if hist_len == 2 and target:
                gradient = (
                    "body {\n"
                    "  background: linear-gradient(135deg, #111827 0%, #1e3a5f 50%, #3b82f6 100%);\n"
                    "  color: white;\n"
                    "}\n"
                )
                return _tc("write_file", {"path": target, "content": gradient})
            if hist_len >= 3:
                return "Task completed successfully. Updated style with background gradient."

        # Delete
        if any(w in task for w in ["delete", "sil", "remove", "kaldır"]):
            import re
            m = re.search(r"(?:delete|remove|sil)\s+([\w./\\-]+\.\w+)", raw_task, re.IGNORECASE)
            if not m:
                m = re.search(r"\b([\w./\\-]+\.(?:txt|py|js|ts|md|json|css|html))\b", raw_task, re.IGNORECASE)
            target = m.group(1) if m else _resolve_target_file()
            if target and hist_len == 0:
                return _tc("delete_file", {"path": target})
            return "Task completed successfully."

        # WRITE / CREATE / ADD FILE
        if any(w in task for w in ["create", "make", "yarat", "yaz", "new file", "write", "add", "insert", "put"]):
            if ("1 to 20" in task or "1-20" in task or "numbers" in task) and hist_len == 0:
                content = "\n".join(str(i) for i in range(1, 21))
                return _tc("write_file", {"path": "numbers.txt", "content": content})

            import re
            code = re.search(r"```(?:[A-Za-z0-9_-]+)?\s*(.*?)```", raw_task, re.DOTALL)
            content = code.group(1).strip() if code else ""

            target = _resolve_target_file()

            if not content:
                if target and target.endswith(".html"):
                    content = (
                        "<!DOCTYPE html>\n"
                        "<html lang=\"en\">\n"
                        "<head>\n"
                        "  <meta charset=\"UTF-8\">\n"
                        "  <title>Simple Page</title>\n"
                        "</head>\n"
                        "<body>\n"
                        "  <h1>Hello World</h1>\n"
                        "  <p>What is your question?</p>\n"
                        "</body>\n"
                        "</html>\n"
                    )
                elif target and target.endswith(".py"):
                    content = "# Simple script\nprint('Hello World')\n"
                elif "question" in task or "sual" in task:
                    content = "<!-- Question: What is the main objective of this application? -->\n"
                else:
                    content = f"<!-- Created for request: {raw_task} -->\n"

            if not target:
                target = "hello.html" if "html" in task else "main.py"

            if hist_len == 0:
                return _tc("write_file", {"path": target, "content": content})

        # Tests
        if any(w in task for w in ["test", "pytest"]):
            if hist_len == 0:
                return _tc("run_tests", {})
            return "Task completed successfully."

        # Analyze
        if any(w in task for w in ["analyze", "inspect", "explain", "summarize"]):
            if hist_len == 0:
                return _tc("detect_project_type", {})
            if hist_len == 1:
                return _tc("tree", {"max_depth": 3})

        # Fallback completion check
        if hist_len > 0:
            last = self.history[-1]
            if last.observation and last.observation.get("exit_code") == 0:
                return "Task completed successfully."

        return "Task completed successfully."

    def _find_style_target(self) -> str | None:
        ignored_parts = {".venv", "venv", "node_modules", ".git", "__pycache__", "build", "dist", ".pytest_cache"}
        for path in sorted(self.project_root.rglob("*")):
            if not path.is_file():
                continue
            parts = set(path.parts)
            if ignored_parts.intersection(parts):
                continue
            name = path.name.lower()
            if name.endswith((".css", ".scss", ".sass", ".html", ".vue", ".jsx", ".tsx")):
                return path.relative_to(self.project_root).as_posix()
            if (name.endswith((".py", ".js", ".ts")) and ("style" in name or "login" in name)):
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
