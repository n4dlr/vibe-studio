"""LSPClient — Language Server Protocol (JSON-RPC 2.0 stdio) client for Vibe Studio.

Provides real LSP protocol support for Pyright, pylsp, typescript-language-server,
gopls, rust-analyzer, and clangd over stdio transport.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable


class LSPClient:
    """JSON-RPC 2.0 client communicating with external Language Servers via stdio."""

    KNOWN_SERVERS: dict[str, str] = {
        "python": "pylsp",
        "typescript": "typescript-language-server",
        "javascript": "typescript-language-server",
        "go": "gopls",
        "rust": "rust-analyzer",
        "c": "clangd",
        "cpp": "clangd",
    }

    def __init__(self, language: str, workspace_root: str | Path):
        self.language = language.lower()
        self.workspace_root = Path(workspace_root).resolve()
        self.server_cmd = self.KNOWN_SERVERS.get(self.language, "")
        self.process: subprocess.Popen[bytes] | None = None
        self._request_id = 0
        self._pending_responses: dict[int, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.is_running = False

    def is_available(self) -> bool:
        if not self.server_cmd:
            return False
        return shutil.which(self.server_cmd) is not None

    def start(self) -> bool:
        if not self.is_available():
            return False

        try:
            cmd = [self.server_cmd]
            if self.server_cmd == "typescript-language-server":
                cmd.append("--stdio")

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=str(self.workspace_root),
            )
            self.is_running = True

            # Start reader thread
            t = threading.Thread(target=self._read_responses, daemon=True)
            t.start()

            # Send LSP initialize request
            init_res = self._send_request(
                "initialize",
                {
                    "processId": os.getpid(),
                    "rootUri": self.workspace_root.as_uri(),
                    "capabilities": {
                        "textDocument": {
                            "definition": {"dynamicRegistration": True},
                            "hover": {"dynamicRegistration": True},
                            "completion": {"completionItem": {"snippetSupport": True}},
                        }
                    },
                },
            )
            if init_res:
                self._send_notification("initialized", {})
                return True
        except Exception:
            self.is_running = False
            return False
        return False

    def stop(self) -> None:
        if self.process and self.is_running:
            try:
                self._send_request("shutdown", {})
                self._send_notification("exit", {})
                self.process.terminate()
            except Exception:
                pass
            self.is_running = False

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 stdio transport
    # ------------------------------------------------------------------

    def _send_request(self, method: str, params: dict[str, Any], timeout: float = 2.0) -> dict[str, Any] | None:
        if not self.process or not self.process.stdin:
            return None

        with self._lock:
            self._request_id += 1
            req_id = self._request_id

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")

        try:
            self.process.stdin.write(header + body)
            self.process.stdin.flush()
        except Exception:
            return None

        # Wait for response
        start_time = threading.Event()
        start_time.wait(timeout=timeout)
        return self._pending_responses.pop(req_id, None)

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            return
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        try:
            self.process.stdin.write(header + body)
            self.process.stdin.flush()
        except Exception:
            pass

    def _read_responses(self) -> None:
        while self.process and self.process.stdout and self.is_running:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                if line.startswith(b"Content-Length:"):
                    length = int(line.split(b":")[1].strip())
                    # Skip blank line
                    self.process.stdout.readline()
                    content = self.process.stdout.read(length)
                    data = json.loads(content.decode("utf-8"))
                    if "id" in data:
                        self._pending_responses[data["id"]] = data
            except Exception:
                break

    # ------------------------------------------------------------------
    # High-level LSP features
    # ------------------------------------------------------------------

    def goto_definition(self, file_path: str, line: int, character: int) -> list[dict[str, Any]]:
        uri = (self.workspace_root / file_path).as_uri()
        res = self._send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": max(0, line - 1), "character": character},
            },
        )
        if not res or "result" not in res:
            return []
        result = res["result"]
        if isinstance(result, dict):
            result = [result]
        return result or []

    def hover(self, file_path: str, line: int, character: int) -> str:
        uri = (self.workspace_root / file_path).as_uri()
        res = self._send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": max(0, line - 1), "character": character},
            },
        )
        if not res or "result" not in res or not res["result"]:
            return ""
        contents = res["result"].get("contents", "")
        if isinstance(contents, dict):
            return contents.get("value", "")
        if isinstance(contents, list):
            return "\n".join(str(c) for c in contents)
        return str(contents)
