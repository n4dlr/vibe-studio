"""NavigatorAgent — explores project files, identifies entry points, and provides structural summaries."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from vibe_studio.project.project_scanner import ProjectScanner


class NavigatorAgent:
    """Specialized agent focused on codebase navigation, file mapping, and dependency discovery."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.scanner = ProjectScanner(self.workspace_root)

    def discover_relevant_files(self, topic: str) -> list[str]:
        summary = self.scanner.scan()
        topic_lower = topic.lower()
        matched: list[str] = []

        for f in summary.files:
            if topic_lower in f.path.lower():
                matched.append(f.path)
            for sym in f.symbols:
                if topic_lower in sym.name.lower():
                    matched.append(f.path)
                    break

        return sorted(list(set(matched)))[:15]

    def get_structure_map(self) -> dict[str, Any]:
        summary = self.scanner.scan()
        return {
            "languages": summary.languages,
            "frameworks": summary.frameworks,
            "entry_points": summary.entry_points,
            "total_files": len(summary.files),
        }
