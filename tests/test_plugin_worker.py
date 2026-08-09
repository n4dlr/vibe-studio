"""Tests for PluginWorker subprocess sandbox."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.plugin.plugin_worker import PluginWorker


class TestPluginWorker:
    def _make_plugin(self, tmp_path: Path, code: str) -> Path:
        p = tmp_path / "test_plugin.py"
        p.write_text(code)
        return p

    def test_is_available(self):
        assert PluginWorker.is_available() is True

    def test_call_simple_tool(self, tmp_path):
        plugin = self._make_plugin(tmp_path, "def greet(name='world'):\n    return f'Hello, {name}!'\n")
        result = PluginWorker.call(
            plugin_path=plugin,
            tool_name="greet",
            kwargs={"name": "Test"},
        )
        assert result == "Hello, Test!"

    def test_call_returns_dict(self, tmp_path):
        plugin = self._make_plugin(tmp_path, "def info():\n    return {'status': 'ok', 'count': 3}\n")
        result = PluginWorker.call(plugin_path=plugin, tool_name="info", kwargs={})
        assert isinstance(result, dict)
        assert result["status"] == "ok"

    def test_call_nonexistent_tool_raises(self, tmp_path):
        plugin = self._make_plugin(tmp_path, "def foo(): pass\n")
        with pytest.raises(RuntimeError, match="not found"):
            PluginWorker.call(plugin_path=plugin, tool_name="nonexistent", kwargs={})

    def test_call_tool_exception_raises(self, tmp_path):
        plugin = self._make_plugin(tmp_path, "def bad(): raise ValueError('intentional')\n")
        with pytest.raises(RuntimeError, match="intentional"):
            PluginWorker.call(plugin_path=plugin, tool_name="bad", kwargs={})

    def test_call_nonexistent_plugin_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            PluginWorker.call(
                plugin_path=tmp_path / "no_such_plugin.py",
                tool_name="foo",
                kwargs={},
            )

    def test_path_escape_blocked(self, tmp_path):
        plugin = self._make_plugin(tmp_path, "def read(path): return path\n")
        with pytest.raises(RuntimeError, match="Path escape"):
            PluginWorker.call(
                plugin_path=plugin,
                tool_name="read",
                kwargs={"path": "../secret.txt"},
                workspace=str(tmp_path),
            )

    def test_timeout_raises(self, tmp_path):
        plugin = self._make_plugin(tmp_path, "import time\ndef slow(): time.sleep(60)\n")
        with pytest.raises(TimeoutError):
            PluginWorker.call(plugin_path=plugin, tool_name="slow", kwargs={}, timeout=1)
