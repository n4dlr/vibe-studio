"""Tests for CLI & REST HTTP Server API."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from threading import Thread

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.api.http_server import create_api_server
from vibe_studio.cli import main as cli_main


class TestCLIAndHTTP:
    @pytest.fixture
    def server(self, tmp_path):
        srv = create_api_server(workspace_root=tmp_path, host="127.0.0.1", port=8899)
        thread = Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        yield srv
        srv.shutdown()

    def test_health_endpoint(self, server):
        resp = urllib.request.urlopen("http://127.0.0.1:8899/health")
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"

    def test_memory_endpoint(self, server):
        resp = urllib.request.urlopen("http://127.0.0.1:8899/api/v1/memory")
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "total_patterns" in data

    def test_graph_endpoint(self, server):
        resp = urllib.request.urlopen("http://127.0.0.1:8899/api/v1/graph")
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "available" in data

    def test_cli_index_command(self, tmp_path):
        (tmp_path / "mod.py").write_text("def hello(): pass")
        res = cli_main(["index", "--root", str(tmp_path)])
        assert res == 0
