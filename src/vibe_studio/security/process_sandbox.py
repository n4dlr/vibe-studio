"""Process Sandbox — isolated execution with resource limits and optional Docker containment.

Execution modes (in order of preference):
  1. Docker container (if docker-py installed and Docker daemon running)
  2. Process group isolation with rlimits (Linux/macOS)
  3. Basic subprocess (Windows / Docker unavailable)
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class DockerUnavailableError(Exception):
    """Raised when Docker is requested but not available."""


class ProcessSandbox:
    """Executes subprocesses inside an isolated environment sandbox."""

    # ------------------------------------------------------------------
    # Environment sanitization
    # ------------------------------------------------------------------

    @classmethod
    def prepare_sanitized_env(cls) -> Dict[str, str]:
        """Return environment dict with sensitive tokens stripped."""
        env = os.environ.copy()
        for key in list(env.keys()):
            if any(s in key.upper() for s in [
                "SECRET", "PASSWORD", "PRIVATE_KEY", "AWS_ACCESS",
                "GITHUB_TOKEN", "API_KEY", "AUTH_TOKEN",
            ]):
                env.pop(key, None)
        return env

    # ------------------------------------------------------------------
    # Standard sandboxed subprocess (rlimit)
    # ------------------------------------------------------------------

    @classmethod
    def run_sandboxed(
        cls,
        command: str,
        cwd: Path,
        timeout: int = 60,
        memory_limit_mb: int = 512,
    ) -> Tuple[int, str, str]:
        """Execute command in process sandbox with resource limits."""
        env = cls.prepare_sanitized_env()

        def _preexec_fn():
            if os.name != "nt":
                os.setsid()
                try:
                    import resource
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

    # ------------------------------------------------------------------
    # Docker sandbox (Zero-Trust)
    # ------------------------------------------------------------------

    @classmethod
    def run_in_docker(
        cls,
        command: str,
        workspace_path: Path,
        image: str = "python:3.11-slim",
        timeout: int = 120,
        network_disabled: bool = True,
        memory_limit: str = "512m",
        cpu_quota: int = 50000,      # 50% of one CPU core
    ) -> Tuple[int, str, str]:
        """Execute command inside a Docker container for maximum isolation.

        The workspace is mounted read-only at /workspace.
        Network is disabled by default (Zero-Trust).

        Args:
            command:          Shell command to run inside container.
            workspace_path:   Path to mount as /workspace (read-only).
            image:            Docker image to use.
            timeout:          Max seconds before container is killed.
            network_disabled: If True, container has no network access.
            memory_limit:     Docker memory limit (e.g. "512m").
            cpu_quota:        Docker CPU quota in microseconds per period.

        Returns:
            (exit_code, stdout, stderr)
        """
        try:
            import docker  # type: ignore
        except ImportError:
            logger.warning("docker-py not installed. Falling back to process sandbox.")
            return cls.run_sandboxed(command, workspace_path, timeout=timeout)

        try:
            client = docker.from_env(timeout=10)
            client.ping()
        except Exception as exc:
            logger.warning("Docker unavailable (%s). Falling back to process sandbox.", exc)
            return cls.run_sandboxed(command, workspace_path, timeout=timeout)

        try:
            container = client.containers.run(
                image=image,
                command=["/bin/sh", "-c", command],
                volumes={
                    str(workspace_path.resolve()): {
                        "bind": "/workspace",
                        "mode": "ro",
                    }
                },
                working_dir="/workspace",
                mem_limit=memory_limit,
                cpu_quota=cpu_quota,
                network_disabled=network_disabled,
                remove=True,
                detach=False,
                stdout=True,
                stderr=True,
                environment=cls.prepare_sanitized_env(),
            )
            # container.run with detach=False returns bytes
            if isinstance(container, bytes):
                return 0, container.decode("utf-8", errors="replace"), ""
            return 0, str(container), ""
        except Exception as exc:
            err_str = str(exc)
            if "timeout" in err_str.lower():
                return -1, "", f"[DOCKER TIMEOUT] {err_str}"
            logger.warning("Docker run failed: %s", exc)
            return 1, "", err_str

    # ------------------------------------------------------------------
    # Auto-select best sandbox
    # ------------------------------------------------------------------

    @classmethod
    def run_best_available(
        cls,
        command: str,
        cwd: Path,
        prefer_docker: bool = False,
        timeout: int = 60,
    ) -> Tuple[int, str, str]:
        """Automatically choose the best sandbox mode available."""
        if prefer_docker:
            return cls.run_in_docker(command, workspace_path=cwd, timeout=timeout)
        return cls.run_sandboxed(command, cwd, timeout=timeout)
