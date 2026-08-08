from __future__ import annotations

import os
from vibe_studio.core.settings import AppSettings
from vibe_studio.providers.ollama_provider import OllamaProvider
from vibe_studio.providers.openai_compatible_provider import OpenAICompatibleProvider


class ModelManager:
    """Manages AI model discovery, selection, and provider connection checks."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.models: list[dict] = []
        self.refresh_models()

    def _get_ollama_url(self) -> str:
        for provider in self.settings.providers:
            if provider.kind == "ollama":
                return provider.base_url.rstrip("/")
        return "http://127.0.0.1:11434"

    def detect_ollama(self) -> tuple[bool, list[str]]:
        provider = OllamaProvider(base_url=self._get_ollama_url(), timeout=3)
        try:
            models = provider.list_models()
            model_names = [m.name for m in models]
            if model_names:
                return True, model_names
        except Exception:
            pass
        return False, []

    def refresh_models(self) -> list[dict]:
        self.models = []

        if self.settings.default_provider == "ollama":
            ok, ollama_models = self.detect_ollama()
            if ok and ollama_models:
                self.models = [{"provider": "ollama", "model": m} for m in ollama_models]
                if not self.settings.default_model or self.settings.default_model not in ollama_models:
                    self.settings.default_model = ollama_models[0]
                return self.models

        env_key = os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY")
        if env_key:
            provider = OpenAICompatibleProvider(api_key=env_key, timeout=5)
            remote_models = [m.name for m in provider.list_models()]
            if not remote_models:
                remote_models = ["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet"]
            self.models = [{"provider": "openai-compatible", "model": m} for m in remote_models]
            if not self.settings.default_model:
                self.settings.default_model = remote_models[0]
            return self.models

        # Offline / fallback mode
        self.models = [{"provider": "ollama", "model": "llama3.1 (Offline)"}]
        return self.models

    def list_models(self) -> list[dict]:
        return self.models if self.models else self.refresh_models()

    def set_default(self, provider: str, model: str) -> None:
        self.settings.default_provider = provider
        self.settings.default_model = model
        self.refresh_models()
