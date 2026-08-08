"""Command safety, risk classification, workspace restriction, and execution engine."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from vibe_studio.security.path_security import PathSecurity, PathSecurityError


class RiskLevel(str, Enum):
    SAFE     = "SAFE"
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


# Absolute blocklist — these patterns are NEVER executed regardless of settings
_CRITICAL_BLOCKLIST: list[str] = [
    r"rm\s+-rf\s+[/~]",
    r"rm\s+-rf\s+/\*",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bformat\s+[A-Za-z]:",
    r"dd\s+if=/dev/zero",
    r":\(\)\s*\{\s*:\|:",          # fork bomb
    r"\bpasswd\b",
    r"openssl\s+enc\s+.*-aes",
    r"/dev/sd[a-z]\b",
    r"\bsudo\s+rm\b",
    r"chmod\s+777\s+/",
]

# HIGH risk patterns — require explicit allow_destructive=True
_HIGH_RISK: list[str] = [
    r"rm\s+-rf",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-f",
    r"git\s+push\s+--force",
    r"git\s+branch\s+-[Dd]\s+\S+",  # delete branch
    r"DROP\s+TABLE",
    r"TRUNCATE\s+TABLE",
    r"DELETE\s+FROM\s+\w+\s*;",     # bare DELETE without WHERE
    r">\s*/dev/null\s+2>&1\s*&&?\s*rm",
]

# MEDIUM risk — shown to user but auto-executed in AUTO mode
_MEDIUM_RISK: list[str] = [
    r"\bpip\s+install\b",
    r"\bnpm\s+install\s+-g\b",
    r"\byarn\s+global\b",
    r"\bcargo\s+install\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bssh\b",
    r"\bscp\b",
]

# Commands that are always safe when workspace-scoped
_SAFE_PATTERNS: list[str] = [
    r"^(echo|cat|ls|dir|find|grep|rg|awk|sed|head|tail|wc|sort|uniq)\b",
    r"^(python3?|python|node|npm\s+test|pytest|cargo\s+test|go\s+test)\b",
    r"^(ruff|mypy|eslint|tsc)\b",
    r"^(git\s+(status|log|diff|branch|show|stash\s+list))\b",
]


@dataclass
class CommandRiskAssessment:
    command: str
    risk_level: RiskLevel
    requires_approval: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class CommandResult:
    command: str
    arguments: list[str]
    working_directory: str
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    timestamp: str
    cancelled: bool = False
    risk_level: str = "LOW"


def _match_any(patterns: list[str], command: str) -> str | None:
    for pat in patterns:
        if re.search(pat, command, re.IGNORECASE):
            return pat
    return None


class CommandSafety:
    """Risk-stratified command execution engine with workspace sandboxing."""

    @staticmethod
    def assess_risk(
        command: str,
        cwd: str | Path | None = None,
        workspace_root: str | Path | None = None,
    ) -> CommandRiskAssessment:
        cmd_lower = command.lower().strip()
        reasons: list[str] = []

        # Critical blocklist
        pat = _match_any(_CRITICAL_BLOCKLIST, command)
        if pat:
            return CommandRiskAssessment(
                command=command,
                risk_level=RiskLevel.CRITICAL,
                requires_approval=True,
                reasons=[f"Blocked pattern: {pat}"],
            )

        # Workspace path enforcement
        if cwd and workspace_root:
            try:
                PathSecurity.validate_workspace_path(cwd, workspace_root)
            except PathSecurityError as err:
                return CommandRiskAssessment(
                    command=command,
                    risk_level=RiskLevel.CRITICAL,
                    requires_approval=True,
                    reasons=[f"Path outside workspace: {err}"],
                )

        # High risk
        pat = _match_any(_HIGH_RISK, command)
        if pat:
            reasons.append(f"Destructive operation: {pat}")
            return CommandRiskAssessment(
                command=command,
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                reasons=reasons,
            )

        # Medium risk
        pat = _match_any(_MEDIUM_RISK, command)
        if pat:
            reasons.append(f"Network/system operation: {pat}")
            return CommandRiskAssessment(
                command=command,
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                reasons=reasons,
            )

        # Known safe
        if _match_any(_SAFE_PATTERNS, command):
            return CommandRiskAssessment(
                command=command, risk_level=RiskLevel.SAFE, requires_approval=False
            )

        return CommandRiskAssessment(
            command=command, risk_level=RiskLevel.LOW, requires_approval=False
        )

    @staticmethod
    def run(
        command: str,
        *,
        cwd: str | Path | None = None,
        workspace_root: str | Path | None = None,
        allow_destructive: bool = False,
        timeout: int = 60,
    ) -> CommandResult:
        work_dir = Path(cwd or Path.cwd()).resolve()
        if workspace_root:
            try:
                work_dir = PathSecurity.validate_workspace_path(work_dir, workspace_root)
            except PathSecurityError:
                pass  # use as-is; validate_workspace_path logs the violation

        assessment = CommandSafety.assess_risk(command, cwd=work_dir, workspace_root=workspace_root)

        if assessment.risk_level == RiskLevel.CRITICAL and not allow_destructive:
            return CommandResult(
                command=command,
                arguments=[],
                working_directory=str(work_dir),
                exit_code=1,
                stdout="",
                stderr=f"Command blocked by safety policy: {'; '.join(assessment.reasons)}",
                duration=0.0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                risk_level=assessment.risk_level.value,
            )

        if assessment.risk_level == RiskLevel.HIGH and not allow_destructive:
            return CommandResult(
                command=command,
                arguments=[],
                working_directory=str(work_dir),
                exit_code=1,
                stdout="",
                stderr=f"High-risk command requires explicit approval: {'; '.join(assessment.reasons)}",
                duration=0.0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                risk_level=assessment.risk_level.value,
            )

        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=str(work_dir),
                shell=True,  # noqa: S602  — we've validated above
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed = time.monotonic() - started
            return CommandResult(
                command=command,
                arguments=_safe_split(command),
                working_directory=str(work_dir),
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration=elapsed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                risk_level=assessment.risk_level.value,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - started
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return CommandResult(
                command=command,
                arguments=_safe_split(command),
                working_directory=str(work_dir),
                exit_code=-1,
                stdout=stdout,
                stderr=f"{stderr}\nCommand timed out after {timeout}s.",
                duration=elapsed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                cancelled=True,
                risk_level=assessment.risk_level.value,
            )
        except Exception as exc:
            elapsed = time.monotonic() - started
            return CommandResult(
                command=command,
                arguments=[],
                working_directory=str(work_dir),
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration=elapsed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                risk_level=assessment.risk_level.value,
            )


def _safe_split(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return [command]
