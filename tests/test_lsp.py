"""Unit tests for LSPClient and LSP fallback integration."""
from __future__ import annotations

import os
os.environ.setdefault("VIBE_STUDIO_OFFLINE", "1")

from pathlib import Path
import pytest

from vibe_studio.editor.lsp_client import LSPClient
from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine


class TestLSPClient:
    def test_lsp_client_initialization(self, tmp_path):
        client = LSPClient("python", tmp_path)
        assert client.language == "python"
        assert client.workspace_root == tmp_path.resolve()
        assert not client.is_running

    def test_lsp_client_is_available_check(self, tmp_path):
        client = LSPClient("unknown_lang", tmp_path)
        assert not client.is_available()

    def test_code_intelligence_lsp_fallback(self, tmp_path):
        engine = CodeIntelligenceEngine(tmp_path)
        client = engine.get_lsp_client("python")
        # If no pylsp/pyright installed in environment, client is None and fallback handles definition
        calc = tmp_path / "calc.py"
        calc.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        defs = engine.find_definition("add")
        assert len(defs) >= 1
        assert defs[0].symbol == "add"
