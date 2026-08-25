"""Tests for Distributed Agent Swarm."""
from __future__ import annotations

from pathlib import Path
import pytest

from vibe_studio.swarm.swarm_protocol import TaskRequest, TaskResult, TaskStatus, WorkerState, WorkerStatus
from vibe_studio.swarm.swarm_coordinator import SwarmCoordinator
from vibe_studio.swarm.swarm_worker import SwarmWorker


def test_swarm_protocol_serialization():
    w = WorkerStatus(worker_id="w1", host="127.0.0.1", port=9001)
    d = w.to_dict()
    assert d["worker_id"] == "w1"
    assert d["state"] == "idle"

    w_deser = WorkerStatus.from_dict(d)
    assert w_deser.worker_id == "w1"
    assert w_deser.state == WorkerState.IDLE


def test_swarm_coordinator_task_lifecycle(tmp_path):
    coord = SwarmCoordinator(host="127.0.0.1", port=9990)
    worker = WorkerStatus(worker_id="w1", host="127.0.0.1", port=9991)
    coord.register_worker(worker)

    assert len(coord.list_workers()) == 1
    assert coord.get_idle_worker().worker_id == "w1"

    task = coord.submit_task("Fix login bug", workspace_root=str(tmp_path))
    assert task.task_id in coord.tasks
    assert task.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.FAILED)


    result = TaskResult(
        task_id=task.task_id,
        worker_id="w1",
        status=TaskStatus.COMPLETED,
        summary="Fixed bug",
    )
    coord.record_result(result)
    assert coord.tasks[task.task_id].status == TaskStatus.COMPLETED
