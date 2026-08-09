"""Process Sandbox for Vibe Studio.

Provides isolated process execution with resource limits (rlimit), environment variable sanitization,
and process group isolation.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class ProcessSandbox:
    """Executes subprocesses inside an isolated environment sandbox."""

    @classmethod
    def prepare_sanitized_env(cls) -> Dict[str, str]:
        """Return environment dictionary with sensitive tokens stripped."""
        env = os.environ.copy()
        # Redact sensitive environment keys that could leak secrets
        for key in list(env.keys()):
            if any(secret in key.upper() for secret in ["SECRET", "PASSWORD", "PRIVATE_KEY", "AWS_ACCESS"]):
                env.pop(key, None)
        return env

    @classmethod
    def run_sandboxed(
        cls,
        command: str,
        cwd: Path,
        timeout: int = 60,
        memory_limit_mb: int = 512,
    ) -> Tuple[int, str, str]:
        """Execute command inside process sandbox with resource limits."""
        env = cls.prepare_sanitized_env()

        def _preexec_fn():
            # Create new process group on Posix
            if os.name != "nt":
                os.setsid()
                try:
                    import resource
                    # Set max memory limit (RLIMIT_AS) in bytes
                    mem_bytes = memory_limit_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                except Exception:
                    pass

        try:
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                shell=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=_preexec_fn if os.name != "nt" else None,
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            return proc.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return -1, stdout or "", f"{stderr or ''}\n[SANDBOX TIMEOUT] Exceeded {timeout}s limit."
        except Exception as exc:
            return 1, "", str(exc)
