"""Tests for J.A.R.V.I.S Autonomous Subsystem."""
from __future__ import annotations

from pathlib import Path
from vibe_studio.jarvis.engine import JarvisCore, JarvisResponse
from vibe_studio.jarvis.system_tools import JarvisSystemTools
from vibe_studio.jarvis.telemetry import SystemSnapshot, SystemTelemetry
from vibe_studio.jarvis.voice_engine import JarvisVoiceEngine
from vibe_studio.jarvis.watchdog import JarvisWatchdog


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


def test_jarvis_core_greeting_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Hello Jarvis")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "greeting"
    assert "J.A.R.V.I.S online" in resp.spoken_text


def test_jarvis_core_network_check_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Jarvis, check network connection")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "network_check"


def test_jarvis_core_clean_cache_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    # create dummy __pycache__
    (tmp_path / "__pycache__").mkdir()
    resp = jarvis.execute_command("Jarvis, clean cache")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "clean_cache"
    assert not (tmp_path / "__pycache__").exists()


def test_jarvis_core_git_summary_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Jarvis, git summary")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "git_summary"


def test_jarvis_watchdog_lifecycle():
    telem = SystemTelemetry()
    alerts = []
    watchdog = JarvisWatchdog(telem, on_alert=lambda t, m: alerts.append((t, m)))
    assert not watchdog.is_running
    watchdog.start()
    assert watchdog.is_running
    watchdog.stop()
    assert not watchdog.is_running


def test_jarvis_voice_engine_presets():
    engine = JarvisVoiceEngine()
    engine.set_voice("british")
    assert engine.current_voice == JarvisVoiceEngine.VOICE_BRITISH_BUTLER
    assert engine._detect_voice("Hello sir, how are you?") == JarvisVoiceEngine.VOICE_BRITISH_BUTLER

    engine.set_voice("azerbaijani")
    assert engine.current_voice == JarvisVoiceEngine.VOICE_AZERBAIJANI
    assert engine._detect_voice("Salam, layihəyə bax") == JarvisVoiceEngine.VOICE_AZERBAIJANI

    engine.set_voice("turkish")
    assert engine.current_voice == JarvisVoiceEngine.VOICE_TURKISH



def test_jarvis_floating_avatar_creation(tmp_path: Path):
    from PySide6.QtWidgets import QApplication
    from vibe_studio.ui.jarvis_floating_avatar import JarvisFloatingAvatar
    app = QApplication.instance() or QApplication([])
    avatar = JarvisFloatingAvatar(workspace_root=tmp_path)
    avatar.show()
    assert avatar.portrait is not None
    assert avatar.popup_card is not None
    avatar._toggle_popup()
    assert not avatar.popup_card.isHidden()
    avatar._toggle_popup()
    assert avatar.popup_card.isHidden()


def test_jarvis_standalone_window_and_edge_snapping(tmp_path: Path):
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication
    from vibe_studio.ui.jarvis_window import JarvisStandaloneWindow

    app = QApplication.instance() or QApplication([])
    win = JarvisStandaloneWindow(workspace_root=tmp_path)
    win.show_and_activate()
    assert win.isVisible()
    assert win.title_bar is not None
    assert win.hud_panel is not None

    # Test snap left
    win.snap_left()
    assert win._is_snapped
    assert win.width() > 0

    # Test snap right
    win.snap_right()
    assert win._is_snapped

    # Test toggle pin on top
    assert not win._is_pinned
    win.toggle_pin_on_top()
    assert win._is_pinned
    win.toggle_pin_on_top()
    assert not win._is_pinned

    # Test check edge snapping top (maximize)
    screen_geo = win._get_current_screen_geometry()
    win.check_edge_snapping(QPoint(screen_geo.left() + 100, screen_geo.top() + 5))
    assert win._is_snapped
    assert win.geometry() == screen_geo

    # Test restore floating from drag
    win.restore_floating_from_drag(QPoint(500, 300))
    assert not win._is_snapped

    win.close()


def test_jarvis_model_switching_and_discovery(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path, model="qwen2.5-coder:14b")
    assert jarvis.model == "qwen2.5-coder:14b"
    models = jarvis.list_available_models()
    assert len(models) > 0
    assert "qwen2.5-coder:14b" in models

    jarvis.set_model("deepseek-coder-v2:lite")
    assert jarvis.model == "deepseek-coder-v2:lite"


def test_jarvis_llm_reasoning_tool_execution(tmp_path: Path):
    class MockProvider:
        def generate(self, prompt: str, **kwargs) -> str:
            if "browser" in prompt.lower() or "brave" in prompt.lower():
                return 'Certainly, sir. Opening Brave browser for you now. [TOOL: open_app("brave")]'
            return "At your service, sir."

    jarvis = JarvisCore(workspace_root=tmp_path, provider=MockProvider())
    resp = jarvis.execute_command("Jarvis please launch the brave browser")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "open_app"
    assert "Certainly, sir" in resp.spoken_text


def test_jarvis_compound_browser_and_network_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("Please launch Brave and check our network")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "compound_browser_and_network"
    assert "Launching Brave Browser" in resp.spoken_text
    assert "latency" in resp.spoken_text


def test_jarvis_fast_com_speedtest_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("open browser and test internet speed test on fast.com")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "open_url"
    assert "Fast.com" in resp.spoken_text
    assert resp.action_result.get("url") == "https://fast.com"


def test_jarvis_go_desktop_and_open_app_command(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)
    resp = jarvis.execute_command("go desktop and open tlauncher")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "desktop_launch_app"
    assert "Navigating to desktop" in resp.spoken_text
    assert "tlauncher" in resp.spoken_text


def test_jarvis_coding_bridge(tmp_path: Path):
    from vibe_studio.jarvis.coding_bridge import JarvisCodingBridge
    bridge = JarvisCodingBridge(workspace_root=tmp_path)

    # 1. Write file
    w_res = bridge.write_file("main.py", "def add(a, b):\n    return a + b\n")
    assert w_res["status"] == "success"
    assert (tmp_path / "main.py").exists()

    # 2. Read file
    r_res = bridge.read_file("main.py")
    assert r_res["status"] == "success"
    assert "def add" in r_res["content"]

    # 3. List files
    l_res = bridge.list_files(".")
    assert l_res["status"] == "success"
    assert l_res["count"] >= 1

    # 4. Terminal command execution
    c_res = bridge.execute_terminal_command("python3 -c 'print(2 + 2)'")
    assert c_res["status"] == "success"
    assert c_res["stdout"].strip() == "4"


def test_jarvis_full_agentic_write_file_execution(tmp_path: Path):
    class MockCodingProvider:
        def generate(self, prompt: str, **kwargs) -> str:
            return 'Əlbəttə, cənab. Sizin üçün server faylını yaradıram. [TOOL: write_file("server.py", "from fastapi import FastAPI\napp = FastAPI()\n")]'

    jarvis = JarvisCore(workspace_root=tmp_path, provider=MockCodingProvider())
    resp = jarvis.execute_command("Mənə bir FastAPI serveri yaz")
    assert isinstance(resp, JarvisResponse)
    assert resp.action_taken == "write_file"
    assert "server.py" in resp.files_modified
    assert (tmp_path / "server.py").exists()
    assert "FastAPI" in (tmp_path / "server.py").read_text()
    assert "Əlbəttə, cənab" in resp.spoken_text





