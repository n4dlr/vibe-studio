"""Hierarchical CancellationToken implementation for Vibe Studio."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, List, Optional


class CancellationToken:
    """
    Thread-safe cancellation token supporting parent-child hierarchy and callbacks.
    """

    def __init__(self, parent: Optional["CancellationToken"] = None):
        self._event = threading.Event()
        self._callbacks: List[Callable[[], None]] = []
        self._lock = threading.RLock()
        self._parent = parent
        if parent is not None:
            parent.register_callback(self.cancel)

    def cancel(self) -> None:
        """Trigger cancellation and execute all registered callbacks idempotently."""
        callbacks_to_run: List[Callable[[], None]] = []
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            callbacks_to_run = list(self._callbacks)
            self._callbacks.clear()

        for cb in callbacks_to_run:
            try:
                cb()
            except Exception:
                pass

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested on this token or parent."""
        if self._event.is_set():
            return True
        if self._parent is not None and self._parent.is_cancelled():
            return True
        return False

    def check_cancelled(self) -> None:
        """Raise InterruptedError if cancellation was requested."""
        if self.is_cancelled():
            raise InterruptedError("Operation was cancelled.")

    def register_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """
        Register a callback to run when cancellation is requested.
        Returns an unregister function.
        """
        already_cancelled = False
        with self._lock:
            if self.is_cancelled():
                already_cancelled = True
            else:
                self._callbacks.append(callback)

        if already_cancelled:
            try:
                callback()
            except Exception:
                pass

        def unregister() -> None:
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)

        return unregister

    def create_child(self) -> "CancellationToken":
        """Create a child token that cancels when this parent cancels."""
        return CancellationToken(parent=self)

    def __enter__(self) -> "CancellationToken":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class CancellationTokenSource:
    """Convenience source that manages token lifecycle and optional timeouts."""

    def __init__(self, timeout_seconds: Optional[float] = None, parent: Optional[CancellationToken] = None):
        self.token = CancellationToken(parent=parent)
        self._timer: Optional[threading.Timer] = None
        if timeout_seconds is not None and timeout_seconds > 0:
            self._timer = threading.Timer(timeout_seconds, self.token.cancel)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self) -> None:
        self.token.cancel()
        if self._timer:
            self._timer.cancel()

    def close(self) -> None:
        if self._timer:
            self._timer.cancel()

    def __enter__(self) -> CancellationToken:
        return self.token

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
