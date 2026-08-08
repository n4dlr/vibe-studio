from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from vibe_studio.security.path_security import PathSecurity, PathSecurityError


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


BLOCKLIST = {
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf /tmp",
    "mkfs",
    "shutdown",
    "reboot",
    "sudo",
    "format",
    "chown -R",
    "/dev/sd",
    "dd if=/dev/zero",
    "passwd",
    "openssl enc -aes",
    "forkbomb",
    ":(){ :|:& };:",
}


@dataclass
class CommandRiskAssessment:
    command: str
    risk_level: RiskLevel
    requires_approval: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class CommandRequest:
    command: str
    arguments: list[str] | None = None
    working_directory: str | None = None
    allow_destructive: bool = False
    timeout: int = 60


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


class CommandSafety:
    """Command safety, risk classification, workspace restriction, and execution engine."""

    @staticmethod
    def assess_risk(command: str, cwd: str | Path | None = None, workspace_root: str | Path | None = None) -> CommandRiskAssessment:
        command_lower = command.lower().strip()
        reasons: list[str] = []
        risk = RiskLevel.LOW

        # Critical blocklist check
        for forbidden in BLOCKLIST:
            if forbidden in command_lower:
                return CommandRiskAssessment(
                    command=command,
                    risk_level=RiskLevel.CRITICAL,
                    requires_approval=True,
                    reasons=[f"Forbidden command pattern detected: '{forbidden}'"],
                )

        # High risk patterns
        if any(token in command_lower for token in ["rm -rf", "git reset --hard", "git clean -fd", "drop table", "truncate"]):
            risk = RiskLevel.HIGH
            reasons.append("Destructive filesystem or git operation")
        elif any(token in command_lower for token in ["pip install", "npm install -g", "yarn global", "cargo install", "chmod +x"]):
            risk = RiskLevel.MEDIUM
            reasons.append("Package installation or privilege modification")

        # Workspace path restriction check
        if cwd and workspace_root:
            try:
                PathSecurity.validate_workspace_path(cwd, workspace_root)
            except PathSecurityError as err:
                risk = RiskLevel.CRITICAL
                reasons.append(str(err))

        requires_approval = risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        return CommandRiskAssessment(
            command=command,
            risk_level=risk,
            requires_approval=requires_approval,
            reasons=reasons,
        )

    @staticmethod
    def validate(request: CommandRequest, workspace_root: str | Path | None = None) -> None:
        assessment = CommandSafety.assess_risk(request.command, cwd=request.working_directory, workspace_root=workspace_root)
        if assessment.risk_level == RiskLevel.CRITICAL and not request.allow_destructive:
            raise ValueError(f"Command blocked by safety policy ({', '.join(assessment.reasons)}): {request.command}")
        if assessment.risk_level == RiskLevel.HIGH and not request.allow_destructive:
            raise ValueError(f"High-risk command requires explicit approval ({', '.join(assessment.reasons)}): {request.command}")

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
            work_dir = PathSecurity.validate_workspace_path(work_dir, workspace_root)

        request = CommandRequest(
            command=command,
            arguments=shlex.split(command, posix=os.name != "nt"),
            working_directory=str(work_dir),
            allow_destructive=allow_destructive,
            timeout=timeout,
        )
        CommandSafety.validate(request, workspace_root=workspace_root)

        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=str(work_dir),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed = time.monotonic() - started
            return CommandResult(
                command=command,
                arguments=request.arguments or [],
                working_directory=str(work_dir),
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration=elapsed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                cancelled=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - started
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return CommandResult(
                command=command,
                arguments=request.arguments or [],
                working_directory=str(work_dir),
                exit_code=-1,
                stdout=stdout,
                stderr=f"{stderr}\nCommand timed out after {timeout} seconds.",
                duration=elapsed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                cancelled=True,
            )
