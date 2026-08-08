from __future__ import annotations

import os

from pathlib import Path
from typing import Any

from vibe_studio.core.command_safety import CommandResult, CommandSafety
from vibe_studio.security.path_security import PathSecurity


class TerminalTools:
    """Implement terminal, script, program, test, build, format, and linter tools."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)

    def execute_command(self, command: str, cwd: str = ".", timeout: int = 60, allow_destructive: bool = False) -> dict[str, Any]:
        work_dir = PathSecurity.validate_workspace_path(self.workspace_root / cwd, self.workspace_root)
        result: CommandResult = CommandSafety.run(
            command,
            cwd=work_dir,
            workspace_root=self.workspace_root,
            allow_destructive=allow_destructive,
            timeout=timeout,
        )
        return {
            "tool": "execute_command",
            "command": result.command,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": result.duration,
            "timestamp": result.timestamp,
            "cancelled": result.cancelled,
        }

    def _get_pytest_cmd(self) -> str:
        import shlex, sys
        root = self.workspace_root
        if (root / ".venv" / "bin" / "pytest").exists():
            return shlex.quote(str(root / ".venv" / "bin" / "pytest"))
        if (root / ".venv" / "Scripts" / "pytest.exe").exists():
            return shlex.quote(str(root / ".venv" / "Scripts" / "pytest.exe"))
        if (root / "venv" / "bin" / "pytest").exists():
            return shlex.quote(str(root / "venv" / "bin" / "pytest"))
        if (root / "venv" / "Scripts" / "pytest.exe").exists():
            return shlex.quote(str(root / "venv" / "Scripts" / "pytest.exe"))
        return f"{shlex.quote(sys.executable)} -m pytest"

    def execute_script(self, script_path: str, args: list[str] | None = None, timeout: int = 60) -> dict[str, Any]:
        import shlex, sys
        target = PathSecurity.validate_workspace_path(self.workspace_root / script_path, self.workspace_root)
        if not target.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")
        arg_str = " ".join(args) if args else ""
        if target.suffix == ".py":
            cmd = f"{shlex.quote(sys.executable)} {target.name} {arg_str}".strip()
        else:
            if os.name == "nt":
                cmd = f"cmd /C {target.name} {arg_str}".strip()
            else:
                cmd = f"bash {target.name} {arg_str}".strip()
        try:
            rel_parent = target.parent.relative_to(self.workspace_root).as_posix()
        except ValueError:
            rel_parent = "."
        return self.execute_command(cmd, cwd=rel_parent or ".", timeout=timeout)

    def run_program(self, program: str, args: list[str] | None = None, timeout: int = 60) -> dict[str, Any]:
        arg_str = " ".join(args) if args else ""
        cmd = f"{program} {arg_str}".strip()
        return self.execute_command(cmd, timeout=timeout)

    def run_tests(self, test_path: str | None = None, timeout: int = 120) -> dict[str, Any]:
        root = self.workspace_root
        cmd = ""
        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
            target_str = f" {test_path}" if test_path else ""
            cmd = f"{self._get_pytest_cmd()}{target_str}"
        elif (root / "package.json").exists():
            cmd = "npm test"
        elif (root / "Cargo.toml").exists():
            cmd = "cargo test"
        elif (root / "go.mod").exists():
            cmd = "go test ./..."
        else:
            cmd = f"{self._get_pytest_cmd()}"

        return self.execute_command(cmd, timeout=timeout)

    def run_linter(self, path: str = ".", timeout: int = 60) -> dict[str, Any]:
        root = self.workspace_root
        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
            cmd = f"ruff check {path}"
        elif (root / "package.json").exists():
            cmd = "npm run lint"
        else:
            cmd = f"ruff check {path}"

        try:
            return self.execute_command(cmd, timeout=timeout)
        except Exception as exc:
            return {"tool": "run_linter", "exit_code": 1, "stdout": "", "stderr": str(exc), "duration": 0.0}

    def run_formatter(self, path: str = ".", timeout: int = 60) -> dict[str, Any]:
        root = self.workspace_root
        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
            cmd = f"ruff format {path}"
        elif (root / "package.json").exists():
            cmd = "npx prettier --write ."
        else:
            cmd = f"ruff format {path}"

        try:
            return self.execute_command(cmd, timeout=timeout)
        except Exception as exc:
            return {"tool": "run_formatter", "exit_code": 1, "stdout": "", "stderr": str(exc), "duration": 0.0}

    def run_build(self, timeout: int = 180) -> dict[str, Any]:
        root = self.workspace_root
        if (root / "package.json").exists():
            cmd = "npm run build"
        elif (root / "Cargo.toml").exists():
            cmd = "cargo build"
        elif (root / "Makefile").exists():
            cmd = "make"
        elif (root / "setup.py").exists() or (root / "pyproject.toml").exists():
            cmd = "python -m build"
        else:
            cmd = "echo 'No standard build system detected'"

        return self.execute_command(cmd, timeout=timeout)

    def inspect_process(self, process_name: str) -> dict[str, Any]:
        if os.name == "nt":
            return self.execute_command(f'tasklist /FI "IMAGENAME eq {process_name}*"')
        return self.execute_command(f"ps aux | grep {process_name}")
