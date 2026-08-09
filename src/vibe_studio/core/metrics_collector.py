"""Metrics Collector for Vibe Studio.

Tracks execution duration, tool response times, provider latency, cancellation success rates, and errors.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List


class MetricsCollector:
    """Collects and aggregates runtime performance metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._durations: Dict[str, List[float]] = {}
        self._counters: Dict[str, int] = {}

    def record_duration(self, metric_name: str, duration: float) -> None:
        with self._lock:
            if metric_name not in self._durations:
                self._durations[metric_name] = []
            self._durations[metric_name].append(duration)

    def increment_counter(self, metric_name: str, count: int = 1) -> None:
        with self._lock:
            self._counters[metric_name] = self._counters.get(metric_name, 0) + count

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            summary: Dict[str, Any] = {"counters": dict(self._counters), "averages": {}}
            for name, values in self._durations.items():
                if values:
                    summary["averages"][name] = round(sum(values) / len(values), 4)
            return summary


default_metrics_collector = MetricsCollector()
