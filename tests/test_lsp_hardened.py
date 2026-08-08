"""Hardened integration and unit tests for LSPClient, LSPServerRegistry,
IntelligenceRouter fallback, monotonic versioning, diagnostics routing, and Agent LSP tools.

Includes a deterministic MockLSPServer process harness for 100% reproducible testing.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
import pytest

from vibe_studio.editor.lsp_registry import LSPServerConfig, LSPServerRegistry, default_lsp_registry
from vibe_studio.editor.lsp_client import LSPClient, LSPClientState
from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine
from vibe_studio.tools.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Mock LSP Server Script (Runs as a subprocess speaking JSON-RPC 2.0 stdio)
# ---------------------------------------------------------------------------

MOCK_SERVER_SCRIPT = """
import sys
import json

def send_response(resp):
    body = json.dumps(resp).encode('utf-8')
    header = f"Content-Length: {len(body)}\\r\\n\\r\\n".encode('utf-8')
    sys.stdout.buffer.write(header + body)
    sys.stdout.buffer.flush()

while True:
    try:
        line = sys.stdin.buffer.readline()
        if not line:
            break
        if line.startswith(b"Content-Length:"):
            length = int(line.split(b":")[1].strip())
            sys.stdin.buffer.readline() # blank line
            content = sys.stdin.buffer.read(length)
            req = json.loads(content.decode('utf-8'))
            
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"capabilities": {"textDocumentSync": 1}}
                })
            elif method == "textDocument/definition":
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": [{"uri": params.get("textDocument", {}).get("uri", "") + ".target", "range": {"start": {"line": 10, "character": 4}}}]
                })
            elif method == "textDocument/references":
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": [{"uri": params.get("textDocument", {}).get("uri", ""), "range": {"start": {"line": 5, "character": 2}}}]
                })
            elif method == "textDocument/hover":
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"contents": {"kind": "markdown", "value": "### Mock Doc\\nMock hover documentation"}}
                })
            elif method == "textDocument/completion":
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"items": [{"label": "mock_func", "kind": 3, "detail": "def mock_func() -> int"}]}
                })
            elif method == "textDocument/documentSymbol":
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": [{"name": "MockClass", "kind": 5, "range": {"start": {"line": 1}}}]
                })
            elif method == "workspace/symbol":
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": [{"name": "MockGlobal", "kind": 13, "location": {"uri": "file:///test.py", "range": {"start": {"line": 1}}}}]
                })
            elif method == "shutdown":
                send_response({"jsonrpc": "2.0", "id": req_id, "result": None})
            elif method == "exit":
                sys.exit(0)
    except Exception:
        break
