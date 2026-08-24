"""JarvisCore — Autonomous AI Desktop & Voice Operating System Engine.

Combines:
- Spoken Voice Interaction (Text-To-Speech / Speech-To-Text)
- System Hardware Diagnostics (CPU, RAM, Disk, GPU, Battery)
- Native OS Automation (Launch apps, control volume, screenshots)
- Code Intelligence & Terminal Command Execution
- JARVIS Personality Engine ("At your service, sir.")
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vibe_studio.jarvis.system_tools import JarvisSystemTools
from vibe_studio.jarvis.telemetry import SystemSnapshot, SystemTelemetry


@dataclass
class JarvisResponse:
    spoken_text: str
    action_taken: str | None = None
    action_result: dict[str, Any] | None = None
    telemetry: SystemSnapshot | None = None
    execution_time: float = 0.0


class JarvisCore:
    """Core autonomous assistant and voice executor for JARVIS."""

    def __init__(self, workspace_root: str | Path = ".", provider: Any = None, model: str = "llama3.1"):
        self.workspace_root = Path(workspace_root).resolve()
        self.provider = provider
        self.model = model
        self.telemetry = SystemTelemetry()
        self.system_tools = JarvisSystemTools(self.workspace_root)
        self.event_callbacks: list[Callable[[str, dict[str, Any]], None]] = []
        self._tts_lock = threading.Lock()

    def add_event_callback(self, cb: Callable[[str, dict[str, Any]], None]) -> None:
        self.event_callbacks.append(cb)

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        for cb in self.event_callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    def speak(self, text: str) -> None:
        """Speak text aloud using local TTS with graceful fallback."""
        if not text:
            return

        def _worker():
            with self._tts_lock:
                # 1. Try pyttsx3
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty("rate", 175)
                    engine.setProperty("volume", 0.9)
                    engine.say(text)
                    engine.runAndWait()
                    return
                except Exception:
                    pass

                # 2. Try espeak or spd-say on Linux
                try:
                    import subprocess
                    import shutil
                    if shutil.which("spd-say"):
                        subprocess.run(["spd-say", "-r", "10", text], timeout=10)
                        return
                    elif shutil.which("espeak"):
                        subprocess.run(["espeak", "-s", "160", text], timeout=10)
                        return
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def execute_command(self, user_prompt: str) -> JarvisResponse:
        """Process user command or voice prompt and execute appropriate actions."""
        t0 = time.monotonic()
        p = user_prompt.strip().lower()
        self._emit("command_received", {"prompt": user_prompt})

        # 1. System Health / Status
        if any(k in p for k in ["status", "system status", "diagnostics", "hardware", "cpu", "ram", "memory", "battery", "vəziyyət", "resurs"]):
            snap = self.telemetry.get_snapshot()
            spoken = (
                f"System status is nominal, sir. CPU load is at {snap.cpu_percent:.0f}%, "
                f"RAM usage is {snap.ram_used_gb:.1f} gigabytes of {snap.ram_total_gb:.1f} gigabytes. "
                f"All core systems functioning optimally."
            )
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="system_diagnostics",
                action_result=snap.to_dict(),
                telemetry=snap,
                execution_time=time.monotonic() - t0,
            )
            self._emit("command_completed", {"response": spoken, "telemetry": snap.to_dict()})
            return res

        # 2. Open Application / Browser
        m_app = re.search(r"(?:open|launch|start|aç|başlat)\s+([a-zA-Z0-9_\-\.\:\/]+)", p)
        if m_app:
            app_target = m_app.group(1)
            result = self.system_tools.open_app(app_target)
            spoken = f"Opening {app_target} now, sir." if result.get("status") == "success" else f"Could not launch {app_target}."
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="open_app",
                action_result=result,
                execution_time=time.monotonic() - t0,
            )
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 3. Screenshot
        if any(k in p for k in ["screenshot", "screen capture", "ekran şəkli", "şəkil çək"]):
            result = self.system_tools.take_screenshot()
            spoken = "Screenshot captured and saved to workspace, sir." if result.get("status") == "success" else "Failed to capture screenshot."
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="take_screenshot",
                action_result=result,
                execution_time=time.monotonic() - t0,
            )
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 4. Volume Control
        m_vol = re.search(r"(?:volume|səs)\s+(?:to\s+)?(\d+)", p)
        if m_vol:
            val = int(m_vol.group(1))
            result = self.system_tools.set_volume(val)
            spoken = f"Master volume adjusted to {val} percent, sir."
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="set_volume",
                action_result=result,
                execution_time=time.monotonic() - t0,
            )
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 5. Web Search
        m_search = re.search(r"(?:search|google|axtar)\s+(?:for\s+)?(.*)", p)
        if m_search and len(m_search.group(1).strip()) > 2:
            query = m_search.group(1).strip()
            result = self.system_tools.search_web(query)
            spoken = f"Searching the web for '{query}', sir."
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="search_web",
                action_result=result,
                execution_time=time.monotonic() - t0,
            )
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 6. General Conversational / AI Query with JARVIS personality
        spoken = f"Right away, sir. Processing: '{user_prompt}'."
        self.speak(spoken)
        res = JarvisResponse(
            spoken_text=spoken,
            action_taken="ai_consultation",
            action_result={"prompt": user_prompt},
            execution_time=time.monotonic() - t0,
        )
        self._emit("command_completed", {"response": spoken})
        return res
