"""Plugin Worker — subprocess-based sandbox for HIGH-risk plugin tools.

Sütun 4 (Plugin Sandbox):
  Protocol: JSON-RPC over stdin/stdout.
    Request : {"tool": "<name>", "kwargs": {...}, "workspace": "<path>"}
    Response: {"result": <any>, "error": null}  |  {"result": null, "error": "<msg>"}

  The worker process:
    1. Accepts exactly one JSON-encoded request on stdin.
    2. Loads the plugin file via importlib.
    3. Executes the requested tool function with the provided kwargs.
    4. Validates that any path argument stays within the declared workspace root.
    5. Writes exactly one JSON-encoded response to stdout, then exits.

  The host process:
    - Spawns the worker via subprocess.run() with a configurable timeout (default 30s).
    - Decodes the response and raises RuntimeError on worker-reported errors.
    - Raises TimeoutError if the worker exceeds the timeout.

Usage (from PluginManager)::

    result = PluginWorker.call(
        plugin_path="/path/to/plugin.py",
        tool_name="my_tool",
        kwargs={"path": "src/foo.py", "content": "..."},
        workspace="/my/project",
        timeout=30,
    )
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker entry point (called when module run as __main__)
# ---------------------------------------------------------------------------

def _worker_main() -> None:
    """Entry point executed inside the sandboxed subprocess."""
    import importlib.util
    import os

    raw = sys.stdin.read()
    try:
        req = json.loads(raw)
    except Exception as exc:
        sys.stdout.write(json.dumps({"result": None, "error": f"Bad JSON request: {exc}"}))
        sys.exit(1)

    plugin_path = req.get("plugin_path", "")
    tool_name = req.get("tool", "")
    kwargs: dict = req.get("kwargs", {})
    workspace = req.get("workspace", "")

    # Path boundary check
    if workspace:
        ws = Path(workspace).resolve()
        for v in kwargs.values():
            if isinstance(v, str):
                try:
                    candidate = (ws / v).resolve()
                    if not str(candidate).startswith(str(ws)):
                        sys.stdout.write(json.dumps(
                            {"result": None, "error": f"Path escape blocked: {v}"}
                        ))
                        sys.exit(1)
                except Exception:
                    pass

    # Load plugin
    try:
        spec = importlib.util.spec_from_file_location("_plugin_sandbox", plugin_path)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load plugin spec from {plugin_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        sys.stdout.write(json.dumps({"result": None, "error": f"Plugin load failed: {exc}"}))
        sys.exit(1)

    # Find tool
    func = getattr(mod, tool_name, None)
    if func is None:
        # Also check @vibe_plugin registry on the module
        registry = getattr(mod, "_VIBE_PLUGIN_REGISTRY", {})
        entry = registry.get(tool_name)
        func = entry.func if entry and hasattr(entry, "func") else None

    if func is None or not callable(func):
        sys.stdout.write(json.dumps({"result": None, "error": f"Tool '{tool_name}' not found in plugin"}))
        sys.exit(1)

    # Execute
    try:
        result = func(**kwargs)
        # Ensure result is JSON-serialisable
        if not isinstance(result, (str, int, float, bool, list, dict, type(None))):
            result = str(result)
        sys.stdout.write(json.dumps({"result": result, "error": None}))
    except Exception as exc:
        sys.stdout.write(json.dumps({"result": None, "error": str(exc)}))
        sys.exit(1)


# ---------------------------------------------------------------------------
# PluginWorker host-side API
# ---------------------------------------------------------------------------

class PluginWorker:
    """Spawns an isolated subprocess to execute a single plugin tool call."""

    @staticmethod
    def call(
        plugin_path: str | Path,
        tool_name: str,
        kwargs: dict,
        workspace: str | Path = "",
        timeout: int = 30,
    ) -> object:
        """Execute *tool_name* from *plugin_path* in an isolated subprocess.

        Args:
            plugin_path: Absolute path to the plugin .py file.
            tool_name  : Name of the function to call within the plugin.
            kwargs     : Keyword arguments forwarded to the function.
            workspace  : Workspace root used for path-boundary enforcement.
            timeout    : Maximum seconds to wait for the subprocess.

        Returns:
            The JSON-deserialized return value of the tool function.

        Raises:
            RuntimeError : Worker reported an error.
            TimeoutError : Worker exceeded the timeout.
        """
        request = json.dumps({
            "plugin_path": str(plugin_path),
            "tool": tool_name,
            "kwargs": kwargs,
            "workspace": str(workspace),
        })

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "vibe_studio.plugin.plugin_worker"],
                input=request,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"Plugin worker timed out after {timeout}s for tool '{tool_name}'"
            ) from exc

        if not proc.stdout.strip():
            stderr_hint = proc.stderr.strip()[:300] if proc.stderr else "no output"
            raise RuntimeError(
                f"Plugin worker produced no output for '{tool_name}'. stderr: {stderr_hint}"
            )

        try:
            response = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Plugin worker returned invalid JSON: {proc.stdout[:200]}"
            ) from exc

        if response.get("error"):
            raise RuntimeError(f"Plugin '{tool_name}' error: {response['error']}")

        return response.get("result")

    @staticmethod
    def is_available() -> bool:
        """Return True — subprocess sandbox is always available (Python stdlib only)."""
        return True


# ---------------------------------------------------------------------------
# Entry point guard
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _worker_main()
