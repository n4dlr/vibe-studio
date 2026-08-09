"""Suggestion Cache — High performance LRU cache for predictive coding hints."""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional


class SuggestionCache:
    """LRU Cache with TTL expiration for coding suggestions."""

    def __init__(self, capacity: int = 100, ttl_seconds: float = 30.0):
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[float, List[Dict[str, Any]]]] = OrderedDict()

    def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        if key not in self._cache:
            return None
        ts, items = self._cache[key]
        if time.time() - ts > self.ttl_seconds:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return items

    def put(self, key: str, items: List[Dict[str, Any]]) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), items)
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()
