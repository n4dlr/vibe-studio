"""MemoryTools — Persistent knowledge and notes storage for the autonomous agent.

Allows the agent to remember facts, project architecture details, user preferences,
research findings, and previous sub-task results across sessions and iterations.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryTools:
    """Persistent JSON-backed knowledge store for AI agents."""

    def __init__(self, workspace_root: str | Path = "."):
        self.workspace_root = Path(workspace_root).resolve()
        self._memory_file = self.workspace_root / ".vibe_studio" / "agent_memory.json"

    def _load(self) -> dict[str, Any]:
        if self._memory_file.exists():
            try:
                return json.loads(self._memory_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load memory file: %s", exc)
        return {"items": {}, "created_at": time.time(), "updated_at": time.time()}

    def _save(self, data: dict[str, Any]) -> None:
        try:
            self._memory_file.parent.mkdir(parents=True, exist_ok=True)
            data["updated_at"] = time.time()
            self._memory_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to save memory file: %s", exc)

    def memory_save(self, key: str, value: str, category: str = "general") -> dict[str, Any]:
        """Save a key-value fact or note into persistent memory."""
        data = self._load()
        data["items"][key] = {
            "value": value,
            "category": category,
            "timestamp": time.time(),
        }
        self._save(data)
        return {
            "action": "memory_save",
            "key": key,
            "category": category,
            "success": True,
        }

    def memory_read(self, key: str) -> dict[str, Any]:
        """Retrieve a specific memory item by key."""
        data = self._load()
        item = data["items"].get(key)
        if item:
            return {
                "action": "memory_read",
                "key": key,
                "found": True,
                "value": item["value"],
                "category": item.get("category", "general"),
                "timestamp": item.get("timestamp"),
            }
        return {
            "action": "memory_read",
            "key": key,
            "found": False,
            "value": None,
        }

    def memory_list(self, category: str | None = None) -> dict[str, Any]:
        """List all keys stored in memory, optionally filtered by category."""
        data = self._load()
        items = {}
        for k, v in data["items"].items():
            if category is None or v.get("category") == category:
                items[k] = v
        return {
            "action": "memory_list",
            "count": len(items),
            "keys": list(items.keys()),
            "items": items,
        }

    def memory_search(self, query: str) -> dict[str, Any]:
        """Search memory keys and contents for a keyword or phrase."""
        data = self._load()
        q = query.lower()
        matches = {}
        for k, v in data["items"].items():
            if q in k.lower() or q in str(v.get("value", "")).lower():
                matches[k] = v
        return {
            "action": "memory_search",
            "query": query,
            "matches_count": len(matches),
            "matches": matches,
        }

    def memory_delete(self, key: str) -> dict[str, Any]:
        """Remove a memory key."""
        data = self._load()
        if key in data["items"]:
            del data["items"][key]
            self._save(data)
            return {"action": "memory_delete", "key": key, "deleted": True}
        return {"action": "memory_delete", "key": key, "deleted": False}
