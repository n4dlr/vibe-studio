"""Centralized Resource Manager for Vibe Studio.

Tracks subprocesses, threads, file handles, and network connections per execution_id.
Supports lifecycle hooks and guaranteed cleanup.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from typing import Any, Callable, Dict, List, Set, Tuple


class ResourceManager:
    """Centralized manager for application and task resources."""

    def __init__(self):
        self._lock = threading.Lock()
        # Map execution_id -> list of subprocess.Popen instances
        self._subprocesses: Dict[str, List[subprocess.Popen]] = {}
        # Map execution_id -> list of open file handles
        self._file_handles: Dict[str, List[Any]] = {}
        # Map execution_id -> set of active resource names
        self._allocated_resources: Dict[str, Set[str]] = {}
        # Lifecycle hooks
        self._on_allocated_hooks: List[Callable[[str, str], None]] = []
        self._on_released_hooks: List[Callable[[str, str], None]] = []

    def register_subprocess(self, execution_id: str, proc: subprocess.Popen) -> None:
        """Register an active subprocess with an execution ID."""
        with self._lock:
            if execution_id not in self._subprocesses:
                self._subprocesses[execution_id] = []
            self._subprocesses[execution_id].append(proc)
            res_id = f"proc_{proc.pid}"
            self._record_allocation(execution_id, res_id)

    def register_file_handle(self, execution_id: str, handle: Any) -> None:
        """Register an open file handle with an execution ID."""
        with self._lock:
            if execution_id not in self._file_handles:
                self._file_handles[execution_id] = []
            self._file_handles[execution_id].append(handle)
            res_id = f"file_{id(handle)}"
            self._record_allocation(execution_id, res_id)

    def _record_allocation(self, execution_id: str, resource_name: str) -> None:
        if execution_id not in self._allocated_resources:
            self._allocated_resources[execution_id] = set()
        self._allocated_resources[execution_id].add(resource_name)
        for hook in self._on_allocated_hooks:
            try:
                hook(execution_id, resource_name)
            except Exception:
                pass

    def cleanup_execution(self, execution_id: str) -> None:
        """Force termination and cleanup of all resources associated with an execution ID."""
        procs_to_kill: List[subprocess.Popen] = []
        handles_to_close: List[Any] = []

        with self._lock:
            procs_to_kill = self._subprocesses.pop(execution_id, [])
            handles_to_close = self._file_handles.pop(execution_id, [])
            allocated = self._allocated_resources.pop(execution_id, set())

        # Clean subprocesses
        for proc in procs_to_kill:
            if proc.poll() is None:
                try:
                    # Attempt graceful SIGTERM
                    proc.terminate()
                    try:
                        proc.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        # Fallback to process tree SIGKILL
                        self._kill_process_tree(proc.pid)
                except Exception:
                    pass

        # Clean file handles
        for handle in handles_to_close:
            try:
                if hasattr(handle, "close"):
                    handle.close()
            except Exception:
                pass

        for res_name in allocated:
            for hook in self._on_released_hooks:
                try:
                    hook(execution_id, res_name)
                except Exception:
                    pass

    def _kill_process_tree(self, pid: int) -> None:
        """Kill a process and its children cross-platform."""
        if os.name == "nt":
            try:
                subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        else:
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass

    def add_allocation_hook(self, hook: Callable[[str, str], None]) -> None:
        self._on_allocated_hooks.append(hook)

    def add_release_hook(self, hook: Callable[[str, str], None]) -> None:
        self._on_released_hooks.append(hook)

    def get_active_count(self, execution_id: str) -> int:
        with self._lock:
            return len(self._allocated_resources.get(execution_id, set()))


# Global singleton instance
default_resource_manager = ResourceManager()
