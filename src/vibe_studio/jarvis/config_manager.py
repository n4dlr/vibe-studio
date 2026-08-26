"""Hierarchical configuration manager for JARVIS.

Resolution order (lowest to highest precedence):
1. Default built-in settings
2. System configuration (/etc/jarvis/config.json or %ProgramData%\\JARVIS\\config.json)
3. User configuration (~/.config/jarvis/config.json or %APPDATA%\\JARVIS\\config\\config.json)
4. Environment variables (JARVIS_*)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from packaging.common.paths import JarvisPaths

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {"api_key", "secret", "password", "token", "auth", "credential"}


@dataclass
class JarvisConfig:
    # LLM and Provider Configuration
    model: str = "jarvis-qwen"
    fallback_model: str = "qwen2.5-coder:1.5b"
    provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    auto_start_ollama: bool = True
    context_size: int = 4096
    temperature: float = 0.2

    # Voice & Speech
    voice_enabled: bool = True
    voice_gender: str = "male"
    voice_persona: str = "jarvis"
    stt_engine: str = "auto"  # auto, faster-whisper, google
    tts_engine: str = "edge-tts"  # edge-tts, pyttsx3, gtts

    # Security & Permissions
    strict_permissions: bool = True
    allow_shell_commands: bool = True
    require_confirmation_for_destructive: bool = True

    # Logging & Telemetry
    log_level: str = "INFO"
    enable_sentinel_watchdog: bool = True
    workspace_root: str = "."

    # Extra custom properties
    custom: dict[str, Any] = field(default_factory=dict)

    def as_safe_dict(self) -> dict[str, Any]:
        """Return config dictionary with sensitive secrets masked."""
        data = asdict(self)
        return self._mask_sensitive(data)

    @classmethod
    def _mask_sensitive(cls, obj: Any) -> Any:
        if isinstance(obj, dict):
            masked = {}
            for k, v in obj.items():
                if any(s in k.lower() for s in SENSITIVE_KEYS) and isinstance(v, str) and v:
                    masked[k] = v[:3] + "..." + v[-3:] if len(v) > 8 else "***"
                else:
                    masked[k] = cls._mask_sensitive(v)
            return masked
        elif isinstance(obj, list):
            return [cls._mask_sensitive(i) for i in obj]
        return obj


class ConfigManager:
    """Manages multi-tier configuration loading, merging, and saving."""

    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self._cached_config: JarvisConfig | None = None

    def load_config(self) -> JarvisConfig:
        """Load merged configuration from all tiers."""
        # 1. Defaults
        config_data = asdict(JarvisConfig(workspace_root=str(self.workspace_root)))

        # 2. System config
        sys_cfg_file = JarvisPaths.get_system_config_dir() / "config.json"
        if sys_cfg_file.is_file():
            try:
                with open(sys_cfg_file, "r", encoding="utf-8") as f:
                    sys_data = json.load(f)
                config_data.update(sys_data)
            except Exception as e:
                logger.warning("Could not read system config %s: %s", sys_cfg_file, e)

        # 3. User config
        user_cfg_file = JarvisPaths.get_user_config_dir() / "config.json"
        if user_cfg_file.is_file():
            try:
                with open(user_cfg_file, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                config_data.update(user_data)
            except Exception as e:
                logger.warning("Could not read user config %s: %s", user_cfg_file, e)

        # 4. Environment Variables
        env_map = {
            "JARVIS_MODEL": ("model", str),
            "JARVIS_FALLBACK_MODEL": ("fallback_model", str),
            "JARVIS_PROVIDER": ("provider", str),
            "JARVIS_OLLAMA_URL": ("ollama_url", str),
            "JARVIS_AUTO_START_OLLAMA": ("auto_start_ollama", lambda v: v.lower() in ("1", "true", "yes")),
            "JARVIS_CONTEXT_SIZE": ("context_size", int),
            "JARVIS_TEMPERATURE": ("temperature", float),
            "JARVIS_VOICE_GENDER": ("voice_gender", str),
            "JARVIS_VOICE_PERSONA": ("voice_persona", str),
            "JARVIS_LOG_LEVEL": ("log_level", str),
            "JARVIS_STRICT_PERMISSIONS": ("strict_permissions", lambda v: v.lower() in ("1", "true", "yes")),
        }

        for env_key, (cfg_key, converter) in env_map.items():
            if env_key in os.environ:
                try:
                    config_data[cfg_key] = converter(os.environ[env_key])
                except Exception as e:
                    logger.warning("Invalid env value for %s: %s", env_key, e)

        # Filter unknown keys to custom
        known_keys = set(JarvisConfig.__annotations__.keys())
        filtered: dict[str, Any] = {}
        custom: dict[str, Any] = config_data.get("custom", {})

        for k, v in config_data.items():
            if k in known_keys:
                filtered[k] = v
            else:
                custom[k] = v
        filtered["custom"] = custom

        self._cached_config = JarvisConfig(**filtered)
        return self._cached_config

    def save_user_config(self, config: JarvisConfig | dict[str, Any]) -> Path:
        """Save user configuration to user config path."""
        user_dir = JarvisPaths.get_user_config_dir()
        user_dir.mkdir(parents=True, exist_ok=True)
        target = user_dir / "config.json"

        data = asdict(config) if isinstance(config, JarvisConfig) else dict(config)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self._cached_config = None  # Invalidate cache
        return target
