"""REST API Server — provides HTTP endpoints for chat, project analysis, and automated fixes."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from vibe_studio.api.auth import APIAuth
from vibe_studio.agents.coding_agent import AutonomousAgent, AutonomyMode
from vibe_studio.project.project_scanner import ProjectScanner


class APIServerHandler:
    """Headless API handler serving REST requests for Vibe Studio."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()

    def handle_chat(self, prompt: str, api_key: str = "") -> dict[str, Any]:
        if not APIAuth.verify_key(api_key):
            return {"error": "Unauthorized: Invalid API key", "status_code": 401}

        agent = AutonomousAgent(
            project_root=self.workspace_root,
            autonomy_mode=AutonomyMode.AUTO,
        )
        res = agent.run(prompt)
        return {
            "status": res.status.value,
            "summary": res.summary,
            "files_changed": res.files_changed,
        }

    def handle_analyze(self, api_key: str = "") -> dict[str, Any]:
        if not APIAuth.verify_key(api_key):
            return {"error": "Unauthorized: Invalid API key", "status_code": 401}

        scanner = ProjectScanner(self.workspace_root)
        summary = scanner.scan()
        return {
            "root": summary.root,
            "languages": summary.languages,
            "frameworks": summary.frameworks,
            "total_files": len(summary.files),
            "entry_points": summary.entry_points,
            "tests": summary.tests,
        }

    def handle_fix(self, error_message: str, api_key: str = "") -> dict[str, Any]:
        if not APIAuth.verify_key(api_key):
            return {"error": "Unauthorized: Invalid API key", "status_code": 401}

        prompt = f"Fix the following error in the project:\n{error_message}"
        return self.handle_chat(prompt, api_key=api_key)
