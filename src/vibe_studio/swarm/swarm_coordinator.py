"""Swarm Coordinator — Manages worker registration, task dispatching, and heartbeat monitoring."""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Dict, List, Optional
import urllib.request
import urllib.error

from vibe_studio.swarm.swarm_protocol import (
    TaskRequest,
    TaskResult,
    TaskStatus,
    WorkerState,
    WorkerStatus,
)

logger = logging.getLogger(__name__)


class SwarmCoordinator:
    """Coordinator node for Swarm. Manages workers and dispatches tasks."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9000):
        self.host = host
        self.port = port
        self.workers: Dict[str, WorkerStatus] = {}
        self.tasks: Dict[str, TaskRequest] = {}
        self.results: Dict[str, TaskResult] = {}
        self.lock = threading.Lock()
        self.running = False
        self._heartbeat_thread: Optional[threading.Thread] = None

    def register_worker(self, worker: WorkerStatus) -> bool:
        with self.lock:
            self.workers[worker.worker_id] = worker
            logger.info("Worker registered: %s @ %s:%d", worker.worker_id, worker.host, worker.port)
            return True

    def unregister_worker(self, worker_id: str) -> None:
        with self.lock:
            if worker_id in self.workers:
                del self.workers[worker_id]
                logger.info("Worker unregistered: %s", worker_id)

    def get_idle_worker(self) -> Optional[WorkerStatus]:
        with self.lock:
            for worker in self.workers.values():
                if worker.state == WorkerState.IDLE and worker.active_tasks < worker.max_tasks:
                    return worker
            return None

    def list_workers(self) -> List[Dict]:
        with self.lock:
            return [w.to_dict() for w in self.workers.values()]

    def submit_task(self, prompt: str, active_file: Optional[str] = None, workspace_root: Optional[str] = None) -> TaskRequest:
        task = TaskRequest(prompt=prompt, active_file=active_file, workspace_root=workspace_root)
        with self.lock:
            self.tasks[task.task_id] = task

        worker = self.get_idle_worker()
        if worker:
            self.dispatch_task(task.task_id, worker.worker_id)
        return task

    def dispatch_task(self, task_id: str, worker_id: str) -> bool:
        with self.lock:
            if task_id not in self.tasks or worker_id not in self.workers:
                return False
            task = self.tasks[task_id]
            worker = self.workers[worker_id]

            task.assigned_worker = worker_id
            task.status = TaskStatus.RUNNING
            worker.state = WorkerState.BUSY
            worker.active_tasks += 1

        # Dispatch via HTTP call to worker endpoint
        def _dispatch():
            url = f"http://{worker.host}:{worker.port}/execute"
            req_data = json.dumps(task.to_dict()).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    result = TaskResult.from_dict(data)
                    self.record_result(result)
            except Exception as e:
                logger.error("Failed to dispatch task %s to worker %s: %s", task_id, worker_id, e)
                result = TaskResult(
                    task_id=task_id,
                    worker_id=worker_id,
                    status=TaskStatus.FAILED,
                    summary=f"Worker dispatch error: {e}",
                    error=str(e),
                )
                self.record_result(result)

        t = threading.Thread(target=_dispatch, daemon=True)
        t.start()
        return True

    def record_result(self, result: TaskResult) -> None:
        with self.lock:
            self.results[result.task_id] = result
            if result.task_id in self.tasks:
                self.tasks[result.task_id].status = result.status
            if result.worker_id in self.workers:
                worker = self.workers[result.worker_id]
                worker.active_tasks = max(0, worker.active_tasks - 1)
                if worker.active_tasks == 0:
                    worker.state = WorkerState.IDLE
        logger.info("Recorded task result for %s: %s", result.task_id, result.status.value)

    def start_heartbeat_monitor(self, interval_sec: float = 5.0) -> None:
        self.running = True

        def _monitor():
            while self.running:
                time.sleep(interval_sec)
                with self.lock:
                    dead_workers = []
                    for wid, worker in list(self.workers.items()):
                        # Check worker health
                        try:
                            req = urllib.request.Request(f"http://{worker.host}:{worker.port}/health")
                            with urllib.request.urlopen(req, timeout=2) as resp:
                                if resp.status != 200:
                                    dead_workers.append(wid)
                        except Exception:
                            dead_workers.append(wid)

                    for wid in dead_workers:
                        logger.warning("Worker %s failed heartbeat check, marking offline", wid)
                        self.workers[wid].state = WorkerState.OFFLINE

        self._heartbeat_thread = threading.Thread(target=_monitor, daemon=True)
        self._heartbeat_thread.start()

    def stop(self) -> None:
        self.running = False
