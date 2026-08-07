from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ModelInfo:
    provider: str
    name: str
    context_window: int = 0
    capabilities: list[str] = field(default_factory=list)
    status: str = "unknown"


class ProviderError(RuntimeError):
    pass


class AIProvider(Protocol):
    name: str

    def list_models(self) -> list[ModelInfo]:
        ...

    def generate(self, *, prompt: str, model: str, system_prompt: str | None = None, stream: bool = False, **kwargs: Any) -> str:
        ...

    def test_connection(self) -> bool:
        ...
