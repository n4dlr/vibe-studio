"""SyncManager — synchronizes project memory and user settings across devices."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from vibe_studio.core.project_memory import ProjectMemory


class SyncManager:
    """Manages local export and remote synchronization of workspace memory bundles."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.memory = ProjectMemory(self.project_root)

    def export_sync_bundle(self) -> str:
        data = self.memory.load()
        bundle = {
            "project_name": self.project_root.name,
            "memory": data,
            "version": "1.0",
        }
        return json.dumps(bundle, indent=2)

    def import_sync_bundle(self, bundle_json: str) -> bool:
        try:
            bundle = json.loads(bundle_json)
            memory_data = bundle.get("memory", {})
            if isinstance(memory_data, dict):
                self.memory.save(memory_data)
                return True
        except Exception:
            return False
        return False
