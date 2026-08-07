from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ContextItem:
    path: str
    score: float
    reason: str
    kind: str = "file"


@dataclass
class ContextBundle:
    items: list[ContextItem] = field(default_factory=list)
    budget: int = 12000


class ContextEngine:
    """Produces a ranked set of relevant files and symbols for the active task."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def build(self, prompt: str, active_file: str | None = None, git_changes: list[str] | None = None) -> ContextBundle:
        items: list[ContextItem] = []
        if not self.root.exists():
            return ContextBundle(items=items)

        candidates = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            if rel.startswith(".git"):
                continue
            score = 0.0
            lower = rel.lower()
            if active_file and rel == active_file:
                score += 60
            if any(token in lower for token in ["config", "settings", "app", "src", "project"]):
                score += 10
            if any(token in prompt.lower() for token in ["api", "auth", "db", "test", "login", "bug"]):
                if any(token in lower for token in ["auth", "api", "db", "test"]):
                    score += 25
            if git_changes and rel in git_changes:
                score += 35
            if rel.endswith((".py", ".json", ".md", ".toml", ".yaml")):
                score += 5
            if score > 0:
                candidates.append((rel, score))

        ranked = sorted(candidates, key=lambda item: item[1], reverse=True)[:25]
        for rel, score in ranked:
            reason = "project relevance"
            if active_file and rel == active_file:
                reason = "active editor" 
            elif git_changes and rel in git_changes:
                reason = "recent git change"
            items.append(ContextItem(path=rel, score=score, reason=reason))
        return ContextBundle(items=items)
