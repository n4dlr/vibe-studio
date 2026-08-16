"""Ollama provider — local-first AI backend with streaming, tool calling, and cancellation."""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from vibe_studio.providers.base import ModelInfo, ProviderError
from vibe_studio.providers.stream_events import StreamEvent

logger = logging.getLogger(__name__)


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: int = 120, num_ctx: int = 32768):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._num_ctx = num_ctx
        self._cancel_event = threading.Event()
        self._active_resp: Any = None  # holds open HTTP response for socket abort
        self._resp_lock = threading.Lock()
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
    # Cancellation — idempotent and propagates via socket abort
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
        event_callback: Callable[[StreamEvent], None] | None = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs: Any,
    ) -> str:
        self._reset_cancel()
        model = self._resolve_model(model)

        unreg = None
        if cancellation_token is not None:
            unreg = cancellation_token.register_callback(self.cancel)

        try:
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
                        return self._stream_generate(req, callback, event_callback, timeout, cancellation_token)
                    with urlopen(req, timeout=timeout) as resp:
                        body = resp.read().decode("utf-8", errors="replace")
                    data = json.loads(body)
                    resp_text = data.get("response", "")
                    if event_callback:
                        event_callback(StreamEvent.complete(
                            resp_text,
                            prompt_tokens=data.get("prompt_eval_count", 0),
                            completion_tokens=data.get("eval_count", 0),
                        ))
                    return resp_text
                except (HTTPError, URLError, TimeoutError) as exc:
                    if self._is_cancelled(cancellation_token):
                        if event_callback:
                            event_callback(StreamEvent.cancelled())
                        return ""
                    raise ProviderError(f"Ollama generate failed: {exc}") from exc
                except json.JSONDecodeError as exc:
                    raise ProviderError("Ollama returned malformed JSON") from exc

            return self.circuit_breaker.call(_do_generate)
        finally:
            if unreg:
                unreg()

    def _stream_generate(
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
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        data = json.loads(raw_line.decode("utf-8", errors="replace"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        logger.debug("Ollama: skipping malformed chunk: %r", raw_line[:80])
                        continue

                    chunk = data.get("response", "")
                    if data.get("prompt_eval_count"):
                        prompt_tokens = data.get("prompt_eval_count", 0)
                    if data.get("eval_count"):
                        completion_tokens = data.get("eval_count", 0)

                    if chunk:
                        chunks.append(chunk)
                        # Detect <think> tags for thinking stream events
                        if "<think>" in chunk:
                            in_thinking = True
                        if in_thinking:
                            if event_callback:
                                event_callback(StreamEvent.thinking(chunk))
                            if "</think>" in chunk:
                                in_thinking = False
                        else:
                            callback(chunk)
                            if event_callback:
                                event_callback(StreamEvent.token(chunk))

                    if data.get("done"):
                        if event_callback:
                            event_callback(StreamEvent.complete(
                                "".join(chunks),
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            ))
                        break
        except (OSError, Exception) as exc:
            if self._is_cancelled(cancellation_token):
                if event_callback:
                    event_callback(StreamEvent.cancelled("Stream cancelled"))
            else:
                logger.warning("Ollama stream interrupted: %s", exc)
                if event_callback:
                    event_callback(StreamEvent.error(f"Stream error: {exc}"))
        finally:
            with self._resp_lock:
                self._active_resp = None
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
        event_callback: Callable[[StreamEvent], None] | None = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        self._reset_cancel()
        model = self._resolve_model(model)

        unreg = None
        if cancellation_token is not None:
            unreg = cancellation_token.register_callback(self.cancel)

        try:
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
                        return self._stream_chat(req, callback, event_callback, timeout, cancellation_token)
                    with urlopen(req, timeout=timeout) as resp:
                        body = resp.read().decode("utf-8", errors="replace")
                    result = json.loads(body)
                    msg_content = result.get("message", {}).get("content", "")
                    if event_callback:
                        event_callback(StreamEvent.complete(
                            msg_content,
                            prompt_tokens=result.get("prompt_eval_count", 0),
                            completion_tokens=result.get("eval_count", 0),
                        ))
                    return msg_content
                except (HTTPError, URLError, TimeoutError) as exc:
                    if self._is_cancelled(cancellation_token):
                        if event_callback:
                            event_callback(StreamEvent.cancelled())
                        return ""
                    raise ProviderError(f"Ollama chat failed: {exc}") from exc
                except json.JSONDecodeError as exc:
                    raise ProviderError("Ollama chat returned malformed JSON") from exc

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
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        data = json.loads(raw_line.decode("utf-8", errors="replace"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        logger.debug("Ollama chat: skipping malformed chunk: %r", raw_line[:80])
                        continue

                    if data.get("prompt_eval_count"):
                        prompt_tokens = data.get("prompt_eval_count", 0)
                    if data.get("eval_count"):
                        completion_tokens = data.get("eval_count", 0)

                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        chunks.append(chunk)
                        if "<think>" in chunk:
                            in_thinking = True
                        if in_thinking:
                            if event_callback:
                                event_callback(StreamEvent.thinking(chunk))
                            if "</think>" in chunk:
                                in_thinking = False
                        else:
                            callback(chunk)
                            if event_callback:
                                event_callback(StreamEvent.token(chunk))

                    if data.get("done"):
                        if event_callback:
                            event_callback(StreamEvent.complete(
                                "".join(chunks),
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            ))
                        break
        except (OSError, Exception) as exc:
            if self._is_cancelled(cancellation_token):
                if event_callback:
                    event_callback(StreamEvent.cancelled("Stream cancelled"))
            else:
                logger.warning("Ollama chat stream interrupted: %s", exc)
                if event_callback:
                    event_callback(StreamEvent.error(f"Stream error: {exc}"))
        finally:
            with self._resp_lock:
                self._active_resp = None
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
