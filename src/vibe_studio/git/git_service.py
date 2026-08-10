from __future__ import annotations

import subprocess
from pathlib import Path


class GitService:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)

    def is_repo(self) -> bool:
        return (self.repo_root / ".git").exists()

    def status(self) -> str:
        if not self.is_repo():
            return "Not a git repository"
        return self._run("git status --short").stdout.strip()

    def diff(self) -> str:
        if not self.is_repo():
            return ""
        return self._run("git --no-pager diff -- .").stdout

    def log(self, limit: int = 5) -> str:
        if not self.is_repo():
            return ""
        return self._run(f"git --no-pager log -{limit} --oneline").stdout

    def branch_list(self) -> str:
        if not self.is_repo():
            return ""
        return self._run("git branch --list").stdout

    def _run(self, command: str) -> subprocess.CompletedProcess[str]:
        import shlex
        args = shlex.split(command) if isinstance(command, str) else command
        return subprocess.run(args, cwd=str(self.repo_root), shell=False, capture_output=True, text=True, check=False)
