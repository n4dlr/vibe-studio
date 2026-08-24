"""Tests for KnowledgeGraphEngine, CanvasDocument, and WorkflowPipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibe_studio.knowledge.canvas_engine import CanvasDocument, CanvasEdge, CanvasNode, CanvasNodeType
from vibe_studio.knowledge.graph_engine import EdgeType, GraphNode, KnowledgeGraphEngine, NodeType
from vibe_studio.workflow.engine import (
    NodeExecutionStatus,
    NodeKind,
    WorkflowNode,
    WorkflowPipeline,
)


# ──────────────────────────────────────────────────────────────────────────────
# Knowledge Graph Engine Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_graph_engine_indexes_python_files(tmp_path: Path) -> None:
    """KnowledgeGraphEngine scans Python files and builds symbol nodes."""
    (tmp_path / "hello.py").write_text("class Greeter:\n    def greet(self): pass\n")
    (tmp_path / "main.py").write_text("from hello import Greeter\ndef run(): pass\n")

    engine = KnowledgeGraphEngine(tmp_path)
    engine.scan_workspace()

    node_names = [n.name for n in engine.nodes.values()]
    assert "hello.py" in node_names
    assert "main.py" in node_names
    assert "Greeter" in node_names

    # Should have DEFINES and IMPORTS edges
    edge_types = {e.edge_type for e in engine.edges}
    assert EdgeType.DEFINES in edge_types
    assert EdgeType.IMPORTS in edge_types


def test_graph_engine_indexes_markdown_wikilinks(tmp_path: Path) -> None:
    """WikiLinks inside Markdown files create WIKILINK edges."""
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\n\n[[AGENTS]] and [[TOOLS]] are key.\n")
    (tmp_path / "AGENTS.md").write_text("# Agents\n")

    engine = KnowledgeGraphEngine(tmp_path)
    engine.scan_workspace()

    edge_types = {e.edge_type for e in engine.edges}
    assert EdgeType.WIKILINK in edge_types


def test_graph_centrality_computed(tmp_path: Path) -> None:
    """After scanning, node centrality and degree should be set."""
    (tmp_path / "a.py").write_text("import os\nimport sys\n")
    engine = KnowledgeGraphEngine(tmp_path)
    engine.scan_workspace()

    file_node = next((n for n in engine.nodes.values() if n.name == "a.py"), None)
    assert file_node is not None
    assert file_node.degree >= 2  # at least 2 import edges


def test_physics_simulation_moves_nodes(tmp_path: Path) -> None:
    """Physics simulation should change node positions."""
    (tmp_path / "x.py").write_text("import os\n")
    engine = KnowledgeGraphEngine(tmp_path)
    engine.scan_workspace()

    initial_positions = {nid: (n.x, n.y) for nid, n in engine.nodes.items()}
    engine.step_physics_simulation(iterations=10)
    final_positions = {nid: (n.x, n.y) for nid, n in engine.nodes.items()}

    # At least some nodes should have moved
    moved = sum(1 for nid in initial_positions if initial_positions[nid] != final_positions.get(nid))
    assert moved > 0


def test_graph_search_nodes(tmp_path: Path) -> None:
    (tmp_path / "auth.py").write_text("class AuthService: pass\n")
    engine = KnowledgeGraphEngine(tmp_path)
    engine.scan_workspace()

    results = engine.search_nodes("auth")
    assert any("auth" in r.name.lower() or "auth" in r.path.lower() for r in results)


# ──────────────────────────────────────────────────────────────────────────────
# Canvas Engine Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_canvas_add_text_node() -> None:
    doc = CanvasDocument()
    node = doc.add_text_node("n1", "Architecture Overview", x=100, y=200)
    assert node.id == "n1"
    assert node.text == "Architecture Overview"
    assert node.node_type == CanvasNodeType.TEXT
    assert "n1" in doc.nodes


def test_canvas_add_file_node() -> None:
    doc = CanvasDocument()
    node = doc.add_file_node("f1", "src/vibe_studio/agents/coding_agent.py", x=50, y=50)
    assert node.node_type == CanvasNodeType.FILE
    assert "coding_agent" in node.file


def test_canvas_add_edge() -> None:
    doc = CanvasDocument()
    doc.add_text_node("n1", "A", x=0, y=0)
    doc.add_text_node("n2", "B", x=100, y=0)
    edge = doc.add_edge("e1", "n1", "n2", label="depends on")
    assert edge.from_node == "n1"
    assert edge.to_node == "n2"
    assert edge.label == "depends on"


def test_canvas_serialization_round_trip() -> None:
    doc = CanvasDocument()
    doc.add_text_node("c1", "Core Agent", x=0, y=0, color="#6366f1")
    doc.add_text_node("c2", "SuperAgent", x=300, y=0, color="#38bdf8")
    doc.add_edge("e1", "c1", "c2", label="extends")

    json_str = doc.to_json()
    data = json.loads(json_str)
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1

    restored = CanvasDocument.from_json(json_str)
    assert "c1" in restored.nodes
    assert "e1" in restored.edges
    assert restored.edges["e1"].label == "extends"


# ──────────────────────────────────────────────────────────────────────────────
# Workflow Engine Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_workflow_manual_trigger_executes() -> None:
    pipeline = WorkflowPipeline("Test Pipeline")
    n1 = WorkflowNode(id="t1", name="Trigger", kind=NodeKind.MANUAL_TRIGGER, params={"payload": {"event": "test"}})
    pipeline.add_node(n1)

    result = pipeline.execute()
    assert result["success"] is True
    assert "t1" in result["outputs"]


def test_workflow_shell_node_runs_command(tmp_path: Path) -> None:
    pipeline = WorkflowPipeline("Shell Test", workspace_root=str(tmp_path))
    n1 = WorkflowNode(id="t1", name="Trigger", kind=NodeKind.MANUAL_TRIGGER)
    n2 = WorkflowNode(id="t2", name="Echo", kind=NodeKind.SHELL_COMMAND, params={"command": "echo hello_world"})
    pipeline.add_node(n1)
    pipeline.add_node(n2)
    pipeline.add_edge("t1", "t2")

    result = pipeline.execute()
    assert result["success"] is True
    assert result["outputs"]["t2"]["exit_code"] == 0
    assert "hello_world" in result["outputs"]["t2"]["stdout"]


def test_workflow_python_node_executes() -> None:
    pipeline = WorkflowPipeline("Python Test")
    n1 = WorkflowNode(id="t1", name="Trigger", kind=NodeKind.MANUAL_TRIGGER)
    n2 = WorkflowNode(id="t2", name="Script", kind=NodeKind.PYTHON_SCRIPT,
                      params={"code": "output = {'computed': 42 * 2}"})
    pipeline.add_node(n1)
    pipeline.add_node(n2)
    pipeline.add_edge("t1", "t2")

    result = pipeline.execute()
    assert result["success"] is True
    assert result["outputs"]["t2"] == {"computed": 84}


def test_workflow_dag_topological_order() -> None:
    """Three-node linear chain executes in order."""
    pipeline = WorkflowPipeline("Chain Test")
    execution_order = []

    def progress(nid, status):
        if status == NodeExecutionStatus.RUNNING:
            execution_order.append(nid)

    n1 = WorkflowNode(id="a", name="A", kind=NodeKind.MANUAL_TRIGGER)
    n2 = WorkflowNode(id="b", name="B", kind=NodeKind.NOTIFICATION_ACTION, params={"message": "b"})
    n3 = WorkflowNode(id="c", name="C", kind=NodeKind.NOTIFICATION_ACTION, params={"message": "c"})
    pipeline.add_node(n1)
    pipeline.add_node(n2)
    pipeline.add_node(n3)
    pipeline.add_edge("a", "b")
    pipeline.add_edge("b", "c")

    pipeline.execute(progress_callback=progress)
    assert execution_order == ["a", "b", "c"]


def test_workflow_serialization_round_trip() -> None:
    pipeline = WorkflowPipeline("Roundtrip Pipeline")
    pipeline.add_node(WorkflowNode(id="x1", name="Trig", kind=NodeKind.MANUAL_TRIGGER, x=10, y=20))
    pipeline.add_node(WorkflowNode(id="x2", name="Notify", kind=NodeKind.NOTIFICATION_ACTION, params={"message": "done"}, x=200, y=20))
    pipeline.add_edge("x1", "x2")

    data = pipeline.to_dict()
    restored = WorkflowPipeline.from_dict(data)

    assert restored.name == "Roundtrip Pipeline"
    assert "x1" in restored.nodes
    assert "x2" in restored.nodes
    assert len(restored.edges) == 1
