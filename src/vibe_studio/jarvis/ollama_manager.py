"""Ollama runtime and model lifecycle supervisor for JARVIS.

Ensures:
- Ollama is running exclusively on local interface (127.0.0.1:11434)
- Existing system Ollama daemon is detected & reused safely
- Bundled Ollama executable is used as fallback if system Ollama is absent
- Automatic model verification and auto-creation via Modelfile / GGUF
- Progress callback support during model creation/pulling
- Non-crashing graceful degradation if Ollama fails to start
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from packaging.common.paths import JarvisPaths

logger = logging.getLogger(__name__)


@dataclass
class OllamaStatus:
    is_running: bool
    version: str | None = None
    endpoint: str = "http://127.0.0.1:11434"
    executable_path: str | None = None
    is_bundled: bool = False
    available_models: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.available_models is None:
            self.available_models = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_running": self.is_running,
            "version": self.version,
            "endpoint": self.endpoint,
            "executable_path": self.executable_path,
            "is_bundled": self.is_bundled,
            "available_models": self.available_models,
        }


class OllamaManager:
    """Manages Ollama process lifecycle, health checks, and local model registration."""

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 11434
    DEFAULT_ENDPOINT = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"

    def __init__(self, endpoint: str | None = None, auto_start: bool = True) -> None:
        self.endpoint = (endpoint or self.DEFAULT_ENDPOINT).rstrip("/")
        self.auto_start = auto_start
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def find_ollama_executable(self) -> tuple[Path | None, bool]:
        """Locate Ollama binary. Returns (path, is_bundled)."""
        # 1. Check system PATH first
        system_bin = shutil.which("ollama")
        if system_bin:
            return Path(system_bin), False

        # 2. Check bundled runtime directory
        bundled_bin = JarvisPaths.get_bundled_ollama_path()
        if bundled_bin and bundled_bin.exists():
            return bundled_bin, True

        # 3. Check common platform locations
        if sys.platform == "win32":
            common_win = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
            if common_win.exists():
                return common_win, False
        elif sys.platform.startswith("linux"):
            for p in [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama")]:
                if p.exists() and os.access(p, os.X_OK):
                    return p, False

        return None, False

    def is_reachable(self, timeout_sec: float = 2.0) -> bool:
        """Check if Ollama server responds on HTTP endpoint."""
        try:
            req = Request(f"{self.endpoint}/api/tags", headers={"User-Agent": "JARVIS/1.0"})
            with urlopen(req, timeout=timeout_sec) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_version(self) -> str | None:
        """Fetch Ollama server version."""
        try:
            req = Request(f"{self.endpoint}/api/version", headers={"User-Agent": "JARVIS/1.0"})
            with urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("version")
        except Exception:
            return None

    def list_models(self) -> list[str]:
        """Retrieve list of registered model tags."""
        try:
            req = Request(f"{self.endpoint}/api/tags", headers={"User-Agent": "JARVIS/1.0"})
            with urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []

    def check_status(self) -> OllamaStatus:
        """Inspect current Ollama service health and inventory."""
        running = self.is_reachable()
        exe, bundled = self.find_ollama_executable()
        version = self.get_version() if running else None
        models = self.list_models() if running else []
        return OllamaStatus(
            is_running=running,
            version=version,
            endpoint=self.endpoint,
            executable_path=str(exe) if exe else None,
            is_bundled=bundled,
            available_models=models,
        )

    def start_service(self, max_wait_sec: float = 12.0) -> bool:
        """Start local Ollama daemon if not already active."""
        with self._lock:
            if self.is_reachable():
                logger.info("Ollama is already running at %s", self.endpoint)
                return True

            exe, _ = self.find_ollama_executable()
            if not exe:
                logger.warning("Ollama executable not found on system or bundle.")
                return False

            logger.info("Starting Ollama background process: %s serve", exe)
            env = os.environ.copy()
            # Strict security: bind exclusively to local loopback
            env["OLLAMA_HOST"] = f"{self.DEFAULT_HOST}:{self.DEFAULT_PORT}"

            try:
                if sys.platform == "win32":
                    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                    self._proc = subprocess.Popen(
                        [str(exe), "serve"],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=creationflags,
                    )
                else:
                    self._proc = subprocess.Popen(
                        [str(exe), "serve"],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
            except Exception as e:
                logger.error("Failed to spawn Ollama daemon: %s", e)
                return False

            # Wait for endpoint readiness
            deadline = time.time() + max_wait_sec
            while time.time() < deadline:
                if self.is_reachable(timeout_sec=0.5):
                    logger.info("Ollama started successfully (PID: %s)", getattr(self._proc, "pid", "unknown"))
                    return True
                time.sleep(0.4)

            logger.warning("Timed out waiting for Ollama to become ready.")
            return False

    def ensure_model_ready(
        self,
        model_name: str = "jarvis-qwen",
        modelfile_path: Path | str | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> bool:
        """Verify model exists in Ollama. If missing, create or pull it."""
        if not self.is_reachable():
            if self.auto_start:
                if not self.start_service():
                    return False
            else:
                return False

        models = self.list_models()
        # Exact match or prefix match (e.g. 'jarvis-qwen:latest' matches 'jarvis-qwen')
        for m in models:
            if m == model_name or m.startswith(f"{model_name}:"):
                if progress_callback:
                    progress_callback(f"Model '{model_name}' is ready.", 100.0)
                return True

        # Model is missing — attempt creation or pull
        logger.info("Model '%s' not found in Ollama inventory. Initializing...", model_name)

        # 1. If Modelfile exists, create custom model
        resolved_modelfile = self._resolve_modelfile(modelfile_path, model_name)
        if resolved_modelfile and resolved_modelfile.exists():
            return self._create_model_from_modelfile(model_name, resolved_modelfile, progress_callback)

        # 2. Otherwise pull model from registry (fallback)
        return self._pull_model(model_name, progress_callback)

    def _resolve_modelfile(self, modelfile_path: Path | str | None, model_name: str) -> Path | None:
        if modelfile_path:
            p = Path(modelfile_path)
            if p.exists():
                return p

        # Check standard model directories
        candidates = [
            JarvisPaths.get_models_dir() / model_name / "Modelfile",
            JarvisPaths.get_bundle_resource_dir() / "models" / model_name / "Modelfile",
            JarvisPaths.get_app_install_dir() / "models" / model_name / "Modelfile",
            Path("models") / model_name / "Modelfile",
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _create_model_from_modelfile(
        self,
        model_name: str,
        modelfile: Path,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> bool:
        """Create model via `ollama create <name> -f <modelfile>`."""
        exe, _ = self.find_ollama_executable()
        if not exe:
            return False

        if progress_callback:
            progress_callback(f"Compiling local model '{model_name}' from Modelfile...", 10.0)

        logger.info("Running: %s create %s -f %s", exe, model_name, modelfile)
        try:
            proc = subprocess.Popen(
                [str(exe), "create", model_name, "-f", str(modelfile)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(modelfile.parent),
            )
            pct = 15.0
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    line_str = line.strip()
                    if line_str:
                        logger.debug("[Ollama Create] %s", line_str)
                        pct = min(95.0, pct + 10.0)
                        if progress_callback:
                            progress_callback(line_str, pct)
                proc.stdout.close()
            proc.wait()

            success = (proc.returncode == 0)
            if success and progress_callback:
                progress_callback(f"Model '{model_name}' successfully compiled and registered!", 100.0)
            return success
        except Exception as e:
            logger.error("Failed to create model from Modelfile: %s", e)
            return False

    def _pull_model(
        self,
        model_name: str,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> bool:
        """Pull model tag via Ollama REST API with streaming progress."""
        if progress_callback:
            progress_callback(f"Downloading model '{model_name}'...", 5.0)

        url = f"{self.endpoint}/api/pull"
        data = json.dumps({"name": model_name, "stream": True}).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"})

        try:
            with urlopen(req, timeout=600) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        status = chunk.get("status", "")
                        total = chunk.get("total", 0)
                        completed = chunk.get("completed", 0)
                        pct = (completed / total * 100.0) if total > 0 else 50.0
                        if progress_callback:
                            msg = f"{status} ({round(pct, 1)}%)" if total > 0 else status
                            progress_callback(msg, pct)
                    except Exception:
                        pass
            if progress_callback:
                progress_callback(f"Model '{model_name}' ready!", 100.0)
            return True
        except Exception as e:
            logger.error("Failed to pull model %s: %s", model_name, e)
            return False

    def stop_service(self) -> None:
        """Stop Ollama if spawned by this manager."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=3)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None
