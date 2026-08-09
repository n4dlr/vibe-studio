"""Unit test suite for StuckAgentDetector & DiffProposalManager."""
import pytest
from pathlib import Path
from vibe_studio.agents.stuck_detector import StuckAgentDetector
from vibe_studio.diff.diff_proposal import DiffProposalManager


def test_stuck_agent_detector():
    detector = StuckAgentDetector(max_identical_steps=3)

    # 2 identical steps -> not stuck
    detector.record_step("read_file", {"path": "a.py"}, "completed")
    detector.record_step("read_file", {"path": "a.py"}, "completed")
    assert detector.is_stuck() is False

    # 3rd identical step -> stuck
    detector.record_step("read_file", {"path": "a.py"}, "completed")
    assert detector.is_stuck() is True
    assert "STUCK RECOVERY" in detector.get_recovery_hint()


def test_diff_proposal_manager(tmp_path):
    dpm = DiffProposalManager(workspace_root=tmp_path)
    file_path = tmp_path / "hello.py"
    file_path.write_text("print('old')", encoding="utf-8")

    prop = dpm.create_proposal("exec_1", "hello.py", "print('new')")
    assert prop.status == "pending"
    assert "-" in prop.diff_text and "+" in prop.diff_text

    # Accept proposal
    ok = dpm.accept_proposal(prop.proposal_id)
    assert ok is True
    assert file_path.read_text(encoding="utf-8") == "print('new')"

    # Revert proposal
    ok_rev = dpm.revert_proposal(prop.proposal_id)
    assert ok_rev is True
    assert file_path.read_text(encoding="utf-8") == "print('old')"
