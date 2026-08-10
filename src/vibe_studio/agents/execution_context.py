"""ExecutionContext — Central, thread-safe execution tracker for Vibe Studio agent runs.

Provides structured tracking of execution lifecycle, state transitions, active tools,
cancellation tokens, generated file changes, and verification results without hidden globals.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from vibe_studio.core.cancellation import CancellationToken

logger = logging.getLogger(__name__)


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
    token_usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    active_tool: Optional[str] = None
    last_error: Optional[str] = None
    generated_changes: list[str] = field(default_factory=list)
    validation_result: Optional[Any] = None
    final_result: Optional[Any] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def is_cancelled(self) -> bool:
        return self.cancellation_token.is_cancelled()

    def record_tool_call(self, tool_name: str) -> None:
        self.active_tool = tool_name
        self.tool_call_count += 1

    def record_file_change(self, file_path: str) -> None:
        if file_path not in self.generated_changes:
            self.generated_changes.append(file_path)

    def record_error(self, error_message: str) -> None:
        self.last_error = error_message

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "task_prompt": self.task_prompt,
            "current_state": self.current_state,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "iteration_count": self.iteration_count,
            "tool_call_count": self.tool_call_count,
            "token_usage": self.token_usage,
            "active_tool": self.active_tool,
            "last_error": self.last_error,
            "generated_changes": self.generated_changes,
            "cancelled": self.is_cancelled,
        }
