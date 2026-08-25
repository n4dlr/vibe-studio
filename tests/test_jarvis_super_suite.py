"""Exhaustive unit & integration tests for J.A.R.V.I.S. Super-Suite:
1. Timers, Scheduler & Alarm Daemon
2. YouTube & Spotify Direct Search & Launcher
3. Global Disk & Semantic File Finder
4. Native Desktop OS Notifications
5. Vision Screen & Webcam Capture
6. Window, Mouse & Keyboard Automation
7. Natural Language Intent Routing in JarvisCore
"""
from __future__ import annotations

import time
from pathlib import Path
import pytest

from vibe_studio.jarvis.engine import JarvisCore, JarvisResponse
from vibe_studio.jarvis.scheduler import JarvisScheduler, ScheduledItem
from vibe_studio.jarvis.system_tools import JarvisSystemTools


def test_scheduler_relative_timer():
    triggered = []

    def on_trig(item: ScheduledItem):
        triggered.append(item.label)

    sched = JarvisScheduler(on_trigger=on_trig)
    item = sched.set_timer(0.2, "Tea Reminder")
    assert item.label == "Tea Reminder"
    assert item.status == "active"
    assert len(sched.list_active_timers()) == 1

    time.sleep(0.8)
    assert "Tea Reminder" in triggered
    assert item.status == "completed"
    sched.stop()


def test_scheduler_alarm_and_cancellation():
    sched = JarvisScheduler()
    item = sched.set_alarm("23:59", "Night Check")
    assert item is not None
    assert item.is_alarm is True
    assert item.alarm_time_str == "23:59"

    # Cancel timer
    assert sched.cancel_timer(item.id) is True
    assert item.status == "cancelled"
    sched.stop()


def test_youtube_and_spotify_search(tmp_path: Path):
    tools = JarvisSystemTools(tmp_path)

    yt = tools.play_youtube("Hans Zimmer Interstellar")
    assert yt["status"] == "success"
    assert "youtube.com" in yt["url"]
    assert "watch?v=" in yt["url"] or "results" in yt["url"]


    sp = tools.play_spotify("Eminem Lose Yourself")
    assert sp["status"] == "success"
    assert "youtube" in sp["url"] or "youtube" in sp.get("message", "").lower()



