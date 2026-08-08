"""LearningEngine — tracks user file access habits, command usage frequency, and project conventions."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from vibe_studio.core.project_memory import ProjectMemory


class LearningEngine:
    """Analyzes workspace operations to infer user habits and primary entry points over time."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        self.memory = ProjectMemory(self.project_root)

    def record_event(self, event_type: str, details: dict[str, Any]) -> None:
        data = self.memory.load()
        habits = data.get("user_habits", {"file_access_counts": {}, "command_counts": {}})

        if event_type == "file_open" or event_type == "file_edit":
            path = details.get("file", "")
            if path:
                counts = habits.get("file_access_counts", {})
                counts[path] = counts.get(path, 0) + 1
                habits["file_access_counts"] = counts

        elif event_type == "command_execute":
            cmd = details.get("command", "")
            if cmd:
                counts = habits.get("command_counts", {})
                counts[cmd] = counts.get(cmd, 0) + 1
                habits["command_counts"] = counts

        data["user_habits"] = habits
        self.memory.save(data)

    def get_frequently_accessed_files(self, limit: int = 5) -> list[str]:
        habits = self.memory.get("user_habits", {})
        counts: dict[str, int] = habits.get("file_access_counts", {})
        sorted_files = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [f[0] for f in sorted_files[:limit]]

    def get_frequent_commands(self, limit: int = 5) -> list[str]:
        habits = self.memory.get("user_habits", {})
        counts: dict[str, int] = habits.get("command_counts", {})
        sorted_cmds = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [c[0] for c in sorted_cmds[:limit]]
