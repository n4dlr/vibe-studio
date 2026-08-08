from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibe_studio.providers.base import AIProvider, ModelInfo, ProviderError


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str = "https://api.openai.com/v1", api_key: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def list_models(self) -> list[ModelInfo]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(f"{self.base_url}/models", headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []
        data = payload.get("data", [])
        return [
            ModelInfo(
                provider=self.name,
                name=item.get("id", "unknown"),
                context_window=int(item.get("context_window") or 16384),
                capabilities=["chat", "code", "tool_calling"],
                status="ready",
            )
            for item in data
        ]

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
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt or "You are an autonomous AI software engineer inside Vibe Studio IDE."},
                {"role": "user", "content": prompt},
            ],
            "stream": bool(stream and callback),
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            if stream and callback:
                full_response = []
                with urlopen(request, timeout=kwargs.get("timeout", self.timeout)) as response:
                    for line in response:
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data: "):
                            data_str = line_str[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                delta = chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_response.append(delta)
                                    callback(delta)
                            except json.JSONDecodeError:
                                continue
                return "".join(full_response)
            else:
                with urlopen(request, timeout=kwargs.get("timeout", self.timeout)) as response:
                    body = response.read().decode("utf-8")
                result = json.loads(body)
                choices = result.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ProviderError(f"OpenAI-compatible request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError("OpenAI-compatible provider returned malformed JSON") from exc

    def test_connection(self) -> bool:
        try:
            models = self.list_models()
            return len(models) > 0
        except Exception:
            return False
