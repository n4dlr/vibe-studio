"""MessageBus — pub/sub inter-agent communication channel."""
from __future__ import annotations

from typing import Any, Callable
from dataclasses import dataclass, field


@dataclass
class AgentMessage:
    sender: str
    topic: str
    payload: dict[str, Any]
    timestamp: float = 0.0


class MessageBus:
    """Central message broker facilitating asynchronous communication between specialized agents."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[AgentMessage], None]]] = {}

    def subscribe(self, topic: str, callback: Callable[[AgentMessage], None]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        if callback not in self._subscribers[topic]:
            self._subscribers[topic].append(callback)

    def publish(self, message: AgentMessage) -> None:
        subscribers = self._subscribers.get(message.topic, [])
        for cb in subscribers:
            try:
                cb(message)
            except Exception:
                pass
