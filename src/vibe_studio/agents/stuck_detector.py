"""Stuck Agent Detector for Vibe Studio.

Monitors execution trajectory in real time to detect non-advancing loops, repeated prompt states,
and model stalls, triggering emergency self-recovery or graceful abort.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class StuckAgentDetector:
    """Detects stuck state patterns in agent execution trajectories."""

    def __init__(self, max_identical_steps: int = 3, max_stall_seconds: float = 45.0):
        self.max_identical_steps = max_identical_steps
        self.max_stall_seconds = max_stall_seconds
        self._history: List[Dict[str, Any]] = []
        self._last_step_time = time.time()

    def record_step(self, tool_name: Optional[str], args: Dict[str, Any], status: str) -> None:
        self._last_step_time = time.time()
        self._history.append({
            "tool": tool_name or "",
            "args": dict(args),
            "status": status,
            "time": self._last_step_time,
        })

    def is_stuck(self) -> bool:
        """Check if agent is stuck in identical steps or stalled in time."""
        # 1. Stall check
        if time.time() - self._last_step_time > self.max_stall_seconds:
            return True

        # 2. Duplicate tool call chain check
        if len(self._history) >= self.max_identical_steps:
            recent = self._history[-self.max_identical_steps:]
            first_tool = recent[0]["tool"]
            first_args = recent[0]["args"]

            all_same = all(
                r["tool"] == first_tool and r["args"] == first_args for r in recent
            )
            if all_same and first_tool:
                return True

        return False

    def get_recovery_hint(self) -> str:
        """Return recovery prompt hint to force agent to switch approaches."""
        return (
            "[SYSTEM STUCK RECOVERY HINT] You have executed identical tool calls repeatedly without progress. "
            "Do NOT run this tool again with the same arguments. Switch approach or explain why task cannot continue."
        )
