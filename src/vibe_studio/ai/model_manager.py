from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from vibe_studio.core.settings import AppSettings


class ModelManager:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.models: list[dict] = []
        self.refresh_models()

    def detect_ollama(self) -> tuple[bool, list[str]]:
        base_url = self._ollama_url()
        try:
            request = Request(f"{base_url}/api/tags", headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [item.get("name", "") for item in payload.get("models", []) if item.get("name")]
            self.models = [{"provider": "ollama", "model": model} for model in models]
            if models and not self.settings.default_model:
                self.settings.default_model = models[0]
            return True, models
        except Exception:
            self.models = []
            if not self.settings.default_model:
                self.settings.default_model = ""
            return False, ["Ollama unavailable"]

    def _ollama_url(self) -> str:
        for provider in self.settings.providers:
            if provider.kind == "ollama":
                return provider.base_url.rstrip("/")
        return "http://127.0.0.1:11434"

    def refresh_models(self) -> list[dict]:
        self.models = []
        if self.settings.default_provider == "ollama":
            ok, _ = self.detect_ollama()
            if ok:
                return self.models

        env_key = os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY")
        if env_key and self.settings.default_provider != "ollama":
            self.models = [{"provider": "openai-compatible", "model": self.settings.default_model or "gpt-4o-mini"}]
        return self.models

    def list_models(self) -> list[dict]:
        return self.models if self.models else self.refresh_models()

    def set_default(self, provider: str, model: str) -> None:
        self.settings.default_provider = provider
        self.settings.default_model = model
        self.refresh_models()
