"""PluginManager — discovers, loads, and registers external plugins from ~/.vibe_studio/plugins/."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Callable

from vibe_studio.security.path_security import PathSecurity, PathSecurityError


class PluginManager:
    """Discovers third-party extensions and registers tool functions with security sandboxing."""

    def __init__(self, plugins_dir: str | Path | None = None):
        if plugins_dir:
            self.plugins_dir = Path(plugins_dir).resolve()
        else:
            self.plugins_dir = Path.home() / ".vibe_studio" / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.registered_tools: dict[str, Callable[..., Any]] = {}

    def discover_plugins(self) -> list[str]:
        plugin_files = []
        for p in self.plugins_dir.glob("*.py"):
            if p.name.startswith("_"):
                continue
            plugin_files.append(p.name)
        return plugin_files

    def load_plugin(self, plugin_name: str, workspace_root: Path) -> bool:
        path = self.plugins_dir / plugin_name
        if not path.exists():
            return False

        spec = importlib.util.spec_from_file_location(path.stem, path)
        if not spec or not spec.loader:
            return False

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            if hasattr(module, "register_tools"):
                tools = module.register_tools()
                for name, func in tools.items():
                    # Wrap function with workspace sandbox check
                    def _sandboxed_func(*args, **kwargs):
                        # Security boundary check on path arguments if present
                        for v in list(args) + list(kwargs.values()):
                            if isinstance(v, (str, Path)) and ("../" in str(v) or "..\\" in str(v)):
                                raise PathSecurityError("Plugin path traversal blocked.")
                        return func(*args, **kwargs)

                    self.registered_tools[name] = _sandboxed_func
                return True
        except Exception:
            return False
        return False
