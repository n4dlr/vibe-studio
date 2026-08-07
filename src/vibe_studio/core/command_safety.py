from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path


BLOCKLIST = {
    "rm -rf /",
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
}


@dataclass
class CommandRequest:
    command: str
    arguments: list[str] | None = None
    working_directory: str | None = None
    allow_destructive: bool = False


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


class CommandSafety:
    @staticmethod
    def validate(request: CommandRequest) -> None:
        command_text = request.command.lower()
        if request.allow_destructive:
            return
        for forbidden in BLOCKLIST:
            if forbidden in command_text:
                raise ValueError(f"Command blocked by safety policy: {request.command}")
        if "rm -rf" in command_text or "rm -rf" in shlex.join(request.arguments or []):
            raise ValueError("Destructive file deletion is blocked by default.")

    @staticmethod
    def run(command: str, *, cwd: str | Path | None = None, allow_destructive: bool = False) -> CommandResult:
        import subprocess
        import time
        from datetime import datetime, timezone

        request = CommandRequest(command=command, arguments=shlex.split(command), working_directory=str(cwd or Path.cwd()), allow_destructive=allow_destructive)
        CommandSafety.validate(request)
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=str(cwd or Path.cwd()),
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        elapsed = time.monotonic() - started
        return CommandResult(
            command=command,
            arguments=request.arguments or [],
            working_directory=str(cwd or Path.cwd()),
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration=elapsed,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
