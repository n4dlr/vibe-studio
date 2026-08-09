"""Retry Manager for Vibe Studio.

Provides exponential backoff retries for transient errors.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Tuple, Type


class RetryManager:
    """Executes callables with exponential backoff on transient errors."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        backoff_factor: float = 2.0,
        retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.retryable_exceptions = retryable_exceptions

    def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        delay = self.base_delay
        attempt = 0

        while True:
            try:
                return func(*args, **kwargs)
            except self.retryable_exceptions as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise exc
                time.sleep(delay)
                delay = min(delay * self.backoff_factor, self.max_delay)
