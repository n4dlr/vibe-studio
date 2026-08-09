"""Audit Logger for Vibe Studio.

Provides an anonymized audit log for security events, tool calls, file access, and user actions.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional


class AuditLogger:
    """Logs security audit records to disk."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or (Path.home() / ".vibe_studio" / "audit")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit.jsonl"

    def log_action(
        self,
        user_action: str,
        execution_id: str,
        tool_name: str = "",
        target_path: str = "",
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = {
            "timestamp": time.time(),
            "execution_id": execution_id,
            "action": user_action,
            "tool": tool_name,
            "path": self._anonymize_path(target_path),
            "status": status,
            "details": details or {},
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

    def _anonymize_path(self, path_str: str) -> str:
        if not path_str:
            return ""
        # Convert home dir to ~
        try:
            home = str(Path.home())
            if path_str.startswith(home):
                return path_str.replace(home, "~", 1)
        except Exception:
            pass
        return path_str


default_audit_logger = AuditLogger()
