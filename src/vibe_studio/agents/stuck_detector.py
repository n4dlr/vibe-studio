"""Stuck Agent Detector for Vibe Studio.

Monitors execution trajectory in real time to detect non-advancing loops, repeated prompt states,
and model stalls, triggering emergency self-recovery or graceful abort.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


READ_SEARCH_TOOLS = {
    "search_filename", "search_text", "list_directory", "file_exists",
    "read_file", "tree", "read_multiple_files", "get_file_metadata"
}


class StuckAgentDetector:
    """Detects stuck state patterns in agent execution trajectories."""

    def __init__(self, max_identical_steps: int = 2, max_search_steps: int = 3, max_stall_seconds: float = 45.0):
        self.max_identical_steps = max_identical_steps
        self.max_search_steps = max_search_steps
        self.max_stall_seconds = max_stall_seconds
        self._history: List[Dict[str, Any]] = []
        self._last_step_time = time.time()
        self._stuck_reason = ""

    def record_step(self, tool_name: Optional[str], args: Dict[str, Any], status: str) -> None:
        self._last_step_time = time.time()
        self._history.append({
            "tool": tool_name or "",
            "args": dict(args),
            "status": status,
            "time": self._last_step_time,
        })

    def is_stuck(self) -> bool:
        """Check if agent is stuck in identical steps, search loops, or stalled in time."""
        # 1. Stall check
        if time.time() - self._last_step_time > self.max_stall_seconds:
            self._stuck_reason = "stall"
            return True

        # 2. Duplicate tool call chain check (2 identical tool calls)
        if len(self._history) >= self.max_identical_steps:
            recent = self._history[-self.max_identical_steps:]
            first_tool = recent[0]["tool"]
            first_args = recent[0]["args"]

            all_same = all(
                r["tool"] == first_tool and r["args"] == first_args for r in recent
            )
            if all_same and first_tool:
                self._stuck_reason = "identical_tools"
                return True

        # 3. Read/Search tool loop check (3 consecutive read/search calls without editing)
        if len(self._history) >= self.max_search_steps:
            recent = self._history[-self.max_search_steps:]
            all_search = all(r["tool"] in READ_SEARCH_TOOLS for r in recent)
            if all_search:
                self._stuck_reason = "search_loop"
                return True

        return False

    def get_recovery_hint(self) -> str:
        """Return recovery prompt hint to force agent to switch approaches."""
        if self._stuck_reason == "search_loop":
            return (
                "[SYSTEM STUCK RECOVERY HINT] You have executed read/search tools 3 times without creating or editing files. "
                "STOP searching. You have enough information. Immediately proceed to creating or writing the required code/files!"
            )
        return (
            "[SYSTEM STUCK RECOVERY HINT] You have executed identical tool calls repeatedly without progress. "
            "Do NOT run this tool again with the same arguments. Switch approach or start building the project files now."
        )
