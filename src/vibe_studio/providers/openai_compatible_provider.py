"""OpenAI-compatible provider — works with any OpenAI-format API including proxied Claude, Gemini, etc."""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from vibe_studio.providers.base import ModelInfo, ProviderError
from vibe_studio.providers.stream_events import StreamEvent

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY") or ""
        self.timeout = timeout
        self._cancel_event = threading.Event()
        self._active_resp: Any = None
        self._resp_lock = threading.Lock()
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
    # Cancellation — idempotent, propagates via socket abort
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._resp_lock:
            resp = self._active_resp
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def _reset_cancel(self) -> None:
        self._cancel_event.clear()
        with self._resp_lock:
            self._active_resp = None

    def _is_cancelled(self, cancellation_token: Optional[CancellationToken]) -> bool:
        if self._cancel_event.is_set():
            return True
        if cancellation_token and cancellation_token.is_cancelled():
            return True
        return False

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
        event_callback: Callable[[StreamEvent], None] | None = None,
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
            event_callback=event_callback,
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
        event_callback: Callable[[StreamEvent], None] | None = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        self._reset_cancel()

        unreg = None
        if cancellation_token is not None:
            unreg = cancellation_token.register_callback(self.cancel)

        try:
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
                        return self._stream_chat(req, callback, event_callback, timeout, cancellation_token)
                    with urlopen(req, timeout=timeout) as resp:
                        body = resp.read().decode("utf-8", errors="replace")
                    result = json.loads(body)
                    choices = result.get("choices", [])
                    usage = result.get("usage", {})
                    content = choices[0].get("message", {}).get("content", "") if choices else ""
                    if event_callback:
                        event_callback(StreamEvent.complete(
                            content,
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                        ))
                    return content
                except (HTTPError, URLError, TimeoutError) as exc:
                    if self._is_cancelled(cancellation_token):
                        if event_callback:
                            event_callback(StreamEvent.cancelled())
                        return ""
                    raise ProviderError(f"OpenAI-compatible request failed: {exc}") from exc
                except json.JSONDecodeError as exc:
                    raise ProviderError("OpenAI-compatible provider returned malformed JSON") from exc

            return self.circuit_breaker.call(_do_chat)
        finally:
            if unreg:
                unreg()

    def _stream_chat(
        self,
        req: Request,
        callback: Callable[[str], None],
        event_callback: Callable[[StreamEvent], None] | None,
        timeout: int,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> str:
        chunks: list[str] = []
        in_thinking = False
        prompt_tokens = 0
        completion_tokens = 0

        try:
            resp = urlopen(req, timeout=timeout)
            with self._resp_lock:
                self._active_resp = resp
            with resp:
                for raw_line in resp:
                    if self._is_cancelled(cancellation_token):
                        if event_callback:
                            event_callback(StreamEvent.cancelled())
                        break
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        if event_callback:
                            event_callback(StreamEvent.complete(
                                "".join(chunks),
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            ))
                        break
                    try:
                        data = json.loads(data_str)
                    except (json.JSONDecodeError, ValueError):
                        logger.debug("OpenAI provider: skipping malformed SSE chunk: %r", data_str[:80])
                        continue

                    usage = data.get("usage")
                    if usage:
                        prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                        completion_tokens = usage.get("completion_tokens", completion_tokens)

                    delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        chunks.append(delta)
                        if "<think>" in delta:
                            in_thinking = True
                        if in_thinking:
                            if event_callback:
                                event_callback(StreamEvent.thinking(delta))
                            if "</think>" in delta:
                                in_thinking = False
                        else:
                            callback(delta)
                            if event_callback:
                                event_callback(StreamEvent.token(delta))
        except (OSError, Exception) as exc:
            if self._is_cancelled(cancellation_token):
                if event_callback:
                    event_callback(StreamEvent.cancelled("Stream cancelled"))
            else:
                logger.warning("OpenAI stream interrupted: %s", exc)
                if event_callback:
                    event_callback(StreamEvent.error(f"Stream error: {exc}"))
        finally:
            with self._resp_lock:
                self._active_resp = None
        return "".join(chunks)
