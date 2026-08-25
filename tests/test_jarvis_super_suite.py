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
    assert "youtube.com/results" in yt["url"]
    assert "Interstellar" in yt["url"] or "Hans" in yt["url"]

    sp = tools.play_spotify("Eminem Lose Yourself")
    assert sp["status"] == "success"
    assert "spotify" in sp["url"] or "spotify" in sp.get("message", "").lower()


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

    # 2. YouTube intent
    resp_yt = jarvis.execute_command("youtube-da Hans Zimmer çal")
    assert isinstance(resp_yt, JarvisResponse)
    assert resp_yt.action_taken == "play_youtube"
    assert "youtube" in resp_yt.spoken_text.lower()

    # 3. Spotify intent (routes to zero-login YouTube music)
    resp_sp = jarvis.execute_command("spotify-da eminem oxut")
    assert isinstance(resp_sp, JarvisResponse)
    assert resp_sp.action_taken == "play_spotify"
    assert "youtube" in resp_sp.spoken_text.lower() or "streaming" in resp_sp.spoken_text.lower()

    # 4. Global file search intent
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

