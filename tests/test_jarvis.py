"""Tests for J.A.R.V.I.S Autonomous Subsystem."""
from __future__ import annotations

from pathlib import Path
from vibe_studio.jarvis.engine import JarvisCore, JarvisResponse
from vibe_studio.jarvis.system_tools import JarvisSystemTools
from vibe_studio.jarvis.telemetry import SystemSnapshot, SystemTelemetry


def test_system_telemetry_get_snapshot():
    telem = SystemTelemetry()
    snap = telem.get_snapshot()
    assert isinstance(snap, SystemSnapshot)
    assert snap.cpu_cores >= 1
    assert snap.ram_total_gb > 0
    assert snap.disk_total_gb > 0
    assert len(snap.os_name) > 0

    d = snap.to_dict()
    assert "cpu_percent" in d
    assert "ram_used_gb" in d
    assert "hostname" in d

    summary = snap.summary_text()
    assert "CPU:" in summary
    assert "RAM:" in summary


def test_jarvis_core_system_status_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Jarvis, what is the system status?")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "system_diagnostics"
    assert "System status is nominal" in resp.spoken_text
    assert resp.telemetry is not None


def test_jarvis_core_screenshot_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Jarvis, take a screenshot")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "take_screenshot"


def test_jarvis_core_volume_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Jarvis, set volume to 50")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "set_volume"
    assert "50 percent" in resp.spoken_text


def test_jarvis_core_open_app_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Jarvis, open browser")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "open_app"


def test_jarvis_core_web_search_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Jarvis, search for quantum computing")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "search_web"
    assert "quantum computing" in resp.spoken_text
