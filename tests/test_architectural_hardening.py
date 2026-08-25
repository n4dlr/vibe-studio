"""Comprehensive tests for architectural hardening:
1. MoA isolated workspace sandboxing.
2. Workflow AST script execution sandboxing.
3. PermissionBroker policy gate in ToolRegistry.
4. Multi-language AST symbol indexing (JS/TS, Go, Rust) and true PageRank.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from vibe_studio.agents.orchestrator import AgentOrchestrator
from vibe_studio.knowledge.graph_engine import EdgeType, KnowledgeGraphEngine, NodeType
from vibe_studio.security.permission_broker import PermissionBroker, PermissionDecision
from vibe_studio.tools.tool_registry import RiskLevel, ToolParameter, ToolRegistry
from vibe_studio.workflow.engine import NodeKind, WorkflowNode, WorkflowPipeline


class MockDummyProvider:
    def __init__(self, response: str = "Task completed successfully."):
        self.response = response

    def generate(self, prompt: str, **kwargs) -> str:
        return self.response

    def chat(self, messages: list, **kwargs) -> str:
        return self.response

    def is_available(self) -> bool:
        return True


def test_moa_sandboxed_isolation(tmp_path: Path) -> None:
    """MoA candidates run in isolated ephemeral directories without corrupting main workspace."""
    main_file = tmp_path / "main.py"
    main_file.write_text("initial = True\n", encoding="utf-8")

    orchestrator = AgentOrchestrator(
        workspace_root=tmp_path,
        provider=MockDummyProvider(),
        model="mock-model",
    )

    res = orchestrator.execute_moa_consensus_task("Refactor codebase", num_candidates=2)
    assert res is not None
    assert "MoA Sandboxed Judge" in res.summary
    assert main_file.exists()


def test_workflow_sandbox_blocks_dangerous_imports(tmp_path: Path) -> None:
    """Workflow Python script node blocks dangerous subprocess / socket imports."""
    pipeline = WorkflowPipeline("Security Test", workspace_root=str(tmp_path))
    t1 = WorkflowNode(id="t1", name="Trigger", kind=NodeKind.MANUAL_TRIGGER)
    p1 = WorkflowNode(
        id="p1",
        name="Malicious Script",
        kind=NodeKind.PYTHON_SCRIPT,
        params={"code": "import subprocess\nsubprocess.run('ls')\noutput = 'hacked'"},
    )
    pipeline.add_node(t1)
    pipeline.add_node(p1)
    pipeline.add_edge("t1", "p1")

    res = pipeline.execute()
    node_out = res["outputs"].get("p1")
    assert isinstance(node_out, dict)
    assert "Sandbox script rejected" in node_out.get("message", "")


def test_workflow_sandbox_allows_safe_operations(tmp_path: Path) -> None:
    """Workflow Python script node executes safe math, json, and string transformations."""
    pipeline = WorkflowPipeline("Safe Math", workspace_root=str(tmp_path))
    t1 = WorkflowNode(id="t1", name="Trigger", kind=NodeKind.MANUAL_TRIGGER)
    p1 = WorkflowNode(
        id="p1",
        name="Safe Script",
        kind=NodeKind.PYTHON_SCRIPT,
        params={"code": "output = {'doubled': [x * 2 for x in [1, 2, 3]], 'sqrt': math.sqrt(16)}"},
    )
    pipeline.add_node(t1)
    pipeline.add_node(p1)
    pipeline.add_edge("t1", "p1")

    res = pipeline.execute()
    node_out = res["outputs"].get("p1")
    assert isinstance(node_out, dict)
    assert node_out.get("doubled") == [2, 4, 6]
    assert node_out.get("sqrt") == 4.0


def test_tool_registry_permission_enforcement(tmp_path: Path) -> None:
    """ToolRegistry enforces PermissionBroker boundary and blocks paths outside workspace."""
    registry = ToolRegistry(tmp_path)

    # Attempt to write outside workspace
    outside_path = "/etc/shadow"
    res = registry.execute("write_file", {"path": outside_path, "content": "exploit"})
    assert res.get("is_error") is True or "denied" in str(res).lower() or "error" in str(res).lower()


def test_multilang_ast_and_pagerank(tmp_path: Path) -> None:
    """KnowledgeGraphEngine extracts symbols from JS, Go, Rust and computes true PageRank."""
    # 1. JS / TS
    (tmp_path / "app.ts").write_text(
        "import { AuthService } from './auth';\n"
        "export class AppServer {\n"
        "  start() {}\n"
        "}\n"
        "export function bootstrap() {}\n",
        encoding="utf-8",
    )
    # 2. Go
    (tmp_path / "main.go").write_text(
        "package main\n"
        "import (\n"
        "  \"fmt\"\n"
        ")\n"
        "type Config struct {}\n"
        "func StartEngine() {}\n",
        encoding="utf-8",
    )
    # 3. Rust
    (tmp_path / "lib.rs").write_text(
        "use std::collections::HashMap;\n"
        "pub struct DataStore {}\n"
        "pub fn init_db() {}\n",
        encoding="utf-8",
    )

    engine = KnowledgeGraphEngine(tmp_path)
    engine.scan_workspace()

    node_names = {n.name for n in engine.nodes.values()}
    # Assert JS/TS symbols
    assert "AppServer" in node_names
    assert "bootstrap" in node_names
    # Assert Go symbols
    assert "Config" in node_names
    assert "StartEngine" in node_names
    # Assert Rust symbols
    assert "DataStore" in node_names
    assert "init_db" in node_names

    # Assert PageRank scores are computed and normalized (0.0 <= centrality <= 1.0)
    for node in engine.nodes.values():
        assert 0.0 <= node.centrality <= 1.0
