from __future__ import annotations

import json
from typing import Any, Callable
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
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []
        models = payload.get("models", [])
        return [
            ModelInfo(
                provider=self.name,
                name=item.get("name", "unknown"),
                context_window=8192,
                capabilities=["chat", "code", "tool_calling"],
                status="ready",
            )
            for item in models
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
        available = self.list_models()
        available_names = [m.name for m in available]
        target_model = model

        if available_names and target_model not in available_names:
            # Fallback to matching model or first available model
            code_models = [m for m in available_names if "coder" in m or "qwen" in m]
            target_model = code_models[0] if code_models else available_names[0]

        payload = {
            "model": target_model,
            "prompt": prompt,
            "system": system_prompt or "You are an autonomous AI software engineer inside Vibe Studio IDE.",
            "stream": bool(stream and callback),
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
            if stream and callback:
                full_response = []
                with urlopen(request, timeout=kwargs.get("timeout", self.timeout)) as response:
                    for line in response:
                        if line:
                            data = json.loads(line.decode("utf-8"))
                            chunk = data.get("response", "")
                            full_response.append(chunk)
                            callback(chunk)
                return "".join(full_response)
            else:
                with urlopen(request, timeout=kwargs.get("timeout", self.timeout)) as response:
                    body = response.read().decode("utf-8")
                result = json.loads(body)
                return result.get("response", "")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError("Ollama returned malformed JSON") from exc

    def test_connection(self) -> bool:
        try:
            models = self.list_models()
            return len(models) > 0
        except Exception:
            return False
