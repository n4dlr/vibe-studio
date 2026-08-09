"""Tests for AgentTrainerDialog."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.ui.agent_trainer_dialog import AgentTrainerDialog
from vibe_studio.core.global_memory import GlobalMemory


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestAgentTrainerDialog:
    def test_dialog_init(self, qapp, tmp_path):
        gm = GlobalMemory(db_path=tmp_path / "trainer_test.db")
        dlg = AgentTrainerDialog(global_memory=gm)
        assert dlg.windowTitle() == "🎓 Agent Trainer — Teach Global Memory"
