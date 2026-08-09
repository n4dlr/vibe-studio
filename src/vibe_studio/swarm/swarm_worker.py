"""Swarm Worker — Worker node that executes tasks dispatched from coordinator."""
from __future__ import annotations

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import threading
from typing import Optional
import urllib.request

from vibe_studio.agents.orchestrator import AgentOrchestrator
from vibe_studio.swarm.swarm_protocol import TaskRequest, TaskResult, TaskStatus, WorkerState, WorkerStatus

logger = logging.getLogger(__name__)


class SwarmWorkerHandler(BaseHTTPRequestHandler):
    """HTTP handler for worker node endpoints."""

    worker: Optional[SwarmWorker] = None

    def log_message(self, format: str, *args: float | str) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status = self.worker.status.to_dict() if self.worker else {"status": "ok"}
            self.wfile.write(json.dumps(status).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/execute":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            try:
                task_dict = json.loads(body)
                task = TaskRequest.from_dict(task_dict)
                result = self.worker.execute_task(task) if self.worker else None
                if result:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result.to_dict()).encode("utf-8"))
                    return
            except Exception as e:
                logger.error("Error executing task in worker: %s", e)
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return
        self.send_response(404)
        self.end_headers()


class SwarmWorker:
    """Worker node instance."""

    def __init__(self, worker_id: str, host: str = "127.0.0.1", port: int = 9100, coordinator_url: str = "http://127.0.0.1:9000", workspace_root: Optional[Path] = None):
        self.worker_id = worker_id
        self.host = host
        self.port = port
        self.coordinator_url = coordinator_url.rstrip("/")
        self.workspace_root = workspace_root or Path.cwd()
        self.status = WorkerStatus(worker_id=worker_id, host=host, port=port, state=WorkerState.IDLE)
        self.orchestrator = AgentOrchestrator(workspace_root=self.workspace_root)
        self.server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        handler = SwarmWorkerHandler
        handler.worker = self
        self.server = HTTPServer((self.host, self.port), handler)
        self._server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._server_thread.start()
        logger.info("Swarm worker %s listening on http://%s:%d", self.worker_id, self.host, self.port)
        self.register_with_coordinator()

    def register_with_coordinator(self) -> bool:
        url = f"{self.coordinator_url}/register"
        data = json.dumps(self.status.to_dict()).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    logger.info("Worker %s successfully registered with coordinator", self.worker_id)
                    return True
        except Exception as e:
            logger.warning("Could not register with coordinator at %s: %s", self.coordinator_url, e)
        return False

    def execute_task(self, task: TaskRequest) -> TaskResult:
        start_time = time.time()
        self.status.state = WorkerState.BUSY
        self.status.active_tasks += 1
        try:
            res = self.orchestrator.execute_task(prompt=task.prompt, active_file=task.active_file)
            exec_res = res.execution_result
            status = TaskStatus.COMPLETED if (exec_res and exec_res.status.value == "completed") else TaskStatus.FAILED
            modified = list(res.diffs.keys()) if res.diffs else []
            return TaskResult(
                task_id=task.task_id,
                worker_id=self.worker_id,
                status=status,
                summary=res.summary,
                files_modified=modified,
                execution_time_sec=round(time.time() - start_time, 2),
            )
        except Exception as e:
            logger.error("Task execution exception: %s", e)
            return TaskResult(
                task_id=task.task_id,
                worker_id=self.worker_id,
                status=TaskStatus.FAILED,
                summary=f"Execution error: {e}",
                error=str(e),
                execution_time_sec=round(time.time() - start_time, 2),
            )
        finally:
            self.status.active_tasks = max(0, self.status.active_tasks - 1)
            if self.status.active_tasks == 0:
                self.status.state = WorkerState.IDLE

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
