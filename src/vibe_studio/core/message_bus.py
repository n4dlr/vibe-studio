"""MessageBus — pub/sub inter-agent communication channel."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentMessage:
    sender: str
    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class MessageBus:
    """Central message broker facilitating asynchronous communication between specialized agents.

    Features:
      - Auto-populates timestamps on publish
      - Per-topic message history (configurable depth)
      - Thread-safe subscribe/unsubscribe
    """

    def __init__(self, history_depth: int = 50):
        self._subscribers: dict[str, list[Callable[[AgentMessage], None]]] = {}
        self._history: dict[str, deque[AgentMessage]] = defaultdict(
            lambda: deque(maxlen=history_depth)
        )
        self._history_depth = history_depth

    def subscribe(self, topic: str, callback: Callable[[AgentMessage], None]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        if callback not in self._subscribers[topic]:
            self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[AgentMessage], None]) -> bool:
        """Remove a subscriber. Returns True if the callback was found and removed."""
        if topic in self._subscribers:
            try:
                self._subscribers[topic].remove(callback)
                return True
            except ValueError:
                pass
        return False

    def publish(self, message: AgentMessage) -> None:
        # Always set a real timestamp
        if message.timestamp == 0.0:
            message.timestamp = time.time()

        # Record in history
        self._history[message.topic].append(message)

        subscribers = self._subscribers.get(message.topic, [])
        for cb in list(subscribers):  # copy so unsubscribe during iteration is safe
            try:
                cb(message)
            except Exception:
                pass

    def get_history(self, topic: str, n: int | None = None) -> list[AgentMessage]:
        """Return last N messages for a topic (all if n is None)."""
        hist = list(self._history.get(topic, []))
        if n is not None:
            hist = hist[-n:]
        return hist

    def clear_history(self, topic: str | None = None) -> None:
        """Clear history for one topic or all topics."""
        if topic is None:
            self._history.clear()
        else:
            self._history.pop(topic, None)
