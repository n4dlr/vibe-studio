"""Normalized LLM stream event protocol for Vibe Studio providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    TOKEN       = "TOKEN"
    THINKING    = "THINKING"
    TOOL_CALL   = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    ERROR       = "ERROR"
    STATUS      = "STATUS"
    COMPLETE    = "COMPLETE"
    CANCELLED   = "CANCELLED"


@dataclass
class StreamEvent:
    event_type: StreamEventType
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def token(cls, text: str, **kwargs: Any) -> StreamEvent:
        return cls(event_type=StreamEventType.TOKEN, content=text, metadata=kwargs)

    @classmethod
    def thinking(cls, text: str, **kwargs: Any) -> StreamEvent:
        return cls(event_type=StreamEventType.THINKING, content=text, metadata=kwargs)

    @classmethod
    def tool_call(cls, tool_name: str, args: dict[str, Any], **kwargs: Any) -> StreamEvent:
        return cls(event_type=StreamEventType.TOOL_CALL, content=tool_name, metadata={"args": args, **kwargs})

    @classmethod
    def error(cls, error_msg: str, **kwargs: Any) -> StreamEvent:
        return cls(event_type=StreamEventType.ERROR, content=error_msg, metadata=kwargs)

    @classmethod
    def status(cls, status_str: str, **kwargs: Any) -> StreamEvent:
        return cls(event_type=StreamEventType.STATUS, content=status_str, metadata=kwargs)

    @classmethod
    def complete(cls, final_text: str = "", **kwargs: Any) -> StreamEvent:
        return cls(event_type=StreamEventType.COMPLETE, content=final_text, metadata=kwargs)

    @classmethod
    def cancelled(cls, reason: str = "Cancelled by user", **kwargs: Any) -> StreamEvent:
        return cls(event_type=StreamEventType.CANCELLED, content=reason, metadata=kwargs)
