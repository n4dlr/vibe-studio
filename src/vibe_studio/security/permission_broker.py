"""Permission Broker for Vibe Studio.

Enforces workspace boundary rules, domain policies, and permission decisions.
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class PermissionDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY  = "DENY"
    ASK   = "ASK"


class PermissionBroker:
    """Brokers permission requests for file access, commands, and network connections."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.allowed_domains: List[str] = ["localhost", "127.0.0.1", "pypi.org", "registry.npmjs.org"]

    def authorize_file_access(self, target_path: str, mode: str = "read") -> PermissionDecision:
        """Check if target file path is within workspace boundaries."""
        try:
            target = (self.workspace_root / target_path).resolve()
            if str(target).startswith(str(self.workspace_root)):
                return PermissionDecision.ALLOW
            return PermissionDecision.DENY
        except Exception:
            return PermissionDecision.DENY

    def authorize_command(self, command: str, allow_destructive: bool = False) -> PermissionDecision:
        """Check command risk and return decision."""
        from vibe_studio.core.command_safety import CommandSafety, RiskLevel

        assessment = CommandSafety.assess_risk(command, workspace_root=self.workspace_root)
        if assessment.risk_level == RiskLevel.CRITICAL:
            return PermissionDecision.DENY
        if assessment.risk_level == RiskLevel.HIGH and not allow_destructive:
            return PermissionDecision.ASK
        return PermissionDecision.ALLOW
