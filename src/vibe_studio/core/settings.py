from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderConfig:
    name: str
    kind: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    api_key_env: str = ""
    timeout: int = 30
    temperature: float = 0.2
    max_tokens: int = 4096
    num_ctx: int = 32768
    streaming: bool = True
    enabled: bool = True


@dataclass
class AppSettings:
    local_only: bool = False
    project_path: str = ""
    default_provider: str = "ollama"
    default_model: str = ""
    providers: list[ProviderConfig] = field(default_factory=list)
    dark_theme: bool = True
    font_size: int = 12
    chat_history_limit: int = 50

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_only": self.local_only,
            "project_path": self.project_path,
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "dark_theme": self.dark_theme,
            "font_size": self.font_size,
            "chat_history_limit": self.chat_history_limit,
            "providers": [
                {
                    "name": p.name,
                    "kind": p.kind,
                    "base_url": p.base_url,
                    "api_key": p.api_key,
                    "model": p.model,
                    "api_key_env": p.api_key_env,
                    "timeout": p.timeout,
                    "temperature": p.temperature,
                    "max_tokens": p.max_tokens,
                    "num_ctx": p.num_ctx,
                    "streaming": p.streaming,
                    "enabled": p.enabled,
                }
                for p in self.providers
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        return cls(
            local_only=bool(data.get("local_only", False)),
            project_path=str(data.get("project_path", "")),
            default_provider=str(data.get("default_provider", "ollama")),
            default_model=str(data.get("default_model", "")),
            dark_theme=bool(data.get("dark_theme", True)),
            font_size=int(data.get("font_size", 12)),
            chat_history_limit=int(data.get("chat_history_limit", 50)),
            providers=[
                ProviderConfig(
                    name=str(p.get("name", "")),
                    kind=str(p.get("kind", "")),
                    base_url=str(p.get("base_url", "")),
                    api_key=str(p.get("api_key", "")),
                    model=str(p.get("model", "")),
                    api_key_env=str(p.get("api_key_env", "")),
                    timeout=int(p.get("timeout", 30)),
                    temperature=float(p.get("temperature", 0.2)),
                    max_tokens=int(p.get("max_tokens", 4096)),
                    num_ctx=int(p.get("num_ctx", 32768)),
                    streaming=bool(p.get("streaming", True)),
                    enabled=bool(p.get("enabled", True)),
                )
                for p in data.get("providers", [])
            ],
        )


class SettingsStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings(
                providers=[
                    ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="")
                ]
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return AppSettings(
                providers=[
                    ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="")
                ]
            )
        return AppSettings.from_dict(data)

    def save(self, settings: AppSettings) -> None:
        self.path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
