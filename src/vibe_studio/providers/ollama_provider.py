"""Ollama provider — local-first AI backend with streaming, tool calling, and cancellation."""
from __future__ import annotations

import json
import threading
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from vibe_studio.providers.base import ModelInfo, ProviderError


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: int = 120, num_ctx: int = 32768):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._num_ctx = num_ctx
        self._cancel_event = threading.Event()
        self.circuit_breaker = CircuitBreaker(name="ollama")

    # ------------------------------------------------------------------
    # Model discovery
    # ------------------------------------------------------------------

    def list_models(self) -> list[ModelInfo]:
        try:
            req = Request(
                f"{self.base_url}/api/tags",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []
        return [
            ModelInfo(
                provider=self.name,
                name=item.get("name", "unknown"),
                context_window=item.get("details", {}).get("parameter_size") or 8192,
                capabilities=["chat", "code", "tool_calling"],
                status="ready",
            )
            for item in payload.get("models", [])
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
    # Generation — non-streaming and streaming
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
        top_p: float = 0.9,
        **kwargs: Any,
    ) -> str:
        self._reset_cancel()
        model = self._resolve_model(model)

        def _do_generate():
            payload: dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "system": system_prompt or (
                    "You are an autonomous AI software engineer inside Vibe Studio IDE. "
                    "You can use tools to read files, search code, edit files, run tests, and fix errors."
                ),
                "stream": bool(stream and callback),
                "options": {
                    "temperature": temperature,
                    "top_p": top_p,
                    "num_ctx": kwargs.get("num_ctx", self._num_ctx),
                },
            }

            req = Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            timeout = kwargs.get("timeout", self.timeout)

            try:
                if stream and callback:
                    return self._stream_generate(req, callback, timeout, cancellation_token)
                with urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8")
                return json.loads(body).get("response", "")
            except (HTTPError, URLError, TimeoutError) as exc:
                raise ProviderError(f"Ollama generate failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise ProviderError("Ollama returned malformed JSON") from exc

        return self.circuit_breaker.call(_do_generate)

    def _stream_generate(
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
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line.decode("utf-8"))
                except Exception:
                    continue
                chunk = data.get("response", "")
                if chunk:
                    chunks.append(chunk)
                    callback(chunk)
                if data.get("done"):
                    break
        return "".join(chunks)

    # ------------------------------------------------------------------
    # Chat endpoint (multi-turn)
    # ------------------------------------------------------------------

    def chat(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        stream: bool = False,
        callback: Callable[[str], None] | None = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        self._reset_cancel()
        model = self._resolve_model(model)

        def _do_chat():
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": bool(stream and callback),
                "options": {
                    "temperature": temperature,
                    "num_ctx": kwargs.get("num_ctx", self._num_ctx),
                },
            }

            req = Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            timeout = kwargs.get("timeout", self.timeout)

            try:
                if stream and callback:
                    return self._stream_chat(req, callback, timeout, cancellation_token)
                with urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8")
                result = json.loads(body)
                return result.get("message", {}).get("content", "")
            except (HTTPError, URLError, TimeoutError) as exc:
                raise ProviderError(f"Ollama chat failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise ProviderError("Ollama chat returned malformed JSON") from exc

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
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line.decode("utf-8"))
                except Exception:
                    continue
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    chunks.append(chunk)
                    callback(chunk)
                if data.get("done"):
                    break
        return "".join(chunks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_model(self, model: str) -> str:
        """Fallback to a running model if the requested one is not available."""
        available = [m.name for m in self.list_models()]
        if not available:
            return model
        if model in available:
            return model
        # Prefer coding models
        for preference in ["coder", "qwen", "deepseek", "codellama", "llama"]:
            for m in available:
                if preference in m.lower():
                    return m
        return available[0]

