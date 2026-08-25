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
    """Brokers permission requests for file access, commands, and tool executions."""

    def __init__(self, workspace_root: Path | str = "."):
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

    def authorize_tool_execution(
        self,
        tool_name: str,
        risk: Any,
        requires_permission: bool,
        args: dict[str, Any],
    ) -> PermissionDecision:
        """Authorize tool execution based on risk, permissions, and security policy."""
        # 1. File mutation tools: check file path boundary
        if "path" in args or "source" in args:
            p = args.get("path") or args.get("source") or ""
            if p and self.authorize_file_access(str(p)) == PermissionDecision.DENY:
                # If path escapes workspace (e.g. /etc/passwd or ../../), DENY
                from vibe_studio.security.path_security import PathSecurity
                if not PathSecurity.is_safe_workspace_path(str(p), self.workspace_root):
                    return PermissionDecision.DENY

        # 2. Command execution tools: check command safety
        if "command" in args:
            dec = self.authorize_command(str(args["command"]))
            if dec == PermissionDecision.DENY:
                return PermissionDecision.DENY

        return PermissionDecision.ALLOW
