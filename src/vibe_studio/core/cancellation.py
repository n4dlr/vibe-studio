"""Hierarchical CancellationToken implementation for Vibe Studio."""
from __future__ import annotations

import threading
from typing import Any, Callable, List, Optional


class CancellationToken:
    """
    Thread-safe cancellation token supporting parent-child hierarchy and callbacks.
    """

    def __init__(self, parent: Optional["CancellationToken"] = None):
        self._event = threading.Event()
        self._callbacks: List[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._parent = parent
        if parent is not None:
            parent.register_callback(self.cancel)

    def cancel(self) -> None:
        """Trigger cancellation and execute all registered callbacks."""
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            callbacks = list(self._callbacks)
            self._callbacks.clear()

        for cb in callbacks:
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

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to run when cancellation is requested."""
        with self._lock:
            if self._event.is_set() or (self._parent and self._parent.is_cancelled()):
                already_cancelled = True
            else:
                already_cancelled = False
                self._callbacks.append(callback)

        if already_cancelled:
            try:
                callback()
            except Exception:
                pass

    def create_child(self) -> "CancellationToken":
        """Create a child token that cancels when this parent cancels."""
        return CancellationToken(parent=self)
