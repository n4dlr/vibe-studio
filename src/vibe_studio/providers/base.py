"""Provider base classes, shared dataclasses, and error hierarchy.

All Vibe Studio LLM providers implement the AIProvider protocol.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

from vibe_studio.providers.stream_events import StreamEvent


# ---------------------------------------------------------------------------
# Shared data structures
# ---------------------------------------------------------------------------

@dataclass
class ModelInfo:
    """Metadata about a model available from a provider."""
    provider: str
    name: str
    context_window: int = 0
    capabilities: list[str] = field(default_factory=list)
    status: str = "unknown"


@dataclass
class GenerationConfig:
    """Optional generation parameters forwarded to providers."""
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] = field(default_factory=list)
    seed: int | None = None


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------

class ProviderError(RuntimeError):
    """Base class for all provider errors."""


class ProviderConnectionError(ProviderError):
    """Raised when the provider cannot be reached (network / process)."""


class ProviderAuthError(ProviderError):
    """Raised when authentication fails (bad API key etc.)."""


class ProviderTimeoutError(ProviderError):
    """Raised when a request exceeds the configured timeout."""


class ProviderCancelledError(ProviderError):
    """Raised when a request was cancelled via CancellationToken."""


class ProviderParseError(ProviderError):
    """Raised when the provider response cannot be decoded/parsed."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class AIProvider(Protocol):
    """Minimal interface every Vibe Studio LLM provider must satisfy.

    Providers may optionally implement ``stream_generate`` for token-by-token
    streaming; ``generate`` is the blocking fallback.
    """

    name: str

    def list_models(self) -> list[ModelInfo]:
        """Return available models from this provider."""
        ...

    def generate(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        stream: bool = False,
        config: GenerationConfig | None = None,
        cancellation_token: Any = None,
        **kwargs: Any,
    ) -> str:
        """Blocking generation — returns the complete response text."""
        ...

    def stream_generate(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        config: GenerationConfig | None = None,
        cancellation_token: Any = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]:
        """Streaming generation — yields StreamEvent objects.

        Implementations MUST:
        - Yield at least one StreamEvent
        - Always yield a terminal event (COMPLETE, CANCELLED, or ERROR) last
        - Respect *cancellation_token.is_cancelled()* promptly
        - Never block the caller for more than ~100 ms between yields

        The default implementation delegates to ``generate`` and yields a
        single COMPLETE event, so providers only need to override if they
        support real streaming.
        """
        text = self.generate(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            config=config,
            cancellation_token=cancellation_token,
            **kwargs,
        )
        yield StreamEvent.complete(final_text=text)

    def test_connection(self) -> bool:
        """Return True if the provider endpoint is reachable."""
        ...

    def cancel(self) -> None:
        """Request cancellation of any in-flight request.

        Providers that do not support mid-request cancellation may implement
        this as a no-op; cancellation via CancellationToken should be
        preferred.
        """
        ...
