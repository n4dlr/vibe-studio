"""Cache Manager for Vibe Studio.

Provides LRU memory caching with TTL for LLM responses and tool outputs.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple


class CacheManager:
    """Thread-safe LRU Cache with Time-To-Live (TTL) expiration."""

    def __init__(self, max_size: int = 200, default_ttl_seconds: float = 300.0):
        self.max_size = max_size
        self.default_ttl = default_ttl_seconds
        # Key -> (value, expire_timestamp)
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            val, expire = self._cache[key]
            if time.time() > expire:
                self._cache.pop(key)
                return None
            self._cache.move_to_end(key)
            return val

    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expire = time.time() + ttl
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            elif len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            self._cache[key] = (value, expire)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


default_cache_manager = CacheManager()
