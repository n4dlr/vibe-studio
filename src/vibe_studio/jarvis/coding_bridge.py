"""JarvisCodingBridge — Full Autonomous Software Engineering Engine for J.A.R.V.I.S.

Equips J.A.R.V.I.S to:
1. Create, edit, and inspect workspace and Desktop files (Python, JS, HTML, Rust, Go, C++, etc.)
2. Run shell commands, automated tests, and syntax validation
3. Smart path resolution (auto-resolves Desktop, Workspace, and cross-platform home paths)
4. Delegate deep multi-file development to CodingAgent and SuperAgent
5. Report accomplishments in natural Azerbaijani and English voice
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from vibe_studio.tools.tool_registry import default_tool_registry

logger = logging.getLogger(__name__)


class JarvisCodingBridge:
    """Autonomous software engineering executor for J.A.R.V.I.S."""

    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.home_dir = Path.home()
        self.desktop_dir = self.home_dir / "Desktop"
        self.registry = default_tool_registry

    def resolve_target_path(self, file_path: str) -> Path:
        """Robust path resolver: handles Desktop, Workspace, '~', and hallucinated paths."""
        p = file_path.strip().strip("\"'")
        if not p:
            return self.workspace_root

        # Expand home ~
        if p.startswith("~"):
            return Path(p).expanduser().resolve()

        # Handle macOS / hallucinated user paths like /Users/your_username/Desktop/...
        if p.startswith("/Users/") or p.startswith("/home/"):
            parts = Path(p).parts
            if "Desktop" in parts:
                idx = parts.index("Desktop")
                sub = Path(*parts[idx + 1:]) if len(parts) > idx + 1 else Path(".")
                return (self.desktop_dir / sub).resolve()
            return Path(p).resolve()

        # Handle "Desktop/file" or "desktop/file"
        if p.lower().startswith("desktop/"):
            sub = p.split("/", 1)[1]
            return (self.desktop_dir / sub).resolve()
        elif p.lower() == "desktop":
            return self.desktop_dir

        # Handle absolute path
        path_obj = Path(p)
        if path_obj.is_absolute():
            return path_obj.resolve()

        # Workspace relative
        return (self.workspace_root / p).resolve()

    def write_file(self, file_path: str, content: str) -> dict[str, Any]:
        """Create or overwrite a file in workspace or Desktop."""
        try:
            target = self.resolve_target_path(file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {
                "status": "success",
                "path": str(target),
                "filename": target.name,
                "bytes": len(content.encode("utf-8")),
                "message": f"Successfully created/updated {target.name} at {target.parent}",
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to write {file_path}: {e}"}

    def read_file(self, file_path: str) -> dict[str, Any]:
        """Read file content from workspace or Desktop."""
        try:
            target = self.resolve_target_path(file_path)
            if not target.exists():
                return {"status": "error", "message": f"File '{file_path}' does not exist."}
            content = target.read_text(encoding="utf-8", errors="replace")
            return {
                "status": "success",
                "path": str(target),
                "content": content,
                "lines": len(content.splitlines()),
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to read {file_path}: {e}"}

    def list_files(self, sub_dir: str = ".") -> dict[str, Any]:
        """List files in the workspace or directory."""
        try:
            target_dir = self.resolve_target_path(sub_dir)
            if not target_dir.exists():
                return {"status": "error", "message": f"Directory '{sub_dir}' not found."}

            entries = []
            for p in sorted(target_dir.iterdir()):
                if p.name.startswith((".", "__pycache__", "node_modules", ".venv")):
                    continue
                entries.append({
                    "name": p.name,
                    "is_dir": p.is_dir(),
                    "size": p.stat().st_size if p.is_file() else 0,
                })
            return {"status": "success", "entries": entries, "count": len(entries), "path": str(target_dir)}
        except Exception as e:
            return {"status": "error", "message": f"Could not list directory: {e}"}

    def run_tests(self) -> dict[str, Any]:
        """Run project tests via pytest."""
        import subprocess
        try:
            res = subprocess.run(
                [".venv/bin/pytest", "-q"],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=45,
            )
            output = res.stdout or res.stderr
            return {
                "status": "success" if res.returncode == 0 else "failure",
                "return_code": res.returncode,
                "output": output[-500:] if len(output) > 500 else output,
                "passed": res.returncode == 0,
            }
        except Exception as e:
            return {"status": "error", "message": f"Test runner error: {e}"}

    def execute_terminal_command(self, cmd: str) -> dict[str, Any]:
        """Execute a shell command inside workspace."""
        import subprocess
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "status": "success" if res.returncode == 0 else "error",
                "return_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "output": (res.stdout + res.stderr).strip(),
            }
        except Exception as e:
            return {"status": "error", "message": f"Command failed: {e}"}
