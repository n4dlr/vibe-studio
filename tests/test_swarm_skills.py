"""Tests for Intelligent Skill-Based Swarm Routing."""
from __future__ import annotations

import pytest
from vibe_studio.swarm.swarm_protocol import TaskRequest, WorkerStatus, WorkerState
from vibe_studio.swarm.swarm_coordinator import SwarmCoordinator


def test_swarm_skill_matching():
    coord = SwarmCoordinator()

    w_general = WorkerStatus(worker_id="w_gen", host="127.0.0.1", port=9001, skills=["python", "refactor"])
    w_security = WorkerStatus(worker_id="w_sec", host="127.0.0.1", port=9002, skills=["security", "audit", "auth"], performance_rating=1.5)

    coord.register_worker(w_general)
    coord.register_worker(w_security)

    # Task requiring security skill should route to w_security
    task_sec = TaskRequest(prompt="Audit security flaws in auth module", required_skills=["security"])
    best_sec = coord.get_best_worker_for_task(task_sec)
    assert best_sec is not None
    assert best_sec.worker_id == "w_sec"

    # Task requiring refactor should route to w_general
    task_refactor = TaskRequest(prompt="Refactor clean code", required_skills=["refactor"])
    best_refactor = coord.get_best_worker_for_task(task_refactor)
    assert best_refactor is not None
    assert best_refactor.worker_id == "w_gen"
