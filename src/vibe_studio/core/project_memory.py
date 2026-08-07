from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    key: str
    value: dict[str, Any] = field(default_factory=dict)


class ProjectMemory:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        self.storage = self.project_root / ".vibe_studio_memory.json"
        self.project_root.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.storage.exists():
            return {}
        try:
            return json.loads(self.storage.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save(self, data: dict[str, Any]) -> None:
        self.storage.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def remember(self, key: str, value: dict[str, Any]) -> None:
        memory = self.load()
        memory[key] = value
        self.save(memory)
