from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibe_studio.providers.base import AIProvider, ModelInfo, ProviderError


class HttpProvider:
    name = "http"

    def __init__(self, base_url: str, api_key: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(provider=self.name, name="custom-model", context_window=4096, capabilities=["chat"], status="configured")]

    def generate(self, *, prompt: str, model: str, system_prompt: str | None = None, stream: bool = False, **kwargs) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "system_prompt": system_prompt or "You are a helpful coding assistant.",
            "stream": bool(stream),
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
            raise ProviderError(f"HTTP provider request failed: {exc}") from exc
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderError("HTTP provider returned malformed JSON") from exc
        if "choices" in result and result["choices"]:
            return result["choices"][0].get("message", {}).get("content", "")
        if "response" in result:
            return result["response"]
        return ""

    def test_connection(self) -> bool:
        return True
