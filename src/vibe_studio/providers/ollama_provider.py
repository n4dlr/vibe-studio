from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibe_studio.providers.base import AIProvider, ModelInfo, ProviderError


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def list_models(self) -> list[ModelInfo]:
        request = Request(f"{self.base_url}/api/tags", headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError):
            return []
        models = payload.get("models", [])
        return [
            ModelInfo(
                provider=self.name,
                name=item.get("name", "unknown"),
                context_window=4096,
                capabilities=["chat", "code"],
                status="ready",
            )
            for item in models
        ]

    def generate(self, *, prompt: str, model: str, system_prompt: str | None = None, stream: bool = False, **kwargs) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt or "You are a helpful coding assistant.",
            "stream": bool(stream),
            "options": {
                "temperature": kwargs.get("temperature", 0.2),
                "top_p": kwargs.get("top_p", 0.9),
            },
        }
        request = Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=kwargs.get("timeout", self.timeout)) as response:
                body = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderError("Ollama returned malformed JSON") from exc
        return result.get("response", "")

    def test_connection(self) -> bool:
        try:
            self.list_models()
            return True
        except ProviderError:
            return False
