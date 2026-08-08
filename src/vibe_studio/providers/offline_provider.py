"""OfflineFallbackProvider — rule-based fallback provider when network or Ollama is unavailable."""
from __future__ import annotations

import json
from typing import Any, Callable
from vibe_studio.providers.base import ModelInfo


class OfflineFallbackProvider:
    name = "offline-fallback"

    def __init__(self, **kwargs: Any):
        pass

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                provider=self.name,
                name="offline-deterministic",
                context_window=16384,
                capabilities=["chat", "code", "offline"],
                status="ready",
            )
        ]

    def test_connection(self) -> bool:
        return True

    def cancel(self) -> None:
        pass

    def generate(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        stream: bool = False,
        callback: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> str:
        res = "Offline mode active: Provider unavailable. Rule-based step executed."
        if stream and callback:
            callback(res)
        return res

    def chat(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        stream: bool = False,
        callback: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> str:
        res = "Offline mode active. Standard operations will execute using local tools."
        if stream and callback:
            callback(res)
        return res
