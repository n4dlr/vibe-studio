"""Normalized LLM stream event protocol for Vibe Studio providers.

Provides a unified StreamEvent dataclass used by all providers so the rest
of the codebase only needs to handle a single event type hierarchy.
"""
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
class TokenUsage:
    """Token accounting snapshot emitted with COMPLETE events."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class StreamEvent:
    """A normalized event emitted by any LLM provider during streaming."""

    event_type: StreamEventType
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def token(cls, text: str, **kwargs: Any) -> "StreamEvent":
        return cls(event_type=StreamEventType.TOKEN, content=text, metadata=kwargs)

    @classmethod
    def thinking(cls, text: str, **kwargs: Any) -> "StreamEvent":
        return cls(event_type=StreamEventType.THINKING, content=text, metadata=kwargs)

    @classmethod
    def tool_call(cls, tool_name: str, args: dict[str, Any], **kwargs: Any) -> "StreamEvent":
        return cls(
            event_type=StreamEventType.TOOL_CALL,
            content=tool_name,
            metadata={"args": args, **kwargs},
        )

    @classmethod
    def tool_result(cls, tool_name: str, result: Any, success: bool = True, **kwargs: Any) -> "StreamEvent":
        return cls(
            event_type=StreamEventType.TOOL_RESULT,
            content=tool_name,
            metadata={"result": result, "success": success, **kwargs},
        )

    @classmethod
    def error(cls, error_msg: str, recoverable: bool = True, **kwargs: Any) -> "StreamEvent":
        return cls(
            event_type=StreamEventType.ERROR,
            content=error_msg,
            metadata={"recoverable": recoverable, **kwargs},
        )

    @classmethod
    def status(cls, status_str: str, **kwargs: Any) -> "StreamEvent":
        return cls(event_type=StreamEventType.STATUS, content=status_str, metadata=kwargs)

    @classmethod
    def complete(
        cls,
        final_text: str = "",
        usage: TokenUsage | None = None,
        **kwargs: Any,
    ) -> "StreamEvent":
        meta: dict[str, Any] = kwargs
        if usage is not None:
            meta["usage"] = usage.as_dict
        return cls(event_type=StreamEventType.COMPLETE, content=final_text, metadata=meta)

    @classmethod
    def cancelled(cls, reason: str = "Cancelled by user", **kwargs: Any) -> "StreamEvent":
        return cls(event_type=StreamEventType.CANCELLED, content=reason, metadata=kwargs)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def is_terminal(self) -> bool:
        """Return True if this event signals the end of the stream."""
        return self.event_type in (
            StreamEventType.COMPLETE,
            StreamEventType.CANCELLED,
            StreamEventType.ERROR,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "content": self.content,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        snippet = self.content[:60].replace("\n", "\\n")
        return f"StreamEvent({self.event_type.value!r}, {snippet!r})"
