"""Circuit Breaker for Vibe Studio AI Providers.

Prevents provider overload by transitioning between CLOSED, OPEN, and HALF_OPEN states.
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Callable


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Provider calls blocked
    HALF_OPEN = "HALF_OPEN"# Testing recovery


class CircuitBreakerOpenException(Exception):
    """Raised when a call is attempted on an OPEN circuit breaker."""
    pass


class CircuitBreaker:
    """Circuit Breaker protecting remote/local LLM providers from cascade failures."""

    def __init__(
        self,
        name: str = "provider",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = time.time()
        self._lock = threading.Lock()

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute func wrapped in circuit breaker protection."""
        with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_state_change > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.last_state_change = time.time()
                else:
                    raise CircuitBreakerOpenException(
                        f"Circuit breaker '{self.name}' is OPEN. Requests blocked."
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise exc

    def _on_success(self) -> None:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.last_state_change = time.time()
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    def _on_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            if self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.last_state_change = time.time()
