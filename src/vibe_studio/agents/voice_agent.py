"""VoiceAgent — conversational AI agent powered by local Ollama LLM.

Designed to work well with mini models (1B – 3B parameters) in both
English and Azerbaijani.  The system prompt is intentionally compact so
small-context models (2 k–4 k tokens) still give coherent answers.

Usage
-----
    agent = VoiceAgent(provider=ollama_provider, model="qwen2.5:1.5b",
                       workspace_root="/path/to/project")
    reply = agent.chat("Salam, bu layihə nə edir?")
    print(reply)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — compact for 2B models
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """You are a helpful voice assistant integrated into Vibe Studio, an AI-powered coding IDE.

Rules:
- Always reply in the SAME LANGUAGE the user writes in (Azerbaijani or English).
- Keep answers SHORT and spoken-friendly (1-4 sentences max unless asked for more).
- You know the current workspace: {workspace_name}
- You can help with: code questions, project structure, debugging hints, explanations.
- Never use markdown formatting (no **, no #, no backticks) — answers are spoken aloud.
- Be conversational and friendly.

Current workspace: {workspace_name}
"""

_SYSTEM_PROMPT_NO_WORKSPACE = """You are a helpful voice assistant integrated into Vibe Studio, an AI-powered coding IDE.

Rules:
- Always reply in the SAME LANGUAGE the user writes in (Azerbaijani or English).
- Keep answers SHORT and spoken-friendly (1-4 sentences max unless asked for more).
- You can help with: coding questions, debugging, explanations, best practices.
- Never use markdown formatting (no **, no #, no backticks) — answers are spoken aloud.
- Be conversational and friendly.
"""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class VoiceMessage:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class VoiceAgentConfig:
    """Configuration for VoiceAgent."""
    model: str = "qwen2.5:1.5b"
    max_history_messages: int = 8          # Keep last N messages (2B friendly)
    max_tokens: int = 256                  # Short spoken replies
    temperature: float = 0.7
    stream: bool = True
    tts_enabled: bool = True
    language_hint: str | None = None       # None = auto-detect


# ---------------------------------------------------------------------------
# VoiceAgent
# ---------------------------------------------------------------------------

class VoiceAgent:
    """Local conversational agent for voice interaction.

    Parameters
    ----------
    provider:
        Any ``AIProvider``-compatible object (typically ``OllamaProvider``).
    model:
        Ollama model name. Recommended: ``qwen2.5:1.5b`` or ``qwen2.5:3b``
        for good Azerbaijani support.
    workspace_root:
        Path to the current project — shown in system prompt for context.
    config:
        Optional ``VoiceAgentConfig`` to override defaults.
    stream_callback:
        Called with each text token as they stream from the LLM.
    """

    def __init__(
        self,
        provider: Any,
        model: str = "qwen2.5:1.5b",
        workspace_root: str | Path | None = None,
        config: VoiceAgentConfig | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ):
        self._provider = provider
        self._model = model
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._config = config or VoiceAgentConfig(model=model)
        self._stream_callback = stream_callback
        self._history: list[VoiceMessage] = []
        self._is_running = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._model = value
        self._config.model = value

    @property
    def history(self) -> list[VoiceMessage]:
        return list(self._history)

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        if self._workspace_root:
            return _SYSTEM_PROMPT_TEMPLATE.format(
                workspace_name=self._workspace_root.name
            )
        return _SYSTEM_PROMPT_NO_WORKSPACE

    # ------------------------------------------------------------------
    # Conversation history → Ollama messages format
    # ------------------------------------------------------------------

    def _build_messages_payload(self) -> list[dict]:
        """Build the messages list for Ollama chat API.

        Keeps only the last ``max_history_messages`` exchanges to stay
        within the context window of small models.
        """
        messages: list[dict] = [
            {"role": "system", "content": self._build_system_prompt()}
        ]
        # Trim history
        trimmed = self._history[-self._config.max_history_messages:]
        for msg in trimmed:
            if msg.role in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content})
        return messages

    # ------------------------------------------------------------------
    # Core chat — blocking
    # ------------------------------------------------------------------

    def chat(self, user_text: str) -> str:
        """Send *user_text* to the LLM and return the assistant reply.

        Conversation history is maintained automatically.
        """
        if not user_text.strip():
            return ""

        self._history.append(VoiceMessage(role="user", content=user_text.strip()))
        self._is_running = True

        try:
            reply = self._call_llm()
        except Exception as exc:
            logger.error("VoiceAgent LLM call failed: %s", exc)
            reply = "Bağışlayın, xəta baş verdi. Zəhmət olmasa yenidən cəhd edin."
        finally:
            self._is_running = False

        self._history.append(VoiceMessage(role="assistant", content=reply))
        return reply

    # ------------------------------------------------------------------
    # Streaming chat
    # ------------------------------------------------------------------

    def chat_stream(self, user_text: str) -> Iterator[str]:
        """Stream tokens from the LLM as they arrive.

        Yields individual token strings.  The full reply is appended to
        history after the stream finishes.
        """
        if not user_text.strip():
            return

        self._history.append(VoiceMessage(role="user", content=user_text.strip()))
        self._is_running = True
        full_reply: list[str] = []

        try:
            from vibe_studio.providers.stream_events import StreamEvent
            messages = self._build_messages_payload()

            # Try Ollama chat endpoint (messages-based)
            if hasattr(self._provider, "stream_chat"):
                for event in self._provider.stream_chat(
                    messages=messages,
                    model=self._model,
                ):
                    if event.type == "token":
                        full_reply.append(event.token)
                        if self._stream_callback:
                            self._stream_callback(event.token)
                        yield event.token
                    elif event.type == "complete":
                        break
            else:
                # Fallback: use standard generate with full prompt
                prompt = self._messages_to_prompt(messages)
                for event in self._provider.stream_generate(
                    prompt=prompt,
                    model=self._model,
                    system_prompt=self._build_system_prompt(),
                ):
                    if hasattr(event, "token") and event.token:
                        full_reply.append(event.token)
                        if self._stream_callback:
                            self._stream_callback(event.token)
                        yield event.token
                    elif hasattr(event, "final_text") and event.final_text:
                        text = event.final_text
                        if not full_reply:
                            full_reply.append(text)
                            yield text
                        break

        except Exception as exc:
            logger.error("VoiceAgent stream failed: %s", exc)
            fallback = "Xəta baş verdi, yenidən cəhd edin."
            full_reply = [fallback]
            yield fallback
        finally:
            self._is_running = False
            reply = "".join(full_reply).strip()
            self._history.append(VoiceMessage(role="assistant", content=reply))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_llm(self) -> str:
        """Call the LLM and return the full reply text."""
        messages = self._build_messages_payload()

        # Prefer Ollama chat endpoint if available
        if hasattr(self._provider, "chat"):
            return self._provider.chat(
                messages=messages,
                model=self._model,
            )

        # Fallback: convert to single prompt string
        prompt = self._messages_to_prompt(messages)
        return self._provider.generate(
            prompt=prompt,
            model=self._model,
            system_prompt=self._build_system_prompt(),
        )

    @staticmethod
    def _messages_to_prompt(messages: list[dict]) -> str:
        """Convert chat messages to a plain-text prompt for generate()."""
        parts: list[str] = []
        for m in messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                parts.append(f"[System]\n{content}")
            elif role == "user":
                parts.append(f"[User]\n{content}")
            elif role == "assistant":
                parts.append(f"[Assistant]\n{content}")
        parts.append("[Assistant]")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def clear_history(self) -> None:
        """Reset conversation context."""
        self._history.clear()

    def stop(self) -> None:
        """Request the agent to stop (best-effort)."""
        self._is_running = False
        if hasattr(self._provider, "cancel"):
            try:
                self._provider.cancel()
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._is_running