"""


@pytest.fixture
def mock_lsp_server(tmp_path):
    server_script = tmp_path / "mock_lsp_server.py"
    server_script.write_text(MOCK_SERVER_SCRIPT, encoding="utf-8")
    config = LSPServerConfig(
        language_id="mocklang",
        display_name="Mock LSP Server",
        file_extensions=[".mock"],
        command=sys.executable,
        args=[str(server_script)],
        priority=100,
    )
    return config


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestLSPHardened:

    def test_lsp_registry_discovery(self):
        reg = LSPServerRegistry()
        langs = reg.get_all_supported_languages()
        assert "python" in langs
        assert "typescript" in langs
        assert "rust" in langs

        py_srv = reg.find_available_server("python")
        # Pyright or pylsp or None depending on env
        if py_srv:
            assert py_srv.command in ("pyright-langserver", "pylsp")

    def test_mock_lsp_client_lifecycle(self, tmp_path, mock_lsp_server):
        client = LSPClient("mocklang", tmp_path, server_config=mock_lsp_server)
        assert client.state == LSPClientState.STOPPED

        started = client.start()
        assert started
        assert client.state == LSPClientState.RUNNING
        assert client.is_running

        client.stop()
        assert client.state == LSPClientState.STOPPED
        assert not client.is_running

    def test_monotonic_document_versions(self, tmp_path, mock_lsp_server):
        client = LSPClient("mocklang", tmp_path, server_config=mock_lsp_server)
        client.start()

        test_file = tmp_path / "test.mock"
        test_file.write_text("v1", encoding="utf-8")

        client.did_open(test_file, "v1")
        assert client.get_document_version(test_file) == 1

        v2 = client.did_change(test_file, "v2 content")
        assert v2 == 2
        assert client.get_document_version(test_file) == 2

        v3 = client.did_change(test_file, "v3 content")
        assert v3 == 3
        assert client.get_document_version(test_file) == 3

        # Duplicate content change should NOT increment version
        v3_again = client.did_change(test_file, "v3 content")
        assert v3_again == 3

        client.stop()

    def test_mock_lsp_queries(self, tmp_path, mock_lsp_server):
        client = LSPClient("mocklang", tmp_path, server_config=mock_lsp_server)
        client.start()

        test_file = tmp_path / "foo.mock"
        test_file.write_text("sample code", encoding="utf-8")
        client.did_open(test_file, "sample code")

        # Definition
        defs = client.goto_definition(test_file, 1, 5)
        assert len(defs) == 1
        assert "target" in defs[0]["uri"]

        # References
        refs = client.find_references(test_file, 1, 5)
        assert len(refs) == 1

        # Hover
        hover = client.hover(test_file, 1, 5)
        assert "Mock hover documentation" in hover

        # Completion
        ver, comps = client.get_completions(test_file, 1, 5)
        assert ver == 1
        assert len(comps) == 1
        assert comps[0]["label"] == "mock_func"

        # Symbols
        doc_syms = client.get_document_symbols(test_file)
        assert len(doc_syms) == 1
        assert doc_syms[0]["name"] == "MockClass"

        ws_syms = client.workspace_symbols("Mock")
        assert len(ws_syms) == 1
        assert ws_syms[0]["name"] == "MockGlobal"

        client.stop()

    def test_code_intelligence_lsp_router_fallback(self, tmp_path):
        engine = CodeIntelligenceEngine(tmp_path)
        
        # Write Python file for AST fallback testing
        py_file = tmp_path / "app.py"
        py_file.write_text("def calculate_tax(amount):\n    '''Calculate total tax.'''\n    return amount * 0.2\n")

        # Definition fallback
        defs = engine.find_definition("calculate_tax", py_file, line=1, column=4)
        assert len(defs) >= 1
        assert defs[0].symbol == "calculate_tax"
        assert defs[0].source in ("lsp", "fallback")

        # References fallback
        refs = engine.find_references("calculate_tax", py_file, line=1, column=4)
        assert len(refs) >= 1

        # Hover fallback
        hover = engine.get_hover_info("calculate_tax", py_file, line=1, column=4)
        assert hover is not None
        assert "Calculate total tax" in hover.docstring

        # Status check
        status = engine.get_status("python")
        assert "Python" in status

    def test_agent_lsp_tools_in_registry(self, tmp_path):
        py_file = tmp_path / "main.py"
        py_file.write_text("def main_entry(): pass\n")

        reg = ToolRegistry(tmp_path)

        # Definition tool
        res_def = reg.execute("lsp_goto_definition", {"file_path": "main.py", "symbol": "main_entry"})
        assert res_def["exit_code"] == 0

        # References tool
        res_ref = reg.execute("lsp_find_references", {"file_path": "main.py", "symbol": "main_entry"})
        assert res_ref["exit_code"] == 0

        # Hover tool
        res_hov = reg.execute("lsp_hover", {"file_path": "main.py", "symbol": "main_entry"})
        assert res_hov["exit_code"] == 0

        # Workspace symbols tool
        res_ws = reg.execute("lsp_workspace_symbols", {"query": "main"})
        assert res_ws["exit_code"] == 0
