"""Unit and integration tests for SuperAgent, BrowserTools, WebTools, MemoryTools, and UI Panel."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vibe_studio.agents.super_agent import (
    HierarchicalPlan,
    HierarchicalPlanner,
    PlanItemStatus,
    SelfCritiqueEngine,
    SelfCritiqueResult,
    SuperAgent,
)
from vibe_studio.tools.browser_tools import BrowserTools
from vibe_studio.tools.memory_tools import MemoryTools
from vibe_studio.tools.tool_registry import ToolRegistry
from vibe_studio.tools.web_tools import WebTools, _html_to_clean_text


def test_tool_registry_includes_super_tools():
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = ToolRegistry(tmpdir)
        tool_names = {t["name"] for t in registry.list_tools()}

        # Browser Tools
        assert "browser_open" in tool_names
        assert "browser_navigate" in tool_names
        assert "browser_click" in tool_names
        assert "browser_type" in tool_names
        assert "browser_screenshot" in tool_names
        assert "browser_extract_text" in tool_names

        # Web Research Tools
        assert "web_fetch" in tool_names
        assert "web_search" in tool_names
        assert "web_extract_links" in tool_names

        # Memory Tools
        assert "memory_save" in tool_names
        assert "memory_read" in tool_names
        assert "memory_list" in tool_names
        assert "memory_search" in tool_names


def test_memory_tools_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = MemoryTools(tmpdir)

        # Save
        res_save = mem.memory_save("arch_pattern", "Event-driven microservices", category="architecture")
        assert res_save["success"] is True

        # Read
        res_read = mem.memory_read("arch_pattern")
        assert res_read["found"] is True
        assert res_read["value"] == "Event-driven microservices"
        assert res_read["category"] == "architecture"

        # Search
        res_search = mem.memory_search("microservices")
        assert res_search["matches_count"] == 1
        assert "arch_pattern" in res_search["matches"]

        # List
        res_list = mem.memory_list(category="architecture")
        assert "arch_pattern" in res_list["keys"]

        # Delete
        res_del = mem.memory_delete("arch_pattern")
        assert res_del["deleted"] is True
        assert mem.memory_read("arch_pattern")["found"] is False


def test_web_tools_html_cleaner():
    raw_html = """
    <html>
      <head><title>Test Page</title></head>
      <body>
        <script>console.log("ignore me");</script>
        <h1>Hello World</h1>
        <p>This is <b>important</b> content &amp; data.</p>
      </body>
    </html>
    """
    cleaned = _html_to_clean_text(raw_html)
    assert "Hello World" in cleaned
    assert "important" in cleaned
    assert "console.log" not in cleaned


def test_hierarchical_planner_heuristic():
    planner = HierarchicalPlanner()
    plan = planner.build_initial_plan("Write a Python FastAPI service with tests and search for best practices")
    assert isinstance(plan, HierarchicalPlan)
    assert len(plan.milestones) >= 3
    assert plan.milestones[0].status == PlanItemStatus.PENDING


def test_self_critique_engine():
    engine = SelfCritiqueEngine(min_score_threshold=85)
    critique = engine._heuristic_critique(
        goal="Create calculator in calc.py",
        summary="Done, created calculator and tests.",
        files_changed=["calc.py", "test_calc.py"],
        tool_history=[],
    )
    assert isinstance(critique, SelfCritiqueResult)
    assert critique.score >= 85
    assert critique.passed_threshold is True


def test_super_agent_execution_loop():
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = SuperAgent(workspace_root=tmpdir, max_iterations=5, push_hard_threshold=70)
        res = agent.run("Create a documentation summary of the project architecture in README.md")
        assert res.status.value in ("COMPLETED", "COMPLETED_WITH_WARNINGS")
        assert res.plan is not None
        assert res.critique is not None
        assert res.execution_id != ""
