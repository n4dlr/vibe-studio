from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from vibe_studio.agents.coding_agent import AgentState, AutonomousAgent, AutonomyMode
from vibe_studio.ai.model_manager import ModelManager
from vibe_studio.providers.ollama_provider import OllamaProvider
from vibe_studio.providers.openai_compatible_provider import OpenAICompatibleProvider


class ChatService:
    """Coordinates chat commands, agent execution tasks, streaming activity, and undo history."""

    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
        self._history: list[tuple[str, str, str | None]] = []
        self._agent: AutonomousAgent | None = None
        self.activity_callbacks: list[Callable[[str, dict[str, Any]], None]] = []

    def add_activity_callback(self, cb: Callable[[str, dict[str, Any]], None]) -> None:
        self.activity_callbacks.append(cb)

    def _emit_activity(self, event_type: str, data: dict[str, Any]) -> None:
        for cb in self.activity_callbacks:
            try:
                cb(event_type, data)
            except Exception:
                pass

    def send_system_message(self, message: str) -> str:
        return f"System: {message}"

    def revert_last_change(self) -> bool:
        if self._agent and self._agent.tool_registry.patch_tools.history:
            return self._agent.tool_registry.patch_tools.undo_last_change()
        if not self._history:
            return False
        file_path_str, previous_content, _ = self._history.pop()
        file_path = Path(file_path_str)
        if previous_content == "" and file_path.exists():
            file_path.unlink(missing_ok=True)
            return True
        if file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(previous_content, encoding="utf-8")
        return True

    def cancel_current_agent(self) -> None:
        if self._agent:
            self._agent.cancel()

    def _get_provider(self) -> Any:
        provider_kind = self.model_manager.settings.default_provider
        if provider_kind == "ollama":
            url = self.model_manager._get_ollama_url()
            p = OllamaProvider(base_url=url, timeout=10)
            if p.test_connection():
                return p
            return None
        env_key = os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY")
        if env_key:
            return OpenAICompatibleProvider(api_key=env_key, timeout=10)
        return None

    def chat(self, prompt: str, autonomy_mode: AutonomyMode = AutonomyMode.AUTO) -> str:
        project_root = Path(self.model_manager.settings.project_path) if self.model_manager.settings.project_path else Path.cwd()

        provider = self._get_provider()
        model = self.model_manager.settings.default_model or "llama3.1"

        self._agent = AutonomousAgent(
            project_root=project_root,
            provider=provider,
            model=model,
            autonomy_mode=autonomy_mode,
        )

        def _agent_event(event_type: str, data: dict[str, Any]):
            self._emit_activity(event_type, data)

        self._agent.add_event_callback(_agent_event)

        result = self._agent.run(prompt)

        if result.files_changed:
            files_str = ", ".join(result.files_changed)
            return f"{result.summary}\n\nModified files: {files_str}"

        return result.summary
