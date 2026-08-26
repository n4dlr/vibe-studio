"""Universal cross-platform path resolution for JARVIS.

Handles directories for:
- Application installation root (frozen vs development)
- User data directory (memory DB, persistent state, caches)
- Configuration directories (system vs user config)
- Log directory (structured production logs)
- Local models directory (GGUF weights & Modelfiles)
- Bundled runtime tools (Ollama, ffmpeg, tesseract, etc.)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


class JarvisPaths:
    """Path resolver adhering to Linux XDG Base Directory specification and Windows AppData."""

    @staticmethod
    def is_frozen() -> bool:
        """Check if running inside a packaged binary (PyInstaller / Nuitka / etc.)."""
        return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

    @classmethod
    def get_app_install_dir(cls) -> Path:
        """Return root installation folder of the application."""
        if cls.is_frozen():
            # In PyInstaller onefile, sys._MEIPASS is temporary unpack dir, sys.executable is the binary
            return Path(sys.executable).resolve().parent
        # In development: repo root
        return Path(__file__).resolve().parents[2]

    @classmethod
    def get_bundle_resource_dir(cls) -> Path:
        """Return the directory containing bundled assets/resources."""
        if cls.is_frozen():
            return Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
        return Path(__file__).resolve().parents[2]

    @staticmethod
    def get_user_data_dir() -> Path:
        """Return user data directory for persistent data, memory DB, plugins."""
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            path = Path(base) / "JARVIS" / "data"
        elif sys.platform == "darwin":
            path = Path.home() / "Library" / "Application Support" / "JARVIS"
        else:
            # Linux XDG_DATA_HOME default: ~/.local/share/jarvis
            base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
            path = Path(base) / "jarvis"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_user_config_dir() -> Path:
        """Return user configuration directory."""
        if sys.platform == "win32":
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            path = Path(base) / "JARVIS" / "config"
        elif sys.platform == "darwin":
            path = Path.home() / "Library" / "Preferences" / "JARVIS"
        else:
            # Linux XDG_CONFIG_HOME default: ~/.config/jarvis
            base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
            path = Path(base) / "jarvis"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_system_config_dir() -> Path:
        """Return system-wide configuration directory."""
        if sys.platform == "win32":
            base = os.environ.get("ProgramData") or r"C:\ProgramData"
            return Path(base) / "JARVIS"
        return Path("/etc/jarvis")

    @staticmethod
    def get_log_dir() -> Path:
        """Return directory for production logs."""
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            path = Path(base) / "JARVIS" / "logs"
        elif sys.platform == "darwin":
            path = Path.home() / "Library" / "Logs" / "JARVIS"
        else:
            # Linux XDG_STATE_HOME default: ~/.local/state/jarvis/logs
            base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
            path = Path(base) / "jarvis" / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_cache_dir() -> Path:
        """Return temporary cache directory."""
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            path = Path(base) / "JARVIS" / "cache"
        elif sys.platform == "darwin":
            path = Path.home() / "Library" / "Caches" / "JARVIS"
        else:
            base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
            path = Path(base) / "jarvis"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def get_models_dir(cls) -> Path:
        """Return model storage directory (user-level first, then bundled app models)."""
        # User downloaded or customized models:
        user_models = cls.get_user_data_dir() / "models"
        user_models.mkdir(parents=True, exist_ok=True)

        # Bundled models inside app directory:
        bundle_models = cls.get_bundle_resource_dir() / "models"
        if bundle_models.exists():
            return bundle_models
        return user_models

    @classmethod
    def get_bundled_ollama_path(cls) -> Path | None:
        """Look for bundled Ollama runtime executable."""
        resource_dir = cls.get_bundle_resource_dir()
        if sys.platform == "win32":
            candidates = [
                resource_dir / "ollama" / "ollama.exe",
                resource_dir / "ollama.exe",
                cls.get_app_install_dir() / "ollama" / "ollama.exe",
            ]
        else:
            candidates = [
                resource_dir / "ollama" / "bin" / "ollama",
                resource_dir / "bin" / "ollama",
                resource_dir / "ollama",
                cls.get_app_install_dir() / "ollama" / "ollama",
            ]
        for c in candidates:
            if c.is_file() and os.access(c, os.X_OK if sys.platform != "win32" else os.R_OK):
                return c
        return None
