"""Unit and integration tests for AgentOrchestrator."""
from __future__ import annotations

import os
os.environ.setdefault("VIBE_STUDIO_OFFLINE", "1")

from pathlib import Path
import pytest

from vibe_studio.agents.orchestrator import AgentOrchestrator


class TestAgentOrchestrator:
    def test_orchestrator_initialization(self, tmp_path):
        orchestrator = AgentOrchestrator(tmp_path)
        assert orchestrator.workspace_root == tmp_path.resolve()

    def test_orchestrator_execute_task(self, tmp_path):
        # Create a sample login file
        src = tmp_path / "src"
        src.mkdir()
        login_css = src / "login.css"
        login_css.write_text("body { background: #fff; }", encoding="utf-8")

        orchestrator = AgentOrchestrator(tmp_path)
        res = orchestrator.execute_task("Find login page and update background")

        assert res.prompt == "Find login page and update background"
        assert res.execution_result is not None
        assert res.review_result is not None
        assert res.summary != ""
        assert "Task:" in res.summary
