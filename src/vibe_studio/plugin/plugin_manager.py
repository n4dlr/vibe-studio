"""PluginManager — discovers, loads, and registers external plugins.

Plugin directories searched (in order):
  1. ~/.vibe_studio/plugins/
  2. <project_root>/.vibe_studio/plugins/

Each plugin file must either:
  a) Define functions decorated with @vibe_plugin (preferred), OR
  b) Expose a register_tools() -> dict[str, Callable] function (legacy)
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Callable

from vibe_studio.plugin.plugin_api import (
    PluginTool,
    _REGISTRY,
    clear_registry,
    get_plugin_schemas,
    get_registered_tools,
    list_plugins,
)
from vibe_studio.plugin.plugin_worker import PluginWorker
from vibe_studio.security.path_security import PathSecurity, PathSecurityError

logger = logging.getLogger(__name__)

RISK_APPROVAL_REQUIRED = {"MEDIUM", "HIGH", "CRITICAL"}


class PluginManager:
    """Discovers third-party extensions and registers tool functions with security sandboxing."""

    def __init__(
        self,
        global_plugins_dir: str | Path | None = None,
        project_root: str | Path | None = None,
    ):
        self.global_plugins_dir = Path(global_plugins_dir or Path.home() / ".vibe_studio" / "plugins")
        self.global_plugins_dir.mkdir(parents=True, exist_ok=True)
        self.project_root = Path(project_root) if project_root else None
        self.registered_tools: dict[str, Callable[..., Any]] = {}
        self._loaded_files: list[str] = []

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _plugin_dirs(self) -> list[Path]:
        dirs = [self.global_plugins_dir]
        if self.project_root:
            local_dir = self.project_root / ".vibe_studio" / "plugins"
            local_dir.mkdir(parents=True, exist_ok=True)
            dirs.append(local_dir)
        return dirs

    def discover_plugins(self) -> list[str]:
        """Return relative plugin file paths and names from all search directories."""
        found: list[str] = []
        for d in self._plugin_dirs():
            for p in sorted(d.glob("*.py")):
                if not p.name.startswith("_"):
                    found.append(p.name)
        return found

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_plugin(self, plugin_path: str | Path, workspace_root: Path | None = None) -> bool:
        """Load a single plugin file. Returns True on success."""
        path = Path(plugin_path)
        if not path.is_absolute() or not path.exists():
            for d in self._plugin_dirs():
                cand = d / plugin_path
                if cand.exists():
                    path = cand
                    break
        path = path.resolve()
        if not path.exists():
            return False

        spec = importlib.util.spec_from_file_location(path.stem, path)
        if not spec or not spec.loader:
            return False

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Plugin %s failed to load: %s", path.name, exc)
            return False

        # Collect @vibe_plugin decorated functions registered during module exec
        current_module_tools = {
            name: tool for name, tool in _REGISTRY.items()
            if getattr(tool.func, "__module__", "") == module.__name__
        }

        self._loaded_files.append(str(path))

        # Also support legacy register_tools() pattern
        if hasattr(module, "register_tools") and not current_module_tools:
            try:
                legacy = module.register_tools()
                if isinstance(legacy, dict):
                    for name, func in legacy.items():
                        sandboxed = self._sandbox(func, workspace_root)
                        self.registered_tools[name] = sandboxed
            except Exception as exc:
                logger.warning("Plugin %s register_tools() failed: %s", path.name, exc)

        for name, tool in current_module_tools.items():
            self.registered_tools[name] = self._sandbox_tool(tool, workspace_root)

        logger.info("Loaded plugin: %s (%d tools)", path.name, len(current_module_tools))
        return True

    def load_all_plugins(self, workspace_root: Path | None = None) -> int:
        """Load all discovered plugins. Returns count of successfully loaded files."""
        loaded = 0
        for plugin_path in self.discover_plugins():
            if self.load_plugin(plugin_path, workspace_root):
                loaded += 1
        return loaded

    # ------------------------------------------------------------------
    # Schema export (for ToolRegistry)
    # ------------------------------------------------------------------

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return tool schemas for all registered plugin tools."""
        return get_plugin_schemas()

    def list_loaded(self) -> list[PluginTool]:
        return list_plugins()

    def needs_approval(self, tool_name: str) -> bool:
        """Return True if this tool requires user approval before execution."""
        tool = _REGISTRY.get(tool_name)
        if tool:
            return tool.risk in RISK_APPROVAL_REQUIRED
        return False

    # ------------------------------------------------------------------
    # Security sandboxing
    # ------------------------------------------------------------------

    def _sandbox(self, func: Callable[..., Any], workspace_root: Path | None) -> Callable[..., Any]:
        def _safe(*args: Any, **kwargs: Any) -> Any:
            for v in list(args) + list(kwargs.values()):
                if isinstance(v, (str, Path)):
                    vs = str(v)
                    if "../" in vs or "..\\" in vs:
                        raise PathSecurityError("Plugin path traversal blocked.")
            return func(*args, **kwargs)
        return _safe

    def _sandbox_tool(self, tool: PluginTool, workspace_root: Path | None) -> Callable[..., Any]:
        """Wrap a PluginTool in a security sandbox.

        HIGH-risk tools are executed in an isolated subprocess (Sütun 4).
        LOW/MEDIUM tools use the fast in-process path-traversal guard.
        """
        if tool.risk in RISK_APPROVAL_REQUIRED and PluginWorker.is_available():
            plugin_path = self._loaded_files[-1] if self._loaded_files else ""

            def _subprocess_call(**kwargs: Any) -> Any:
                return PluginWorker.call(
                    plugin_path=plugin_path,
                    tool_name=tool.name,
                    kwargs=kwargs,
                    workspace=str(workspace_root) if workspace_root else "",
                )

            logger.debug(
                "Plugin '%s' (risk=%s) routed to subprocess sandbox",
                tool.name, tool.risk,
            )
            return _subprocess_call

        return self._sandbox(tool.func, workspace_root)
