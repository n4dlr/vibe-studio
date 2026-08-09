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
        execution_id: str | None = None,
        cancellation_token: Any = None,
    ) -> CommandResult:
        work_dir = Path(cwd or Path.cwd()).resolve()
        if workspace_root:
            try:
                work_dir = PathSecurity.validate_workspace_path(work_dir, workspace_root)
            except PathSecurityError:
                work_dir = PathSecurity.normalize_path(workspace_root)

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

        if cancellation_token and cancellation_token.is_cancelled():
            return CommandResult(
                command=command,
                arguments=_safe_split(command),
                working_directory=str(work_dir),
                exit_code=-1,
                stdout="",
                stderr="Operation cancelled prior to command execution.",
                duration=0.0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                cancelled=True,
                risk_level=assessment.risk_level.value,
            )

        started = time.monotonic()
        try:
            from vibe_studio.core.resource_manager import default_resource_manager

            # Create Popen directly with process group on Posix so process tree can be killed cleanly
            start_new_session = os.name != "nt"
            proc = subprocess.Popen(
                command,
                cwd=str(work_dir),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=start_new_session,
            )

            if execution_id:
                default_resource_manager.register_subprocess(execution_id, proc)

            try:
                # Wait with timeout polling to support fast cancellation check
                poll_interval = 0.2
                elapsed = 0.0
                stdout_data, stderr_data = "", ""

                while True:
                    if cancellation_token and cancellation_token.is_cancelled():
                        proc.terminate()
                        try:
                            proc.wait(timeout=1.0)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        return CommandResult(
                            command=command,
                            arguments=_safe_split(command),
                            working_directory=str(work_dir),
                            exit_code=-1,
                            stdout="",
                            stderr="Command execution cancelled by user.",
                            duration=time.monotonic() - started,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            cancelled=True,
                            risk_level=assessment.risk_level.value,
                        )

                    try:
                        out, err = proc.communicate(timeout=poll_interval)
                        stdout_data, stderr_data = out, err
                        break
                    except subprocess.TimeoutExpired:
                        elapsed += poll_interval
                        if elapsed >= timeout:
                            proc.kill()
                            out, err = proc.communicate()
                            return CommandResult(
                                command=command,
                                arguments=_safe_split(command),
                                working_directory=str(work_dir),
                                exit_code=-1,
                                stdout=out or "",
                                stderr=f"{err or ''}\nCommand timed out after {timeout}s.",
                                duration=time.monotonic() - started,
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                cancelled=True,
                                risk_level=assessment.risk_level.value,
                            )

                elapsed = time.monotonic() - started
                return CommandResult(
                    command=command,
                    arguments=_safe_split(command),
                    working_directory=str(work_dir),
                    exit_code=proc.returncode,
                    stdout=stdout_data,
                    stderr=stderr_data,
                    duration=elapsed,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    risk_level=assessment.risk_level.value,
                )

            finally:
                pass

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
