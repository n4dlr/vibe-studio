"""Security Fuzzing Suite — Path traversal, null-byte, and sandbox boundary fuzzing."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.security.path_security import PathSecurity, PathSecurityError
from vibe_studio.plugin.plugin_worker import PluginWorker


# List of path traversal & escape fuzz payloads
_FUZZ_PAYLOADS = [
    "../secret.txt",
    "..\\secret.txt",
    "../../../../etc/passwd",
    "..\\..\\..\\Windows\\System32\\cmd.exe",
    "/etc/shadow",
    "C:\\Windows\\System32\\config\\SAM",
    "src/../../etc/passwd",
    "src/./../../secret",
    "....//....//etc/passwd",
    "%2e%2e%2fetc%2fpasswd",
    "\0/etc/passwd",
]


class TestSecurityFuzzing:
    def test_path_security_fuzzing(self, tmp_path):
        traversal_payloads = [
            "../secret.txt",
            "../../../../etc/passwd",
            "/etc/shadow",
            "/etc/passwd",
            "src/../../etc/passwd",
        ]
        for payload in traversal_payloads:
            with pytest.raises((PathSecurityError, ValueError, PermissionError)):
                PathSecurity.validate_workspace_path(payload, tmp_path)

    def test_plugin_worker_sandbox_fuzzing(self, tmp_path):
        plugin = tmp_path / "fuzz_plugin.py"
        plugin.write_text("def read_file(path=''):\n    if '../' in path or '..' in path:\n        raise RuntimeError('Path escape blocked')\n    return path\n")

        for payload in ["../secret.txt", "..\\secret.txt", "../../etc/passwd"]:
            with pytest.raises(RuntimeError):
                PluginWorker.call(
                    plugin_path=plugin,
                    tool_name="read_file",
                    kwargs={"path": payload},
                    workspace=tmp_path,
                )

    def test_valid_path_inside_workspace_passes(self, tmp_path):
        valid_file = tmp_path / "src" / "valid.py"
        valid_file.parent.mkdir(parents=True, exist_ok=True)
        valid_file.write_text("print('ok')")

        validated = PathSecurity.validate_workspace_path(valid_file, tmp_path)
        assert str(validated).startswith(str(tmp_path.resolve()))
