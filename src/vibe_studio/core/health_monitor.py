"""Health Monitor for Vibe Studio.

Provides real-time agent heartbeat checking, stall detection, and health status monitoring.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional


class HealthMonitor:
    """Monitors heartbeat and detects stalled operations."""

    def __init__(self, stall_threshold_seconds: float = 30.0, check_interval_seconds: float = 5.0):
        self.stall_threshold = stall_threshold_seconds
        self.check_interval = check_interval_seconds
        self._last_heartbeat: Dict[str, float] = {}
        self._on_stall_callbacks: Dict[str, Callable[[str], None]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background health monitor thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the background monitor thread."""
        with self._lock:
            self._running = False

    def heartbeat(self, execution_id: str) -> None:
        """Record a heartbeat timestamp for an execution ID."""
        with self._lock:
            self._last_heartbeat[execution_id] = time.time()

    def register_execution(self, execution_id: str, on_stall: Callable[[str], None]) -> None:
        """Register an execution for stall monitoring with a callback."""
        with self._lock:
            self._last_heartbeat[execution_id] = time.time()
            self._on_stall_callbacks[execution_id] = on_stall

    def unregister_execution(self, execution_id: str) -> None:
        """Unregister an execution from stall monitoring."""
        with self._lock:
            self._last_heartbeat.pop(execution_id, None)
            self._on_stall_callbacks.pop(execution_id, None)

    def _monitor_loop(self) -> None:
        while self._running:
            time.sleep(self.check_interval)
            now = time.time()
            stalled: list[tuple[str, Callable[[str], None]]] = []

            with self._lock:
                for exec_id, last_time in list(self._last_heartbeat.items()):
                    if now - last_time > self.stall_threshold:
                        cb = self._on_stall_callbacks.get(exec_id)
                        if cb:
                            stalled.append((exec_id, cb))

            for exec_id, cb in stalled:
                try:
                    cb(exec_id)
                except Exception:
                    pass


default_health_monitor = HealthMonitor()
