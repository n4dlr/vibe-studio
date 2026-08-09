"""HTTP Server API — REST JSON interface for headless / remote agent invocation.

Pillar 2 (API & CLI Mode):
  Provides HTTP REST endpoints:
    - GET  /health           : Health status & workspace root
    - POST /api/v1/execute   : Execute an agent task (prompt, active_file)
    - GET  /api/v1/context   : Query ranked ContextBundle for a prompt
    - GET  /api/v1/graph     : Export CodeGraph summary (nodes, edges)
    - GET  /api/v1/memory    : Query GlobalMemory stats & patterns
"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from vibe_studio.agents.orchestrator import AgentOrchestrator
from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.context.graph_rag import CodeGraph
from vibe_studio.core.global_memory import GlobalMemory

logger = logging.getLogger(__name__)


class VibeAPIRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Vibe Studio REST API."""

    workspace_root: Path = Path.cwd()
    orchestrator: AgentOrchestrator | None = None
    context_engine: ContextEngine | None = None
    global_memory: GlobalMemory | None = None

    def _set_headers(self, status: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._set_headers(200)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(body)
        except Exception:
            return {}

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path == "/health":
            self._set_headers(200)
            res = {
                "status": "ok",
                "service": "Vibe Studio REST API 3.0",
                "workspace": str(self.workspace_root),
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/v1/memory":
            gm = self.global_memory or GlobalMemory(db_path=self.workspace_root / ".vibe_studio" / "global_memory.db")
            self._set_headers(200)
            self.wfile.write(json.dumps(gm.stats()).encode("utf-8"))

        elif path == "/api/v1/graph":
            cg = CodeGraph.build_from_root(self.workspace_root)
            self._set_headers(200)
            res = {
                "available": cg.available,
                "symbols_count": len(cg.symbol_file_map),
                "files_count": len(cg.file_symbols_map),
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/v1/context":
            prompt = self.path.split("prompt=")[-1] if "prompt=" in self.path else "main"
            ce = self.context_engine or ContextEngine(self.workspace_root, graph_expand=True)
            bundle = ce.build(prompt=prompt)
            self._set_headers(200)
            res = {
                "total_tokens_est": bundle.total_tokens_est,
                "items_count": len(bundle.items),
                "items": [{"path": item.path, "score": item.score, "reason": item.reason} for item in bundle.items],
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

    def do_POST(self) -> None:
        path = self.path.split("?")[0]

        if path == "/api/v1/execute":
            body = self._read_json_body()
            prompt = body.get("prompt", "")
            active_file = body.get("active_file", None)

            if not prompt:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "'prompt' field is required"}).encode("utf-8"))
                return

            orch = self.orchestrator or AgentOrchestrator(self.workspace_root)
            result = orch.execute_task(prompt=prompt, active_file=active_file)

            self._set_headers(200)
            res = {
                "prompt": prompt,
                "summary": result.summary,
                "files_changed": result.execution_result.files_changed if result.execution_result else [],
                "status": result.execution_result.status.value if result.execution_result else "UNKNOWN",
                "stage_timings": [{"stage": t.stage_name, "duration": t.duration_seconds} for t in result.stage_timings],
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("VibeAPI: " + format, *args)


def create_api_server(
    workspace_root: str | Path,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> HTTPServer:
    """Create a configured HTTPServer instance."""
    ws = Path(workspace_root).resolve()
    handler = VibeAPIRequestHandler
    handler.workspace_root = ws
    handler.orchestrator = AgentOrchestrator(ws)
    handler.context_engine = ContextEngine(ws, graph_expand=True)
    handler.global_memory = GlobalMemory()

    server = HTTPServer((host, port), handler)
    logger.info("Vibe Studio API server initialized on http://%s:%d", host, port)
    return server
