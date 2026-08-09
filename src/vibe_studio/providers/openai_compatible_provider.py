"""OpenAI-compatible provider — works with any OpenAI-format API including proxied Claude, Gemini, etc."""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from vibe_studio.providers.base import ModelInfo, ProviderError


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        # Accept key from constructor or env var
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY") or ""
        self.timeout = timeout
        self._cancel_event = threading.Event()
        self.circuit_breaker = CircuitBreaker(name="openai_compatible")

    # ------------------------------------------------------------------
    # Model discovery
    # ------------------------------------------------------------------

    def list_models(self) -> list[ModelInfo]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            req = Request(f"{self.base_url}/models", headers=headers)
            with urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
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

    def test_connection(self) -> bool:
        try:
            return len(self.list_models()) > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        self._cancel_event.set()

    def _reset_cancel(self) -> None:
        self._cancel_event.clear()

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    def generate(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        stream: bool = False,
        callback: Callable[[str], None] | None = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": system_prompt or (
                    "You are an autonomous AI software engineer inside Vibe Studio IDE."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        return self.chat(
            messages=messages,
            model=model,
            stream=stream,
            callback=callback,
            cancellation_token=cancellation_token,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def chat(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        stream: bool = False,
        callback: Callable[[str], None] | None = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        self._reset_cancel()

        def _do_chat():
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": bool(stream and callback),
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            req = Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            timeout = kwargs.get("timeout", self.timeout)

            try:
                if stream and callback:
                    return self._stream_chat(req, callback, timeout, cancellation_token)
                with urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8")
                result = json.loads(body)
                choices = result.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
            except (HTTPError, URLError, TimeoutError) as exc:
                raise ProviderError(f"OpenAI-compatible request failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise ProviderError("OpenAI-compatible provider returned malformed JSON") from exc

        return self.circuit_breaker.call(_do_chat)

    def _stream_chat(
        self,
        req: Request,
        callback: Callable[[str], None],
        timeout: int,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> str:
        chunks: list[str] = []
        with urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                if self._cancel_event.is_set() or (cancellation_token and cancellation_token.is_cancelled()):
                    break
                line = raw_line.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except Exception:
                    continue
                delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    chunks.append(delta)
                    callback(delta)
        return "".join(chunks)

