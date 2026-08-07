from __future__ import annotations

import json
from urllib.request import Request, urlopen

from vibe_studio.ai.model_manager import ModelManager


class ChatService:
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager

    def send_system_message(self, message: str) -> str:
        return f"System: {message}"

    def chat(self, prompt: str) -> str:
        provider = self.model_manager.settings.default_provider
        model = self.model_manager.settings.default_model or "llama3.1"
        if provider == "ollama":
            try:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2},
                }
                request = Request(
                    f"{self.model_manager._ollama_url()}/api/generate",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=30) as response:
                    result = json.loads(response.read().decode("utf-8"))
                return result.get("response", "No response from model.")
            except Exception as exc:  # pragma: no cover - network-specific fallback
                return f"Ollama unavailable: {exc}"
        return f"AI provider '{provider}' is configured but not implemented in this build."
