"""Workflow Engine — n8n-Grade Node-Based Visual Automation Pipeline.

Supports triggers, DAG execution, intermediate variable payloads ($json, $prev, $env),
conditional routing (If/Else), Playwright web actions, SuperAgent coding actions, and Python scripts.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class NodeKind(str, Enum):
    # Triggers
    MANUAL_TRIGGER      = "MANUAL_TRIGGER"
    CRON_TRIGGER        = "CRON_TRIGGER"
    FILE_WATCH_TRIGGER  = "FILE_WATCH_TRIGGER"
    GIT_HOOK_TRIGGER    = "GIT_HOOK_TRIGGER"

    # AI & Actions
    SUPER_AGENT_ACTION  = "SUPER_AGENT_ACTION"
    PLAYWRIGHT_ACTION   = "PLAYWRIGHT_ACTION"
    PYTHON_SCRIPT       = "PYTHON_SCRIPT"
    SHELL_COMMAND       = "SHELL_COMMAND"
    HTTP_REQUEST        = "HTTP_REQUEST"
    NOTIFICATION_ACTION = "NOTIFICATION_ACTION"

    # Flow & Logic
    CONDITION_BRANCH    = "CONDITION_BRANCH"
    LOOP_ITERATOR       = "LOOP_ITERATOR"
    DELAY_TIMER         = "DELAY_TIMER"


class NodeExecutionStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"
    SKIPPED   = "SKIPPED"


@dataclass
class WorkflowNode:
    id: str
    name: str
    kind: NodeKind
    params: dict[str, Any] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0
    status: NodeExecutionStatus = NodeExecutionStatus.PENDING
    last_output: Any = None
    error: str = ""
    duration: float = 0.0


@dataclass
class WorkflowEdge:
    source_id: str
    source_port: str = "output"
    target_id: str = "target"
    target_port: str = "input"


@dataclass
class WorkflowContext:
    variables: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    workspace_root: str = "."


class WorkflowPipeline:
    """Orchestrates node-based DAG workflow execution."""

    def __init__(self, name: str = "New Workflow", workspace_root: str = "."):
        self.name = name
        self.workspace_root = Path(workspace_root).resolve()
        self.nodes: dict[str, WorkflowNode] = {}
        self.edges: list[WorkflowEdge] = []
        self.context = WorkflowContext(workspace_root=str(self.workspace_root))

    def add_node(self, node: WorkflowNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, source_id: str, target_id: str, source_port: str = "output", target_port: str = "input") -> None:
        edge = WorkflowEdge(source_id=source_id, source_port=source_port, target_id=target_id, target_port=target_port)
        self.edges.append(edge)

    def execute(self, trigger_payload: Any = None, progress_callback: Optional[Callable[[str, NodeExecutionStatus], None]] = None) -> dict[str, Any]:
        """Execute the workflow graph in topological order."""
        logger.info("Executing workflow: %s", self.name)
        self.context.variables["$json"] = trigger_payload or {}
        self.context.variables["$prev"] = None

        # Reset statuses
        for node in self.nodes.values():
            node.status = NodeExecutionStatus.PENDING
            node.error = ""
            node.duration = 0.0

        # Build adjacency
        adj: dict[str, list[WorkflowEdge]] = {nid: [] for nid in self.nodes}
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}

        for edge in self.edges:
            if edge.source_id in adj:
                adj[edge.source_id].append(edge)
            if edge.target_id in in_degree:
                in_degree[edge.target_id] += 1

        # Queue starting nodes (in_degree == 0)
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        if not queue and self.nodes:
            queue = [next(iter(self.nodes))]

        executed_count = 0

        while queue:
            node_id = queue.pop(0)
            node = self.nodes.get(node_id)
            if not node:
                continue

            node.status = NodeExecutionStatus.RUNNING
            if progress_callback:
                progress_callback(node_id, node.status)

            start_t = time.monotonic()
            try:
                out = self._execute_node(node)
                node.last_output = out
                node.status = NodeExecutionStatus.SUCCESS
                self.context.node_outputs[node_id] = out
                self.context.variables["$prev"] = out
                if isinstance(out, dict):
                    self.context.variables["$json"] = {**self.context.variables.get("$json", {}), **out}
            except Exception as exc:
                node.status = NodeExecutionStatus.FAILED
                node.error = str(exc)
                logger.error("Node %s failed: %s", node.name, exc)

            node.duration = round(time.monotonic() - start_t, 3)
            if progress_callback:
                progress_callback(node_id, node.status)

            executed_count += 1

            # Follow outgoing edges
            if node.status == NodeExecutionStatus.SUCCESS:
                for edge in adj.get(node_id, []):
                    # Handle Condition branching port filter
                    if node.kind == NodeKind.CONDITION_BRANCH:
                        branch = "true" if bool(node.last_output) else "false"
                        if edge.source_port != branch and edge.source_port != "output":
                            continue

                    tgt = edge.target_id
                    in_degree[tgt] = max(0, in_degree.get(tgt, 1) - 1)
                    if in_degree[tgt] == 0 and tgt not in queue:
                        queue.append(tgt)

        return {
            "workflow": self.name,
            "executed_nodes": executed_count,
            "outputs": self.context.node_outputs,
            "success": all(n.status != NodeExecutionStatus.FAILED for n in self.nodes.values()),
        }

    def _execute_node(self, node: WorkflowNode) -> Any:
        kind = node.kind
        params = node.params
        prev_data = self.context.variables.get("$prev")

        if kind == NodeKind.MANUAL_TRIGGER:
            return params.get("payload", {"event": "manual_trigger", "timestamp": time.time()})

        elif kind == NodeKind.PYTHON_SCRIPT:
            code = params.get("code", "output = $prev")
            local_scope = {"$json": self.context.variables.get("$json", {}), "$prev": prev_data, "output": None}
            # Replace $ variables for python execution
            exec_code = code.replace("$json", "local_json").replace("$prev", "local_prev")
            scope = {"local_json": self.context.variables.get("$json", {}), "local_prev": prev_data, "output": None}
            exec(exec_code, {}, scope)
            return scope.get("output", "Python executed successfully")

        elif kind == NodeKind.SHELL_COMMAND:
            cmd = params.get("command", "echo 'Vibe Workflow'")
            import subprocess
            res = subprocess.run(cmd, shell=True, cwd=self.workspace_root, capture_output=True, text=True, timeout=30)
            return {"exit_code": res.returncode, "stdout": res.stdout.strip(), "stderr": res.stderr.strip()}

        elif kind == NodeKind.SUPER_AGENT_ACTION:
            prompt = params.get("prompt", "Analyze repository")
            from vibe_studio.swarm.specialist_swarm import SpecialistSwarm
            swarm = SpecialistSwarm(self.workspace_root)
            res = swarm.execute_mission(prompt)
            return {"success": res.success, "quality": res.quality_score.score, "summary": res.summary}

        elif kind == NodeKind.PLAYWRIGHT_ACTION:
            url = params.get("url", "https://example.com")
            from vibe_studio.tools.web_tools import WebTools
            web = WebTools()
            return web.fetch_webpage(url)

        elif kind == NodeKind.CONDITION_BRANCH:
            expr = params.get("expression", "True")
            # Evaluate expression against context
            val = prev_data
            if isinstance(val, dict):
                return bool(val.get(expr, True))
            return True

        elif kind == NodeKind.NOTIFICATION_ACTION:
            msg = params.get("message", "Workflow step finished")
            return {"notified": True, "message": msg}

        return {"status": "ok", "node": node.name}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "kind": n.kind.value,
                    "params": n.params,
                    "x": n.x,
                    "y": n.y,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source_id": e.source_id,
                    "source_port": e.source_port,
                    "target_id": e.target_id,
                    "target_port": e.target_port,
                }
                for e in self.edges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], workspace_root: str = ".") -> WorkflowPipeline:
        pipeline = cls(name=data.get("name", "Workflow"), workspace_root=workspace_root)
        for nd in data.get("nodes", []):
            node = WorkflowNode(
                id=nd["id"],
                name=nd["name"],
                kind=NodeKind(nd["kind"]),
                params=nd.get("params", {}),
                x=nd.get("x", 0.0),
                y=nd.get("y", 0.0),
            )
            pipeline.add_node(node)
        for ed in data.get("edges", []):
            pipeline.add_edge(
                source_id=ed["source_id"],
                target_id=ed["target_id"],
                source_port=ed.get("source_port", "output"),
                target_port=ed.get("target_port", "input"),
            )
        return pipeline
