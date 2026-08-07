from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibe_studio.providers.base import AIProvider, ModelInfo, ProviderError


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def list_models(self) -> list[ModelInfo]:
        request = Request(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError):
            return []
        data = payload.get("data", [])
        return [
            ModelInfo(
                provider=self.name,
                name=item.get("id", "unknown"),
                context_window=int(item.get("context_window") or 4096),
                capabilities=["chat"],
                status="ready",
            )
            for item in data
        ]

    def generate(self, *, prompt: str, model: str, system_prompt: str | None = None, stream: bool = False, **kwargs) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a helpful coding assistant."},
                {"role": "user", "content": prompt},
            ],
            "stream": bool(stream),
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=kwargs.get("timeout", self.timeout)) as response:
                body = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ProviderError(f"OpenAI-compatible provider request failed: {exc}") from exc
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderError("OpenAI-compatible provider returned malformed JSON") from exc
        if "choices" in result and result["choices"]:
            return result["choices"][0].get("message", {}).get("content", "")
        return ""

    def test_connection(self) -> bool:
        try:
            self.list_models()
            return True
        except ProviderError:
            return False
