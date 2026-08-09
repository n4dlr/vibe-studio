"""ChatService — coordinates the autonomous agent, conversation history, streaming, and undo."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from vibe_studio.agents.coding_agent import AgentState, AutonomousAgent, AutonomyMode
from vibe_studio.ai.model_manager import ModelManager
from vibe_studio.providers.ollama_provider import OllamaProvider
from vibe_studio.providers.openai_compatible_provider import OpenAICompatibleProvider


class ChatService:
    """
    Top-level chat coordinator.

    Responsibilities:
      - Maintain multi-turn conversation history (up to chat_history_limit turns)
      - Wire streaming callbacks from provider → UI
      - Manage one AutonomousAgent per task (cancelled on demand)
      - Expose revert_last_change() for UI undo button
    """

    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
        self._agent: AutonomousAgent | None = None
        self._provider: OllamaProvider | OpenAICompatibleProvider | None = None
        self.activity_callbacks: list[Callable[[str, dict[str, Any]], None]] = []
        # Conversation history as list of {"role": ..., "content": ...} dicts
        self._conversation: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def add_activity_callback(self, cb: Callable[[str, dict[str, Any]], None]) -> None:
        if cb not in self.activity_callbacks:
            self.activity_callbacks.append(cb)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        for cb in self.activity_callbacks:
            try:
                cb(event_type, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Provider resolution
    # ------------------------------------------------------------------

    def _get_provider(self) -> OllamaProvider | OpenAICompatibleProvider | None:
        # Allow test/CI environments to force offline (deterministic) mode
        if os.getenv("VIBE_STUDIO_OFFLINE") == "1":
            return None

        s = self.model_manager.settings
        if s.local_only or s.default_provider == "ollama":
            url = "http://127.0.0.1:11434"
            for p in s.providers:
                if p.kind == "ollama":
                    url = p.base_url
            # Fast connection check — 2s timeout to avoid hanging tests
            import socket
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 11434
            try:
                with socket.create_connection((host, port), timeout=2):
                    pass
                provider = OllamaProvider(base_url=url, timeout=120)
                if provider.test_connection():
                    return provider
            except (OSError, Exception):
                pass
            if s.local_only:
                return None  # never fall through to remote

        # OpenAI-compatible
        api_key = ""
        api_url = "https://api.openai.com/v1"
        for p in s.providers:
            if p.kind == "openai-compatible":
                api_key = p.api_key or ""
                api_url = p.base_url or api_url
        env_key = os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY") or ""
        key = api_key or env_key
        if key:
            return OpenAICompatibleProvider(base_url=api_url, api_key=key, timeout=120)

        return None

    # ------------------------------------------------------------------
    # Main chat entry point
    # ------------------------------------------------------------------

    def chat(self, prompt: str, autonomy_mode: AutonomyMode = AutonomyMode.AUTO) -> str:
        import uuid
        from vibe_studio.agents.tool_call_parser import parse_tool_calls, strip_tool_calls
        from vibe_studio.core.cancellation import CancellationToken

        project_root = (
            Path(self.model_manager.settings.project_path)
            if self.model_manager.settings.project_path
            else Path.cwd()
        )

        provider = self._get_provider()
        self._provider = provider
        model = self.model_manager.settings.default_model or "llama3.1"
        token = CancellationToken()
        exec_id = str(uuid.uuid4())

        # Streaming callback forwards chunks to UI as activity events
        def _stream_chunk(chunk: str) -> None:
            self._emit("stream_chunk", {"chunk": chunk, "execution_id": exec_id})

        self._agent = AutonomousAgent(
            project_root=project_root,
            provider=provider,
            model=model,
            autonomy_mode=autonomy_mode,
            stream_callback=_stream_chunk,
            cancellation_token=token,
            execution_id=exec_id,
        )

        # Wire agent events to UI
        self._agent.add_event_callback(self._emit)

        # Append to conversation history
        self._conversation.append({"role": "user", "content": prompt})
        limit = self.model_manager.settings.chat_history_limit
        if len(self._conversation) > limit * 2:
            self._conversation = self._conversation[-(limit * 2):]

        result = self._agent.run(prompt, conversation_history=self._conversation)

        raw_summary = result.summary
        # Clean any raw tool call JSON that might linger in summary
        calls = parse_tool_calls(raw_summary)
        clean_summary = strip_tool_calls(raw_summary, calls) if calls else raw_summary

        if result.files_changed:
            clean_summary += f"\n\nModified files: {', '.join(result.files_changed)}"

        # Record assistant turn
        self._conversation.append({"role": "assistant", "content": clean_summary})

        return clean_summary

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def cancel_current_agent(self) -> None:
        if self._agent:
            self._agent.cancel()
        if self._provider:
            self._provider.cancel()

    def revert_last_change(self) -> bool:
        if self._agent and self._agent.tool_registry.patch_tools.history:
            return self._agent.tool_registry.patch_tools.undo_last_change()
        return False

    def clear_history(self) -> None:
        self._conversation.clear()
