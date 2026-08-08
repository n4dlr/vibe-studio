from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectMemoryData:
    architecture: str = ""
    frameworks: list[str] = field(default_factory=list)
    build_system: str = ""
    test_framework: str = ""
    conventions: list[str] = field(default_factory=list)
    recent_modifications: list[dict[str, Any]] = field(default_factory=list)
    custom_notes: dict[str, Any] = field(default_factory=dict)


class ProjectMemory:
    """Manages project-specific metadata and decisions saved locally in .vibe_studio_memory.json."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        self.storage = self.project_root / ".vibe_studio_memory.json"

    def load(self) -> dict[str, Any]:
        if not self.storage.exists():
            return {}
        try:
            return json.loads(self.storage.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, data: dict[str, Any]) -> None:
        try:
            self.storage.parent.mkdir(parents=True, exist_ok=True)
            self.storage.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def remember(self, key: str, value: Any) -> None:
        memory = self.load()
        memory[key] = value
        self.save(memory)

    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def record_modification(self, file_path: str, action: str, summary: str) -> None:
        memory = self.load()
        mods = memory.get("recent_modifications", [])
        mods.append({"file": file_path, "action": action, "summary": summary})
        memory["recent_modifications"] = mods[-50:]  # Keep last 50 edits
        self.save(memory)
