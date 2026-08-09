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

    def test_web_ui_endpoints(self, server):
        resp = urllib.request.urlopen("http://127.0.0.1:8899/")
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "Vibe Studio 4.0" in html

        css_resp = urllib.request.urlopen("http://127.0.0.1:8899/static/styles.css")
        assert css_resp.status == 200

    def test_plugins_rest_endpoint(self, server):
        resp = urllib.request.urlopen("http://127.0.0.1:8899/api/v1/plugins")
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert len(data["plugins"]) >= 30

    def test_predict_rest_endpoint(self, server):
        req_data = json.dumps({"current_file": "test_app.py"}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8899/api/v1/predict", data=req_data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req)
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "suggestions" in data

    def test_cli_plugin_commands(self, tmp_path):
        res = cli_main(["--root", str(tmp_path), "plugin", "list"])
        assert res == 0

        res_search = cli_main(["--root", str(tmp_path), "plugin", "search", "Docker"])
        assert res_search == 0

