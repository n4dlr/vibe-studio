"""LSPClient — Language Server Protocol (JSON-RPC 2.0 stdio) client for Vibe Studio.

Provides real LSP protocol support for Pyright, pylsp, typescript-language-server,
gopls, rust-analyzer, and clangd over stdio transport.

Bug fix: replaced busy-wait (threading.Event().wait()) with per-request Events
stored in _pending_events so each send properly waits for its specific response.
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
        self._id_lock = threading.Lock()

        # Per-request response storage: id → response dict
        self._pending_responses: dict[int, dict[str, Any]] = {}
        # Per-request event: id → threading.Event (set when response arrives)
        self._pending_events: dict[int, threading.Event] = {}
        self._response_lock = threading.Lock()

        # Diagnostics published by the server
        self._diagnostics: dict[str, list[dict[str, Any]]] = {}
        self._diagnostics_callbacks: list[Callable[[str, list[dict[str, Any]]], None]] = []

        self.is_running = False

    def is_available(self) -> bool:
        if not self.server_cmd:
            return False
        return shutil.which(self.server_cmd) is not None

    def on_diagnostics(self, callback: Callable[[str, list[dict[str, Any]]], None]) -> None:
        """Register a callback for textDocument/publishDiagnostics notifications."""
        self._diagnostics_callbacks.append(callback)

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
            t = threading.Thread(target=self._read_responses, daemon=True, name="lsp-reader")
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
                            "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                            "completion": {
                                "completionItem": {
                                    "snippetSupport": True,
                                    "documentationFormat": ["markdown", "plaintext"],
                                }
                            },
                            "publishDiagnostics": {"relatedInformation": True},
                        },
                        "workspace": {
                            "symbol": {"dynamicRegistration": True},
                        },
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
                self._send_request("shutdown", {}, timeout=1.0)
                self._send_notification("exit", {})
                self.process.terminate()
            except Exception:
                pass
            self.is_running = False

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 stdio transport
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        with self._id_lock:
            self._request_id += 1
            return self._request_id

    def _send_request(self, method: str, params: dict[str, Any], timeout: float = 3.0) -> dict[str, Any] | None:
        if not self.process or not self.process.stdin:
            return None

        req_id = self._next_id()

        # Register event BEFORE sending so reader thread can't miss the response
        event = threading.Event()
        with self._response_lock:
            self._pending_events[req_id] = event

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
            with self._response_lock:
                self._pending_events.pop(req_id, None)
            return None

        # Wait for the specific response event (proper correlated wait)
        event.wait(timeout=timeout)

        with self._response_lock:
            self._pending_events.pop(req_id, None)
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
                    # Skip blank line separator
                    self.process.stdout.readline()
                    content = self.process.stdout.read(length)
                    data = json.loads(content.decode("utf-8"))

                    if "id" in data:
                        # This is a response to a request
                        req_id = data["id"]
                        with self._response_lock:
                            self._pending_responses[req_id] = data
                            event = self._pending_events.get(req_id)
                        if event:
                            event.set()  # Wake up the waiting _send_request
                    elif data.get("method") == "textDocument/publishDiagnostics":
                        # Server-initiated diagnostics notification
                        params = data.get("params", {})
                        uri = params.get("uri", "")
                        diags = params.get("diagnostics", [])
                        self._diagnostics[uri] = diags
                        for cb in self._diagnostics_callbacks:
                            try:
                                cb(uri, diags)
                            except Exception:
                                pass
            except Exception:
                break

    # ------------------------------------------------------------------
    # High-level LSP features
    # ------------------------------------------------------------------

    def notify_open(self, file_path: str, content: str, language_id: str | None = None) -> None:
        """Notify the server that a document was opened."""
        uri = (self.workspace_root / file_path).as_uri()
        self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id or self.language,
                "version": 1,
                "text": content,
            }
        })

    def notify_change(self, file_path: str, content: str, version: int = 2) -> None:
        """Notify the server of document changes."""
        uri = (self.workspace_root / file_path).as_uri()
        self._send_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": version},
            "contentChanges": [{"text": content}],
        })

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

    def get_completions(self, file_path: str, line: int, character: int) -> list[dict[str, Any]]:
        """Request completion items at the given position."""
        uri = (self.workspace_root / file_path).as_uri()
        res = self._send_request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": max(0, line - 1), "character": character},
            },
        )
        if not res or "result" not in res or not res["result"]:
            return []
        result = res["result"]
        # Result can be CompletionList or CompletionItem[]
        if isinstance(result, dict):
            return result.get("items", [])
        if isinstance(result, list):
            return result
        return []

    def workspace_symbols(self, query: str) -> list[dict[str, Any]]:
        """Search for symbols across the workspace."""
        res = self._send_request("workspace/symbol", {"query": query})
        if not res or "result" not in res:
            return []
        return res["result"] or []

    def get_diagnostics(self, file_path: str) -> list[dict[str, Any]]:
        """Return last known diagnostics for a file."""
        uri = (self.workspace_root / file_path).as_uri()
        return self._diagnostics.get(uri, [])
