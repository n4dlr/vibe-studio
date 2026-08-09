"""Pure Python Packager Plugin — venv & distribution package inspector.

Pillar 3 (Enterprise Official Plugins):
  Provides tools to inspect Python environment packages and build wheels cleanly.
"""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from vibe_studio.plugin.plugin_api import vibe_plugin


@vibe_plugin(
    name="inspect_python_environment",
    description="List installed Python packages and version information in workspace virtualenv.",
    risk="LOW",
)
def inspect_python_environment(workspace: str = ".") -> str:
    ws = Path(workspace).resolve()
    venv_py = ws / ".venv" / "bin" / "python"
    if not venv_py.exists():
        venv_py = ws / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        venv_py = Path(sys.executable)

    try:
        out = subprocess.check_output(
            [str(venv_py), "-m", "pip", "list", "--format=freeze"],
            text=True,
            errors="replace",
            timeout=15,
        )
        lines = out.strip().splitlines()
        return f"Python {sys.version.split()[0]} ({len(lines)} packages installed):\n" + "\n".join(lines[:20])
    except Exception as exc:
        return f"Failed to inspect Python environment: {exc}"
