from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from vibe_studio.security.path_security import PathSecurity


class GitTools:
    """Implement Git inspection and safe branch/commit/diff operations."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)

    def _run_git(self, args: list[str]) -> str:
        cmd = ["git", "--no-pager"] + args
        res = subprocess.run(
            cmd,
            cwd=str(self.workspace_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0 and res.stderr:
            return f"Git error ({res.returncode}): {res.stderr.strip()}"
        return res.stdout.strip()

    def git_status(self) -> str:
        return self._run_git(["status", "--short"])

    def git_diff(self, file_path: str | None = None) -> str:
        args = ["diff"]
        if file_path:
            target = PathSecurity.validate_workspace_path(self.workspace_root / file_path, self.workspace_root)
            args.extend(["--", target.relative_to(self.workspace_root).as_posix()])
        return self._run_git(args)

    def git_log(self, limit: int = 10) -> str:
        return self._run_git(["log", f"-{limit}", "--oneline"])

    def git_branch(self) -> str:
        return self._run_git(["branch", "-a"])

    def git_checkout(self, branch_name: str) -> str:
        return self._run_git(["checkout", branch_name])

    def git_create_branch(self, branch_name: str) -> str:
        return self._run_git(["checkout", "-b", branch_name])

    def git_add(self, path: str = ".") -> str:
        return self._run_git(["add", path])

    def git_commit(self, message: str) -> str:
        """Stage all tracked changes and commit."""
        self._run_git(["add", "-u"])
        return self._run_git(["commit", "-m", message])

    def git_restore(self, path: str) -> str:
        return self._run_git(["restore", path])

    def git_show(self, object_spec: str = "HEAD") -> str:
        return self._run_git(["show", object_spec])