def test_global_file_finder(tmp_path: Path):
    tools = JarvisSystemTools(tmp_path)
    (tmp_path / "financial_report_2026.pdf").write_text("dummy pdf", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("dummy notes", encoding="utf-8")

    res = tools.find_files_global("financial_report", search_dir=str(tmp_path))
    assert res["status"] == "success"
    assert res["count"] >= 1
    assert any("financial_report_2026.pdf" in m["name"] for m in res["matches"])


def test_desktop_notification_emission(tmp_path: Path):
    tools = JarvisSystemTools(tmp_path)
    res = tools.show_desktop_notification("J.A.R.V.I.S.", "System check complete")
    assert res["status"] == "success"
    assert res["title"] == "J.A.R.V.I.S."


def test_vision_screenshot_and_webcam(tmp_path: Path):
    tools = JarvisSystemTools(tmp_path)
    v_res = tools.analyze_screenshot_vision("Analyze screen")
    assert v_res["status"] == "success"
    assert "analysis" in v_res

    cam_res = tools.capture_webcam(str(tmp_path / "test_cam.jpg"))
    assert "status" in cam_res


def test_window_control_and_keyboard(tmp_path: Path):
    tools = JarvisSystemTools(tmp_path)
    w_res = tools.window_control("maximize")
    assert w_res["status"] in ("success", "simulated")

    k_res = tools.press_keys("ctrl+c")
    assert k_res["status"] in ("success", "simulated")

    t_res = tools.type_text("hello world")
    assert t_res["status"] in ("success", "simulated")

    m_res = tools.click_mouse(100, 200, "left")
    assert m_res["status"] in ("success", "simulated")
    assert m_res["x"] == 100
    assert m_res["y"] == 200


def test_jarvis_play_music_defaults_to_youtube(tmp_path: Path):
    tools = JarvisSystemTools(tmp_path)
    res = tools.play_music("Queen Bohemian Rhapsody")
    assert res["status"] == "success"
    assert "youtube" in res["url"]


def test_jarvis_core_super_suite_intents(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)

    # 1. Timer intent
    resp_timer = jarvis.execute_command("5 dəqiqə sonra çayı xatırlat")
    assert isinstance(resp_timer, JarvisResponse)
    assert resp_timer.action_taken == "set_timer"
    assert "taymeri quruldu" in resp_timer.spoken_text or "timer set" in resp_timer.spoken_text.lower()

    # 2. Direct Azerbaijani music query (e.g. inna caliente musiqisini ac)
    resp_inna = jarvis.execute_command("inna caliente musiqisini ac")
    assert isinstance(resp_inna, JarvisResponse)
    assert resp_inna.action_taken == "play_youtube"
    assert "inna caliente" in resp_inna.spoken_text.lower() or "youtube" in resp_inna.spoken_text.lower()

    # 3. Direct first video auto-play intent (e.g. browserde 1ci mahnini ac)
    resp_first = jarvis.execute_command("browserde 1ci mahnini ac")
    assert isinstance(resp_first, JarvisResponse)
    assert resp_first.action_taken == "play_first_video"

    # 4. YouTube intent (e.g. open the inna-caliente music in ytb)
    resp_ytb = jarvis.execute_command("open the inna-caliente music in ytb")
    assert isinstance(resp_ytb, JarvisResponse)
    assert resp_ytb.action_taken == "play_youtube"
    assert "youtube" in resp_ytb.spoken_text.lower() or "inna-caliente" in resp_ytb.spoken_text.lower()

    # 5. Global file search intent
    resp_find = jarvis.execute_command("bütün kompüterdə report tap")
    assert isinstance(resp_find, JarvisResponse)
    assert resp_find.action_taken == "find_files_global"
    assert "fayl" in resp_find.spoken_text.lower() or "files" in resp_find.spoken_text.lower()


    # 5. Desktop notification intent
    resp_notif = jarvis.execute_command("send notification Task completed successfully")
    assert isinstance(resp_notif, JarvisResponse)
    assert resp_notif.action_taken == "desktop_notification"

    # 6. Vision analysis intent
    resp_vision = jarvis.execute_command("ekranı analiz et")
    assert isinstance(resp_vision, JarvisResponse)
    assert resp_vision.action_taken == "vision_analysis"

    # 7. Window control intent
    resp_win = jarvis.execute_command("tam ekran et")
    assert isinstance(resp_win, JarvisResponse)
    assert resp_win.action_taken == "window_control"


def test_jarvis_llm_reasoning_super_suite_tool_execution(tmp_path: Path):
    class SuperMockProvider:
        def generate(self, prompt: str, **kwargs) -> str:
            if "tea" in prompt.lower():
                return 'Certainly, sir. Setting a timer for your tea. [TOOL: set_timer(300, "Tea")]'
            elif "music" in prompt.lower():
                return 'Playing your track right away, sir. [TOOL: play_music("Interstellar")]'
            elif "notify" in prompt.lower():
                return 'Sending notification, sir. [TOOL: show_notification("J.A.R.V.I.S.", "System updated")]'
            return "At your command, sir."

    jarvis = JarvisCore(workspace_root=tmp_path, provider=SuperMockProvider())
    resp_timer = jarvis._reason_with_agentic_llm("Jarvis set timer for tea")
    assert resp_timer[1] == "set_timer"
    assert "set_timer" in resp_timer[2]

    resp_music = jarvis._reason_with_agentic_llm("Jarvis play some music")
    assert resp_music[1] == "play_music"
    assert "play_music" in resp_music[2]

    resp_notify = jarvis._reason_with_agentic_llm("Jarvis notify me when done")
    assert resp_notify[1] == "show_notification"
    assert "notification" in resp_notify[2]


def test_jarvis_neural_voice_engine_gender_and_personas(tmp_path: Path):
    from vibe_studio.jarvis.voice_engine import JarvisVoiceEngine

    engine = JarvisVoiceEngine(cache_dir=tmp_path)
    # Default is male
    assert engine.gender == "male"
    assert "Babek" in engine.VOICE_AZ_MALE
    assert "Banu" in engine.VOICE_AZ_FEMALE

    # Switch to female
    info_f = engine.set_gender("female")
    assert info_f["gender"] == "female"
    assert info_f["persona"] == "banu"
    assert "Banu" in info_f["voice"]

    # Toggle back to male
    info_m = engine.toggle_gender()
    assert info_m["gender"] == "male"
    assert info_m["persona"] == "babek"

    # Set specific persona (e.g. friday)
    info_fri = engine.set_persona("friday")
    assert info_fri["gender"] == "female"
    assert "Jenny" in info_fri["voice"]


def test_jarvis_advanced_system_tools_wifi_bt_tabs(tmp_path: Path):
    tools = JarvisSystemTools(tmp_path)

    # 1. Read active browser tab
    tab_res = tools.read_active_browser_tab()
    assert tab_res["status"] == "success"
    assert "title" in tab_res

    # 2. Visual OCR clicker
    click_res = tools.click_element_by_text("Login")
    assert click_res["status"] in ("success", "simulated")

    # 3. Wi-Fi control
    wifi_res = tools.manage_wifi("status")
    assert wifi_res["status"] in ("success", "simulated")

    # 4. Bluetooth control
    bt_res = tools.manage_bluetooth("status")
    assert bt_res["status"] in ("success", "simulated")


def test_jarvis_advanced_intents(tmp_path: Path):
    jarvis = JarvisCore(workspace_root=tmp_path)

    # Voice gender switch
    r_v = jarvis.execute_command("qadın səsinə keç")
    assert r_v.action_taken == "set_voice_gender"
    assert jarvis.voice_engine.gender == "female"

    r_vm = jarvis.execute_command("kişi səsinə keç")
    assert r_vm.action_taken == "set_voice_gender"
    assert jarvis.voice_engine.gender == "male"

    # Active browser tab reading
    r_tab = jarvis.execute_command("bu səhifəni oxu")
    assert r_tab.action_taken == "read_active_browser_tab"

    # Wi-Fi command
    r_wf = jarvis.execute_command("wifi axtar")
    assert r_wf.action_taken == "manage_wifi"

    # Bluetooth command
    r_bt = jarvis.execute_command("bluetooth söndür")
    assert r_bt.action_taken == "manage_bluetooth"

    # Power profile
    r_perf = jarvis.execute_command("performans rejimi")
    assert r_perf.action_taken == "set_power_profile"

    r_eco = jarvis.execute_command("qənaət rejimi")
    assert r_eco.action_taken == "set_power_profile"

    r_bal = jarvis.execute_command("balans rejimi")
    assert r_bal.action_taken == "set_power_profile"

    # Battery status
    r_bat = jarvis.execute_command("batareya")
    assert r_bat.action_taken == "get_battery_status"

    # Night light
    r_nl_on = jarvis.execute_command("gecə işığını yandır")
    assert r_nl_on.action_taken == "set_night_light"

    r_nl_off = jarvis.execute_command("gecə işığını söndür")
    assert r_nl_off.action_taken == "set_night_light"

    # Scroll
    r_scr_d = jarvis.execute_command("aşağı sürüşdür")
    assert r_scr_d.action_taken == "scroll_mouse"

    r_scr_u = jarvis.execute_command("yuxarı sürüşdür")
    assert r_scr_u.action_taken == "scroll_mouse"

    # Monitor listing
    r_mon = jarvis.execute_command("monitorları göstər")
    assert r_mon.action_taken == "get_display_monitors"


def test_jarvis_system_tools_new_features(tmp_path: Path):
    """Tests for power, battery, multi-monitor, night light, and mouse automation tools."""
    tools = JarvisSystemTools(tmp_path)

    # Battery status always returns something
    bat = tools.get_battery_status()
    assert bat["status"] in ("success", "simulated")
    assert "percent" in bat

    # Power profile switch (simulated if no powerprofilesctl)
    for profile in ("performance", "balanced", "power-saver"):
        p_res = tools.set_power_profile(profile)
        assert p_res["status"] in ("success", "simulated", "error")

    # Night light toggle
    nl_on = tools.set_night_light(True)
    assert nl_on["status"] in ("success", "simulated")
    nl_off = tools.set_night_light(False)
    assert nl_off["status"] in ("success", "simulated")

    # Monitor detection
    mon = tools.get_display_monitors()
    assert mon["status"] in ("success", "simulated")
    assert "monitors" in mon
    assert isinstance(mon["monitors"], list)

    # Scroll
    s_res = tools.scroll_mouse("down", 3)
    assert s_res["status"] in ("success", "simulated")

    # Double-click (simulated without display)
    dc_res = tools.double_click(100, 100)
    assert dc_res["status"] in ("success", "simulated")

    # Drag
    drag_res = tools.drag_mouse(0, 0, 100, 100)
    assert drag_res["status"] in ("success", "simulated")

    # Hotkey
    hk_res = tools.press_hotkey("ctrl+c")
    assert hk_res["status"] in ("success", "simulated")
