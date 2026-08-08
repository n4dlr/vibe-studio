"""ShellDetector — cross-platform shell discovery and command formatting."""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


class ShellDetector:
    """Detects best shell executable and arguments for Windows and Linux."""

    @staticmethod
    def detect_shell() -> tuple[str, list[str]]:
        system = platform.system()
        if system == "Windows":
            pwsh = shutil.which("pwsh") or shutil.which("powershell")
            if pwsh:
                return "PowerShell", [pwsh, "-Command"]
            return "cmd", ["cmd.exe", "/C"]
        
        user_shell = os.environ.get("SHELL", "")
        preferred = ["zsh", "bash", "sh"]
        if user_shell:
            preferred.insert(0, user_shell)

        for sh in preferred:
            path = shutil.which(sh)
            if path:
                return Path(sh).name, [path, "-c"]

        return "sh", ["sh", "-c"]

    @staticmethod
    def format_command(command: str) -> list[str]:
        _, shell_cmd = ShellDetector.detect_shell()
        return shell_cmd + [command]
