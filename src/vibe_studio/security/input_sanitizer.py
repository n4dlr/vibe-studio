"""Input Sanitizer for Vibe Studio.

Sanitizes tool arguments and command lines to prevent command injection, privilege escalation, and path traversal.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict


class InputSanitizer:
    """Sanitizes inputs and detects malicious/dangerous command patterns."""

    DANGEROUS_PATTERNS = [
        re.compile(r"\brm\s+-rf\s+/", re.IGNORECASE),
        re.compile(r"\bdel\s+/f\s+[a-z]:\\", re.IGNORECASE),
        re.compile(r"\bsudo\b", re.IGNORECASE),
        re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
        re.compile(r"\bchmod\s+777\b", re.IGNORECASE),
    ]

    @classmethod
    def sanitize_command(cls, command: str) -> str:
        """Sanitize a shell command or raise ValueError if dangerous pattern detected."""
        cmd_str = command.strip()
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.search(cmd_str):
                raise ValueError(f"Dangerous command pattern detected: '{cmd_str}'")
        return cmd_str

    @classmethod
    def sanitize_path(cls, path_str: str, workspace_root: Path) -> Path:
        """Sanitize path string and ensure it does not break workspace sandbox."""
        resolved_root = workspace_root.resolve()
        target_path = (resolved_root / path_str).resolve() if not Path(path_str).is_absolute() else Path(path_str).resolve()

        if not str(target_path).startswith(str(resolved_root)):
            raise ValueError(f"Path traversal blocked: '{path_str}' escapes workspace root")
        return target_path

    @classmethod
    def sanitize_args(cls, tool_name: str, args: Dict[str, Any], workspace_root: Path) -> Dict[str, Any]:
        """Sanitize tool arguments based on tool parameter schemas."""
        sanitized = dict(args)
        if "path" in sanitized and isinstance(sanitized["path"], str):
            cls.sanitize_path(sanitized["path"], workspace_root)
        if "command" in sanitized and isinstance(sanitized["command"], str):
            sanitized["command"] = cls.sanitize_command(sanitized["command"])
        return sanitized
