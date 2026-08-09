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
        """Register a persistent callback (e.g. tests). Accumulates."""
        if cb not in self.activity_callbacks:
            self.activity_callbacks.append(cb)

    def set_activity_callback(self, cb: Callable[[str, dict[str, Any]], None]) -> None:
        """Replace the primary UI callback slot (one per active task)."""
        # Remove any previously registered primary UI callbacks (those that were
        # registered via set_activity_callback in prior runs) while keeping
        # persistent test callbacks.
        self._ui_callback = cb
        # Keep all callbacks that were added with add_activity_callback (tests etc.)
        # and add the new UI callback at position 0.
        self.activity_callbacks = [
            c for c in self.activity_callbacks if getattr(c, "_is_ui_cb", False) is False
        ]
        cb._is_ui_cb = True  # type: ignore[attr-defined]
        self.activity_callbacks.insert(0, cb)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        for cb in list(self.activity_callbacks):  # copy — safe against mutation
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
            num_ctx = 32768
            for p in s.providers:
                if p.kind == "ollama":
                    url = p.base_url
                    num_ctx = getattr(p, "num_ctx", 32768)
            # Fast connection check — 2s timeout to avoid hanging tests
            import socket
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 11434
            try:
                with socket.create_connection((host, port), timeout=2):
                    pass
                provider = OllamaProvider(base_url=url, timeout=120, num_ctx=num_ctx)
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

        # ── Greeting fast-path ──────────────────────────────────────────────────
        # Detect before any expensive I/O (provider ping, context engine, etc.)
        _t = prompt.strip().lower()
        _words = _t.split()
        _is_greeting = (
            len(_t) < 40
            and not any(k in _t for k in ["create", "yarat", "yaz", "file", "fayl", "make", "code", "run", "delete", "sil"])
            and any(w in _words for w in ["salam", "hello", "hi", "hey", "necəsn", "necesen", "günaydın", "gunaydin"])
        )
        if _is_greeting:
            response = (
                "Salam! Mən Vibe Studio AI köməkçisiyəm. "
                "Layihənizdə sizə necə kömək edə bilərəm?\n"
                "Məsələn: fayl yaratmaq, kodu düzəltmək, testləri işə salmaq, refaktor etmək və s."
            )
            self._emit("completed", {"summary": response, "files_changed": []})
            self._conversation.append({"role": "user", "content": prompt})
            self._conversation.append({"role": "assistant", "content": response})
            return response
        # ───────────────────────────────────────────────────────────────────────

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

        s = self.model_manager.settings
        max_iter = getattr(s, "max_iterations", 30)

        self._agent = AutonomousAgent(
            project_root=project_root,
            provider=provider,
            model=model,
            autonomy_mode=autonomy_mode,
            max_iterations=max_iter,
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

        result = self._agent.run(prompt, conversation_history=self._clean_conversation())

        raw_summary = result.summary
        # Clean any raw tool call JSON that might linger in summary
        calls = parse_tool_calls(raw_summary)
        clean_summary = strip_tool_calls(raw_summary, calls) if calls else raw_summary

        if result.files_changed:
            clean_summary += f"\n\nModified files: {', '.join(result.files_changed)}"

        # Record assistant turn
        self._conversation.append({"role": "assistant", "content": clean_summary})
        self.save_history()

        return clean_summary

    # ------------------------------------------------------------------
    # Chat History Persistence
    # ------------------------------------------------------------------

    def _get_history_file(self, project_path: str | Path | None = None) -> Path:
        import json
        p = (
            Path(project_path)
            if project_path
            else Path(self.model_manager.settings.project_path)
            if self.model_manager.settings.project_path
            else Path.cwd()
        )
        history_dir = p / ".vibe_studio"
        history_dir.mkdir(parents=True, exist_ok=True)
        return history_dir / "chat_history.json"

    def save_history(self, project_path: str | Path | None = None) -> None:
        """Persist current conversation history to disk."""
        import json
        try:
            target = self._get_history_file(project_path)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(self._clean_conversation(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_history(self, project_path: str | Path | None = None) -> list[dict[str, str]]:
        """Load conversation history from disk."""
        import json
        try:
            target = self._get_history_file(project_path)
            if target.exists():
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._conversation = [
                            msg for msg in data if isinstance(msg, dict) and "role" in msg and "content" in msg
                        ]
                        return self._conversation
        except Exception:
            pass
        return self._conversation

    def clear_history(self, project_path: str | Path | None = None) -> None:
        """Clear conversation history in memory and delete disk file."""
        self._conversation.clear()
        try:
            target = self._get_history_file(project_path)
            if target.exists():
                target.unlink()
        except Exception:
            pass

    def export_history_markdown(self, export_path: str | Path) -> str:
        """Export history formatted as clean Markdown."""
        from datetime import datetime
        lines = [f"# Vibe Studio Chat History\n\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]
        for msg in self._clean_conversation():
            role = "You" if msg.get("role") == "user" else "Vibe AI"
            content = msg.get("content", "")
            lines.append(f"### {role}\n\n{content}\n\n---\n")
        out_text = "\n".join(lines)
        Path(export_path).write_text(out_text, encoding="utf-8")
        return out_text

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def cancel_current_agent(self) -> None:
        if self._agent:
            self._agent.cancel()
        if self._provider:
            self._provider.cancel()
        # Strip the last assistant turn if it was cancelled mid-flight
        # so the LLM never sees "previous task was cancelled" in history.
        if self._conversation and self._conversation[-1]["role"] == "user":
            self._conversation.pop()
        elif len(self._conversation) >= 2 and self._conversation[-1]["role"] == "assistant":
            last = self._conversation[-1]["content"].lower()
            if any(k in last for k in ["cancelled", "ləğv", "cancel", "interrupted"]):
                self._conversation.pop()
                if self._conversation and self._conversation[-1]["role"] == "user":
                    self._conversation.pop()
        self.save_history()

    def _clean_conversation(self) -> list[dict[str, str]]:
        """Return conversation history with cancelled/failed/error turns stripped."""
        _bad_markers = [
            "cancelled", "ləğv", "cancel", "interrupted",
            "execution cancelled", "task cancelled",
            "previous task was cancelled",
        ]
        cleaned: list[dict[str, str]] = []
        skip_next = False
        for i, msg in enumerate(self._conversation):
            if skip_next:
                skip_next = False
                continue
            if msg["role"] == "assistant":
                content_lower = msg["content"].lower()
                if any(m in content_lower for m in _bad_markers):
                    if cleaned and cleaned[-1]["role"] == "user":
                        cleaned.pop()
                    continue
            cleaned.append(msg)
        return cleaned

    def revert_last_change(self) -> bool:
        if self._agent and self._agent.tool_registry.patch_tools.history:
            return self._agent.tool_registry.patch_tools.undo_last_change()
        return False
