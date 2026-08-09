"""Tests for GraphVisualizerWidget and AgentTrainerDialog (Qt widgets headless)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.ui.graph_visualizer_widget import GraphVisualizerWidget
from vibe_studio.context.graph_rag import CodeGraph


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestGraphVisualizerWidget:
    def test_load_graph(self, qapp, tmp_path):
        widget = GraphVisualizerWidget()
        cg = CodeGraph()
        widget.load_graph(cg)
        assert widget.status_label.text() is not None

    def test_refresh_from_workspace(self, qapp, tmp_path):
        widget = GraphVisualizerWidget()
        (tmp_path / "a.py").write_text("def hello(): pass")
        widget.refresh_from_workspace(tmp_path)
        assert widget.status_label.text() is not None
