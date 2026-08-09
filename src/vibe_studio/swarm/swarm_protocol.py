"""Swarm Protocol — Data structures and serialization for distributed agents."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class WorkerState(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkerStatus:
    worker_id: str
    host: str
    port: int
    state: WorkerState = WorkerState.IDLE
    active_tasks: int = 0
    max_tasks: int = 4
    capabilities: list[str] = field(default_factory=lambda: ["python", "refactor", "test"])

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkerStatus:
        data_copy = dict(data)
        if "state" in data_copy and isinstance(data_copy["state"], str):
            data_copy["state"] = WorkerState(data_copy["state"])
        return cls(**data_copy)


@dataclass
class TaskRequest:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str = ""
    active_file: Optional[str] = None
    workspace_root: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    assigned_worker: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskRequest:
        data_copy = dict(data)
        if "status" in data_copy and isinstance(data_copy["status"], str):
            data_copy["status"] = TaskStatus(data_copy["status"])
        return cls(**data_copy)


@dataclass
class TaskResult:
    task_id: str
    worker_id: str
    status: TaskStatus
    summary: str
    files_modified: list[str] = field(default_factory=list)
    error: Optional[str] = None
    execution_time_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskResult:
        data_copy = dict(data)
        if "status" in data_copy and isinstance(data_copy["status"], str):
            data_copy["status"] = TaskStatus(data_copy["status"])
        return cls(**data_copy)


def create_jsonrpc_request(method: str, params: Dict[str, Any], msg_id: Optional[str] = None) -> str:
    return json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": msg_id or str(uuid.uuid4())
    })


def create_jsonrpc_response(result: Any, msg_id: str, error: Optional[Dict[str, Any]] = None) -> str:
    resp: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": msg_id
    }
    if error:
        resp["error"] = error
    else:
        resp["result"] = result
    return json.dumps(resp)
