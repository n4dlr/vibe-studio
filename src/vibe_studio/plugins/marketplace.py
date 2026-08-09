"""Plugin Marketplace — Local in-repo discovery, search, installation, and management."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PluginMarketplace:
    """In-repo plugin marketplace manager."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.plugins_dir = self.workspace_root / ".vibe_studio" / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.community_dir = Path(__file__).parent / "community"
        self.registry_file = Path(__file__).parent / "registry.json"
        self._registry_cache: Dict[str, Dict[str, Any]] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if self.registry_file.exists():
            try:
                data = json.loads(self.registry_file.read_text(encoding="utf-8"))
                for item in data.get("plugins", []):
                    self._registry_cache[item["name"]] = item
            except Exception as e:
                logger.error("Failed to parse plugin registry.json: %s", e)

    def list_available(self) -> List[Dict[str, Any]]:
        """Returns list of all available plugins in the marketplace."""
        res = []
        for name, info in self._registry_cache.items():
            installed = (self.plugins_dir / f"{name}.py").exists() or (self.plugins_dir / name).exists()
            item = dict(info)
            item["installed"] = installed
            res.append(item)
        return res

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search available plugins by query string."""
        q = query.lower()
        available = self.list_available()
        return [
            p for p in available
            if q in p["name"].lower() or q in p.get("description", "").lower() or q in p.get("category", "").lower()
        ]

    def install(self, name: str) -> bool:
        """Installs a plugin from community directory to workspace .vibe_studio/plugins/."""
        if name not in self._registry_cache:
            logger.warning("Plugin '%s' not found in marketplace registry.", name)
            return False

        src_file = self.community_dir / f"{name}.py"
        src_dir = self.community_dir / name

        if src_file.exists():
            dest = self.plugins_dir / f"{name}.py"
            shutil.copy2(src_file, dest)
            logger.info("Installed plugin file '%s' -> %s", name, dest)
            return True
        elif src_dir.exists():
            dest = self.plugins_dir / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src_dir, dest)
            logger.info("Installed plugin directory '%s' -> %s", name, dest)
            return True
        else:
            logger.error("Source plugin content for '%s' does not exist in community dir.", name)
            return False

    def uninstall(self, name: str) -> bool:
        """Uninstalls a plugin from workspace .vibe_studio/plugins/."""
        file_dest = self.plugins_dir / f"{name}.py"
        dir_dest = self.plugins_dir / name

        removed = False
        if file_dest.exists():
            file_dest.unlink()
            removed = True
        if dir_dest.exists():
            shutil.rmtree(dir_dest)
            removed = True

        if removed:
            logger.info("Uninstalled plugin '%s'", name)
            return True
        return False
