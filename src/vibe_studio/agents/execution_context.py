"""ExecutionContext — Central, thread-safe execution tracker for Vibe Studio agent runs.

Provides structured tracking of execution lifecycle, state transitions, active tools,
cancellation tokens, generated file changes, token usage, and verification results without hidden globals.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from vibe_studio.core.cancellation import CancellationToken

logger = logging.getLogger(__name__)


class ExecutionState:
    """Standard execution state constants for agent pipeline stages."""
    IDLE       = "IDLE"
    ANALYZING  = "ANALYZING"
    PLANNING   = "PLANNING"
    EXECUTING  = "EXECUTING"
    OBSERVING  = "OBSERVING"
    VALIDATING = "VALIDATING"
    FIXING     = "FIXING"
    REVIEWING  = "REVIEWING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    CANCELLED  = "CANCELLED"
    BLOCKED    = "BLOCKED"

    WAITING_APPROVAL = "WAITING_APPROVAL"

    # All terminal states
    TERMINAL_STATES: frozenset[str] = frozenset({
        "COMPLETED", "FAILED", "CANCELLED", "BLOCKED"
    })


@dataclass
class StateTransitionRecord:
    from_state: str
    to_state: str
    timestamp: float
    duration_in_prev_state: float
    details: str = ""


@dataclass
class ExecutionContext:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_prompt: str = ""
    current_state: str = "IDLE"
    start_time: float = field(default_factory=time.monotonic)
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    iteration_count: int = 0
    tool_call_count: int = 0
    token_usage: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    active_tool: Optional[str] = None
    last_error: Optional[str] = None
    generated_changes: list[str] = field(default_factory=list)
    validation_result: Optional[Any] = None
    final_result: Optional[Any] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    state_history: list[StateTransitionRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_state_time: float = field(default_factory=time.monotonic, repr=False)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def is_cancelled(self) -> bool:
        return self.cancellation_token.is_cancelled()

    def transition_to(self, new_state: str, details: str = "") -> None:
        """Atomically transition to a new state and record timing."""
        with self._lock:
            now = time.monotonic()
            prev_duration = now - self._last_state_time
            record = StateTransitionRecord(
                from_state=self.current_state,
                to_state=new_state,
                timestamp=now,
                duration_in_prev_state=prev_duration,
                details=details,
            )
            self.state_history.append(record)
            self.current_state = new_state
            self._last_state_time = now

    def record_tool_call(self, tool_name: str) -> None:
        with self._lock:
            self.active_tool = tool_name
            self.tool_call_count += 1

    def finish_tool_call(self) -> None:
        with self._lock:
            self.active_tool = None

    def record_file_change(self, file_path: str) -> None:
        with self._lock:
            if file_path not in self.generated_changes:
                self.generated_changes.append(file_path)

    def record_error(self, error_message: str) -> None:
        with self._lock:
            self.last_error = error_message

    def add_token_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        """Alias for record_tokens — accumulates token counts thread-safely."""
        self.record_tokens(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    def record_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        with self._lock:
            self.token_usage["prompt_tokens"] += prompt_tokens
            self.token_usage["completion_tokens"] += completion_tokens
            self.token_usage["total_tokens"] = (
                self.token_usage["prompt_tokens"] + self.token_usage["completion_tokens"]
            )

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "task_id": self.task_id,
                "task_prompt": self.task_prompt,
                "current_state": self.current_state,
                "elapsed_seconds": round(self.elapsed_seconds, 2),
                "iteration_count": self.iteration_count,
                "tool_call_count": self.tool_call_count,
                "token_usage": dict(self.token_usage),
                "active_tool": self.active_tool,
                "last_error": self.last_error,
                "generated_changes": list(self.generated_changes),
                "validation_result": str(self.validation_result) if self.validation_result else None,
                "final_result": str(self.final_result) if self.final_result else None,
                "cancelled": self.is_cancelled,
                "metadata": dict(self.metadata),
                "state_transitions": [
                    {
                        "from": r.from_state,
                        "to": r.to_state,
                        "duration": round(r.duration_in_prev_state, 3),
                        "details": r.details,
                    }
                    for r in self.state_history
                ],
            }
