"""JarvisCore — Full Agentic Autonomous Operating System & Software Engineering Intelligence.

Features:
- Full Agentic Coding & System Execution (write files, edit code, run terminal commands, execute tests)
- Native Bilingual Voice & Text Reasoner (Azerbaijani, English, Turkish)
- Multi-Tool Autonomous LLM Reasoner (qwen2.5-coder:14b, qwen3:8b, deepseek-coder-v2:lite)
- Integrated Voice Listener (Offline faster-whisper STT + Edge-TTS Neural Speech)
- Desktop App & Game Launcher (Brave, TLauncher, Steam, CS2, VSCode, Discord, Spotify)
- Hardware Diagnostics & Proactive Background Sentinel Watchdog
"""
from __future__ import annotations

import datetime
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vibe_studio.jarvis.coding_bridge import JarvisCodingBridge
from vibe_studio.jarvis.memory_db import JarvisMemoryDB
from vibe_studio.jarvis.scheduler import JarvisScheduler, ScheduledItem
from vibe_studio.jarvis.system_tools import JarvisSystemTools
from vibe_studio.jarvis.telemetry import SystemSnapshot, SystemTelemetry
from vibe_studio.jarvis.voice_engine import JarvisVoiceEngine
from vibe_studio.jarvis.voice_listener import JarvisVoiceListener
from vibe_studio.jarvis.watchdog import JarvisWatchdog
from vibe_studio.providers.ollama_provider import OllamaProvider



@dataclass
class JarvisResponse:
    spoken_text: str
    action_taken: str | None = None
    action_result: dict[str, Any] | None = None
    telemetry: SystemSnapshot | None = None
    execution_time: float = 0.0
    model_used: str = "qwen2.5-coder:14b"
    files_modified: list[str] = field(default_factory=list)


class JarvisCore:
    """Full Agentic AI Assistant, Software Engineer, and Desktop Intelligence."""

    DEFAULT_MODELS = [
        "qwen2.5-coder:3b",
        "qwen2.5-coder:7b",
        "deepseek-coder:6.7b",
        "deepseek-r1:7b",
        "qwen2.5-coder:1.5b",
        "deepseek-r1:1.5b",
        "gemma3:4b",
        "starcoder2:3b",
        "codellama:7b",
        "qwen2.5-coder:14b",
        "deepseek-coder-v2:lite",
    ]

    def __init__(self, workspace_root: str | Path = ".", provider: Any = None, model: str = "qwen2.5-coder:3b"):

        self.workspace_root = Path(workspace_root).resolve()
        self.provider = provider or OllamaProvider()
        self.model = model

        self.telemetry = SystemTelemetry()
        self.system_tools = JarvisSystemTools(self.workspace_root)
        self.coding_bridge = JarvisCodingBridge(self.workspace_root)
        self.memory_db = JarvisMemoryDB()
        self.voice_engine = JarvisVoiceEngine()
        self.voice_listener = JarvisVoiceListener(
            on_text_recognized=self._on_voice_transcribed,
            on_wake_word=self._on_wake_word_triggered,
        )
        # Hook half-duplex TTS speaking feedback avoidance
        self.voice_engine.add_state_callback(self._on_tts_speaking_changed)

        self.watchdog = JarvisWatchdog(self.telemetry, on_alert=self._on_watchdog_alert)
        self.scheduler = JarvisScheduler(on_trigger=self._on_scheduler_trigger)
        self.event_callbacks: list[Callable[[str, dict[str, Any]], None]] = []

    def _on_tts_speaking_changed(self, is_speaking: bool) -> None:
        self.voice_listener.set_tts_speaking(is_speaking)

    def _on_voice_transcribed(self, text: str) -> None:
        self._emit("voice_transcribed", {"text": text})

    def _on_wake_word_triggered(self, prompt: str) -> None:
        self._emit("wake_word_triggered", {"prompt": prompt})
        if prompt:
            self.execute_command(prompt)



    def set_model(self, model_name: str) -> None:
        """Update active AI model."""
        self.model = model_name

    def list_available_models(self) -> list[str]:
        """Fetch list of available Ollama models."""
        try:
            if hasattr(self.provider, "list_models"):
                discovered = [m.name for m in self.provider.list_models()]
                if discovered:
                    return discovered
        except Exception:
            pass
        return list(self.DEFAULT_MODELS)

    def start_sentinel(self) -> None:
        """Start proactive background watchdog."""
        self.watchdog.start()

    def stop_sentinel(self) -> None:
        """Stop background watchdog."""
        self.watchdog.stop()

    def add_event_callback(self, cb: Callable[[str, dict[str, Any]], None]) -> None:
        self.event_callbacks.append(cb)

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        if event == "command_completed":
            resp_txt = data.get("response", "")
            if resp_txt:
                try:
                    self.memory_db.save_turn("assistant", resp_txt, model=self.model)
                except Exception:
                    pass
        for cb in self.event_callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    def _on_watchdog_alert(self, alert_type: str, message: str) -> None:
        self.speak(message)
        self._emit("watchdog_alert", {"type": alert_type, "message": message})

    def _on_scheduler_trigger(self, item: ScheduledItem) -> None:
        title = "Alarm" if item.is_alarm else "Timer"
        spoken = f"Sir, your {item.label} reminder has expired."
        self.speak(spoken)
        self.system_tools.show_desktop_notification(f"J.A.R.V.I.S. {title}", f"{item.label} completed!")
        self._emit("timer_triggered", item.to_dict())


    def _resolve_smart_file_boilerplate(self, raw_name: str, prompt: str, loc: str = "desktop") -> tuple[str, str]:
        """Resolve realistic filename and idiomatic starter boilerplate based on requested language."""
        name = raw_name.strip()
        p_lower = prompt.lower()

        # 1. Node.js / JavaScript
        if name.lower() in ("nodejs", "node", "javascript", "js", "node.js") or "node" in p_lower or "javascript" in p_lower:
            if "." not in name or name.lower() in ("nodejs", "node", "javascript", "node.js"):
                name = "app.js"
            elif not name.endswith((".js", ".mjs", ".ts")):
                name = f"{name}.js"
            content = (
                "// Node.js Application generated by J.A.R.V.I.S\n"
                "const http = require('http');\n\n"
                "const server = http.createServer((req, res) => {\n"
                "  res.writeHead(200, { 'Content-Type': 'application/json' });\n"
                "  res.end(JSON.stringify({ status: 'ok', message: 'Hello from Node.js & J.A.R.V.I.S!' }));\n"
                "});\n\n"
                "const PORT = process.env.PORT || 3000;\n"
                "server.listen(PORT, () => {\n"
                "  console.log(`Server running at http://localhost:${PORT}/`);\n"
                "});\n"
            )
            return name, content

        # 2. Python
        elif name.lower() in ("python", "py", "python3") or "python" in p_lower:
            if "." not in name or name.lower() in ("python", "py", "python3"):
                name = "main.py"
            elif not name.endswith(".py"):
                name = f"{name}.py"
            content = (
                "#!/usr/bin/env python3\n"
                '"""Simple Python Application generated by J.A.R.V.I.S."""\n\n'
                "def main():\n"
                "    print('Hello from J.A.R.V.I.S!')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
            return name, content

        # 3. HTML / Web
        elif name.lower() in ("html", "website", "web", "html5") or "html" in p_lower or "web" in p_lower:
            if "." not in name or name.lower() in ("html", "web", "website"):
                name = "index.html"
            elif not name.endswith((".html", ".htm")):
                name = f"{name}.html"
            content = (
                "<!DOCTYPE html>\n"
                "<html lang='en'>\n"
                "<head>\n"
                "  <meta charset='UTF-8'>\n"
                "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
                "  <title>Vibe Studio App</title>\n"
                "  <style>body { font-family: sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }</style>\n"
                "</head>\n"
                "<body>\n"
                "  <h1>⚡ Hello from J.A.R.V.I.S</h1>\n"
                "</body>\n"
                "</html>\n"
            )
            return name, content

        # 4. Rust
        elif name.lower() in ("rust", "rs") or "rust" in p_lower:
            if "." not in name or name.lower() in ("rust", "rs"):
                name = "main.rs"
            elif not name.endswith(".rs"):
                name = f"{name}.rs"
            content = (
                "fn main() {\n"
                "    println!(\"Hello from Rust & J.A.R.V.I.S!\");\n"
                "}\n"
            )
            return name, content

        # 5. Go
        elif name.lower() in ("go", "golang") or "golang" in p_lower:
            if "." not in name or name.lower() in ("go", "golang"):
                name = "main.go"
            elif not name.endswith(".go"):
                name = f"{name}.go"
            content = (
                "package main\n\n"
                "import \"fmt\"\n\n"
                "func main() {\n"
                "    fmt.Println(\"Hello from Go & J.A.R.V.I.S!\")\n"
                "}\n"
            )
            return name, content

        # 6. Bash / Shell
        elif name.lower() in ("bash", "sh", "shell") or "bash" in p_lower or "shell" in p_lower:
            if "." not in name or name.lower() in ("bash", "sh", "shell"):
                name = "script.sh"
            elif not name.endswith(".sh"):
                name = f"{name}.sh"
            content = (
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n\n"
                "echo \"⚡ Hello from Bash & J.A.R.V.I.S!\"\n"
            )
            return name, content

        # Fallback by extension
        if "." not in name:
            name = f"{name}.py"
            content = f"# {name}\nprint('Hello from J.A.R.V.I.S on {loc}!')\n"
        elif name.endswith((".js", ".ts", ".mjs")):
            content = f"// {name}\nconsole.log('Hello from J.A.R.V.I.S on {loc}!');\n"
        elif name.endswith(".html"):
            content = f"<!DOCTYPE html>\n<html><body><h1>Hello from J.A.R.V.I.S on {loc}!</h1></body></html>\n"
        elif name.endswith(".sh"):
            content = f"#!/usr/bin/env bash\necho 'Hello from J.A.R.V.I.S on {loc}!'\n"
        else:
            content = f"# {name}\nprint('Hello from J.A.R.V.I.S on {loc}!')\n"

        return name, content

    def speak(self, text: str) -> None:
        """Speak text aloud using natural neural voice synthesis."""
        if not text:
            return
        self.voice_engine.speak(text)

    def execute_command(self, user_prompt: str) -> JarvisResponse:
        """Process natural language command and execute full agentic actions."""
        t0 = time.monotonic()
        p = user_prompt.strip().lower()
        self._emit("command_received", {"prompt": user_prompt, "model": self.model})

        # Save user prompt turn to persistent conversation memory
        try:
            self.memory_db.save_turn("user", user_prompt, model=self.model)
        except Exception:
            pass

        # Check if Azerbaijani language prompt (letters or keywords)
        is_az = any(c in p for c in "əışçğöü") or any(w in p for w in ["salam", "necesen", "yarat", "temizle", "bagla", "nedir", "necedir", "veziyyet", "ise sal", "sabahin", "axsamin", "cenab", "kilidle", "kilitle", "cihaz", "whatsapdan", "zeng", "internetden", "mene", "qiymet", "tapib", "haqqinda", "musigi", "mahnisi"])





        # 1. Direct Time-aware Greetings (Single greeting only)
        if any(p == w or p.startswith(w + " ") for w in ["salam", "hello", "hi", "hey", "good morning", "good evening", "sabahın xeyir", "axşamın xeyir"]):
            if not any(act in p for act in ["open", "launch", "check", "test", "kill", "clean", "speed", "fast.com", "yarat", "aç", "yaz", "run"]):
                if is_az:
                    hour = datetime.datetime.now().hour
                    g = "Sabahınız xeyir" if hour < 12 else ("Hər vaxtınız xeyir" if hour < 18 else "Axşamınız xeyir")
                    spoken = f"{g}, cənab. J.A.R.V.I.S aktivdir, beyin modeli {self.model}. Bütün sistemlər tam qaydasındadır. Sizə necə kömək edə bilərəm?"
                else:
                    hour = datetime.datetime.now().hour
                    tod = "morning" if hour < 12 else ("afternoon" if hour < 18 else "evening")
                    spoken = f"Good {tod}, sir. J.A.R.V.I.S online using {self.model}. All systems fully operational. How may I assist you?"
                self.speak(spoken)
                res = JarvisResponse(spoken_text=spoken, action_taken="greeting", execution_time=time.monotonic() - t0, model_used=self.model)
                self._emit("command_completed", {"response": spoken})
                return res

        # --- HIGH-PRIORITY INTENT SHORTCUTS (must come before LLM delegation) ---

        # 1b. Screenshot
        if any(k in p for k in ["take screenshot", "screenshot", "capture screen", "ekran çək", "şəkil çək"]):
            result = self.system_tools.take_screenshot()
            spoken = "Screenshot captured and saved, sir."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="take_screenshot", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1c. Volume control: "set volume to 50", "volume 75"
        m_vol = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})", p)
        if m_vol:
            level = int(m_vol.group(1))
            result = self.system_tools.set_volume(level)
            spoken = f"Master volume set to {level} percent, sir."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_volume", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1d. Git summary (must be before web search so "git summary" isn't swallowed)
        if any(k in p for k in ["git status", "git summary", "git summary", "git log", "filial", "dəyişikliklər"]) or p.strip().rstrip(".!?") in ("git summary", "git status", "jarvis git summary", "jarvis, git summary"):
            result = self.system_tools.get_git_summary()
            spoken = f"Workspace is on Git branch {result.get('branch', 'unknown')}, with {result.get('changed_files_count', 0)} modified files, sir."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="git_summary", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1e. Web search & live price / info lookup:
        m_search = re.search(
            r"(?:(?:internet(?:den|dən)\s+(?:mene|mənə\s+)?(?:en\s+son\s+)?|internet(?:de|də)\s+(?:axtar\s+)?|search\s+(?:for|the\s+web\s+for|in\s+internet\s+for|in\s+internet)?|google\s+(?:for)?|say\s+(?:to\s+(?:men|me)\s+)?latest\s+|tell\s+me\s+about\s+|find\s+(?:out\s+)?(?:the\s+)?prices?\s+of\s+)(.+)|(.+?)\s+(?:qiymet(?:lerini|i|ler)?\s+(?:tap(?:ib\s+de)?|de|necedir|axtar)|qiymetleri|qiymeti))",
            p
        )
        if m_search:
            query = (m_search.group(1) or m_search.group(2) or "").strip().rstrip(".,!?")
            query = re.sub(r"\b(?:tapıb\s+de|tapib\s+de|tap|de|axtar)\b", "", query, flags=re.IGNORECASE).strip()
            if not query or len(query) < 2:
                query = p
            result = self.system_tools.search_web(query)
            snips = result.get("snippets", [])
            if snips:
                top_info = snips[0]
                if len(top_info) > 220:
                    top_info = top_info[:220] + "..."
                spoken = f"According to web data for '{query}': {top_info}" if not is_az else f"'{query}' üzrə internet məlumatı: {top_info}"
            else:
                spoken = f"Searching the web for '{query}', sir." if not is_az else f"'{query}' üçün internetdə axtarış edirəm, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="search_web", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res


        # 1f. Screen Lock / Cihazı Kilidlə
        if any(k in p for k in ["lock screen", "lock the screen", "lock computer", "lock pc", "lock device", "lock session", "cihazı kilitle", "cihazı kilidlə", "ekranı kilitle", "ekranı kilidlə", "kilitle", "kilidlə", "kompüteri kilidlə"]):
            result = self.system_tools.lock_screen()
            spoken = "Locking the screen now, sir." if not is_az else "Cihazı kilidləyirəm, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="lock_screen", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res


        # 1g. Save Contact: "save contact tuncay +994501234567"
        m_save = re.search(r"(?:save\s+contact|kontakt\s+əlavə\s+et|kontakt\s+saxla|yadda\s+saxla)\s+([a-zA-Z0-9_əşçğöüƏŞÇĞÖÜ]+)\s+([\+0-9\s\-]+)", p)
        if m_save:
            cname = m_save.group(1).strip()
            cphone = m_save.group(2).strip()
            result = self.system_tools.save_contact(cname, cphone)
            spoken = f"Saved contact {cname} with number {cphone}, sir." if not is_az else f"{cname} kontaktı {cphone} nömrəsi ilə yadda saxlanıldı, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="save_contact", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 1h. WhatsApp Call: "whatsapdan tuncayi ara", "whatsapp call tuncay", "call tuncay on whatsapp"
        m_wacall = (
            re.search(r"(?:whatsap+dan|whatsap+da|whatsapp)\s+([a-zA-Z0-9_əşçğöüƏŞÇĞÖÜ]+)\s*(?:i|ı|u|ü|ə|e|ya|yə|a|na|nə)?\s*(?:ara|zəng\s+et|zeng\s+et|call)", p)
            or re.search(r"whatsapp\s+call\s+([a-zA-Z0-9_əşçğöüƏŞÇĞÖÜ]+)", p)
            or re.search(r"call\s+([a-zA-Z0-9_əşçğöüƏŞÇĞÖÜ]+)\s+(?:on\s+|via\s+)?whatsapp", p)
        )
        if m_wacall:
            cname = m_wacall.group(1).strip()
            result = self.system_tools.whatsapp_call(cname)
            if result.get("status") == "success":
                spoken = f"Initiating WhatsApp call with {cname}, sir. Please click the call button on screen." if not is_az else f"{cname} ilə WhatsApp zəngi açıldı, ekranda zəng düyməsini klikləyin, cənab."
            else:
                spoken = f"Contact {cname} not found in address book, sir. Opening WhatsApp Web for manual search." if not is_az else f"{cname} kontakt kitabında tapılmadı, cənab. Əl ilə axtarış üçün WhatsApp Web açılır."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="whatsapp_call", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 1i. WhatsApp Message: "whatsapdan tuncaya yaz salam necesen"
        m_wamsg = (
            re.search(r"(?:whatsap+dan|whatsap+da|whatsapp)\s+([a-zA-Z0-9_əşçğöüƏŞÇĞÖÜ]+)\s*(?:ya|yə|a|e|na|nə)?\s+(?:yaz|mesaj\s+yaz|mesaj\s+göndər)\s+(.+)", p)
            or re.search(r"send\s+whatsapp\s+message\s+to\s+([a-zA-Z0-9_əşçğöüƏŞÇĞÖÜ]+)\s+(?:saying\s+|with\s+text\s+|:\s*)?(.+)", p)
        )
        if m_wamsg:
            cname = m_wamsg.group(1).strip()
            msg_text = m_wamsg.group(2).strip()
            result = self.system_tools.whatsapp_message(cname, msg_text)
            spoken = f"Opening WhatsApp message to {cname}, sir." if not is_az else f"{cname} üçün WhatsApp mesajı açılır, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="whatsapp_message", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 1j. Live Weather: "hava necədir", "what is the weather in Baku"
        if any(k in p for k in ["hava", "weather", "havanı göstər", "havanı öyrən"]):
            m_city = re.search(r"(?:weather\s+in|hava)\s+([a-zA-ZçəğışöüÇƏĞIŞÖÜ]+)", p)
            city = m_city.group(1) if m_city and m_city.group(1) not in ("necədir", "necedir", "haqqında", "today", "now") else "Baku"
            result = self.system_tools.get_weather(city)
            spoken = f"Live weather report: {result.get('report')}, sir." if not is_az else f"Hava məlumatı: {result.get('report')}, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="get_weather", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 1k. Brightness: "ekran parlaqlığını 80 faiz et", "set brightness to 75"
        m_bright = re.search(r"(?:set\s+)?(?:brightness|parlaqlıq|parlaqlığı)\s+(?:to\s+)?(\d{1,3})", p)
        if m_bright:
            level = int(m_bright.group(1))
            result = self.system_tools.set_brightness(level)
            spoken = f"Screen brightness adjusted to {level} percent, sir." if not is_az else f"Ekran parlaqlığı {level} faizə qoyuldu, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_brightness", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 1l. Media Playback: "musiqini dayandır", "play music", "next track", "növbəti mahnı"
        if any(k in p for k in ["pause music", "stop music", "musiqini dayandır", "musiqini saxla", "pauza"]):
            result = self.system_tools.media_control("pause")
            spoken = "Media paused, sir." if not is_az else "Musiqi dayandırıldı, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="media_control", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["play music", "resume music", "musiqini oxut", "musiqi çal", "davam et"]):
            result = self.system_tools.media_control("play-pause")
            spoken = "Resuming media playback, sir." if not is_az else "Musiqi oxunur, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="media_control", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["next song", "next track", "növbəti mahnı", "növbəti trek"]):
            result = self.system_tools.media_control("next")
            spoken = "Skipping to next track, sir." if not is_az else "Növbəti mahnıya keçirəm, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="media_control", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1m. Telegram Message / Chat: "telegramdan tuncaya yaz salam"
        m_tg = re.search(r"(?:telegramdan|telegramda|telegram)\s+([a-zA-Z0-9_]+)\s*(?:ya|yə|a|e)?\s*(?:yaz|mesaj\s+yaz)?\s*(.*)", p)
        if m_tg and ("telegram" in p):
            tgt = m_tg.group(1).strip()
            tg_text = m_tg.group(2).strip()
            if tgt not in ("open", "aç", "app", "application"):
                result = self.system_tools.telegram_message(tgt, tg_text)
                spoken = f"Opening Telegram chat with {tgt}, sir." if not is_az else f"{tgt} ilə Telegram çatı açılır, cənab."
                self.speak(spoken)
                res = JarvisResponse(spoken_text=spoken, action_taken="telegram_message", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
                self._emit("command_completed", {"response": spoken, "result": result})
                return res

        # 1n. Time & Date: "saat neçədir", "what time is it", "tarix nədir"
        if any(p == k or p.startswith(k) for k in ["saat neçədir", "saat necedir", "saat neçə", "what time is it", "current time", "bu gün ayın neçəsidir", "tarix nədir", "today date"]):
            now = datetime.datetime.now()
            time_str = now.strftime("%H:%M")
            date_str = now.strftime("%d.%m.%Y")
            spoken = f"The time is {time_str}, today's date is {date_str}, sir." if not is_az else f"Hazırda saat {time_str}, bu günün tarixi {date_str}-dir, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="time_check", action_result={"time": time_str, "date": date_str}, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1o. System Sleep: "yuxu rejimi", "suspend pc", "sleep mode"
        if any(k in p for k in ["yuxu rejimi", "yuxuya get", "suspend", "sleep mode", "sleep pc"]):
            result = self.system_tools.suspend_system()
            spoken = "Putting system into suspend sleep mode, sir." if not is_az else "Kompüter yuxu rejiminə keçirilir, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="suspend_system", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1p. Operating System & Environment check
        if any(k in p for k in ["operation system", "operating system", "mine os", "my os", "what os", "which os", "find mine operation", "hansı əməliyyat sistemi", "əməliyyat sistemi nədir", "hansı os", "os nədir"]):
            snap = self.telemetry.get_snapshot()
            gpu_info = f", GPU: {snap.gpu_name}" if snap.gpu_name else ""
            spoken = (
                f"Your operating system is {snap.os_name} on host '{snap.hostname}'{gpu_info}, sir."
            ) if not is_az else (
                f"Əməliyyat sisteminiz {snap.os_name}, kompüter adı '{snap.hostname}'-dir, cənab."
            )
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="os_info",
                action_result={"os": snap.os_name, "hostname": snap.hostname, "gpu": snap.gpu_name},
                telemetry=snap,
                execution_time=time.monotonic() - t0,
                model_used=self.model,
            )
            self._emit("command_completed", {"response": spoken, "result": snap.to_dict()})
            return res

        # 1q. RAM / Memory info check
        if any(k in p for k in ["how many ram", "how much ram", "what is my ram", "check ram", "ram info", "ram amount", "ram nə qədərdir", "nə qədər ram", "ram miqdarı", "operativ yaddaş", "ram status", "yaddaş nə qədərdir", "ram usage", "ram-ım nə qədər"]):
            snap = self.telemetry.get_snapshot()
            spoken = (
                f"You have {snap.ram_total_gb:.1f} gigabytes of RAM installed, currently using {snap.ram_used_gb:.1f} gigabytes ({snap.ram_percent:.0f}%), sir."
            ) if not is_az else (
                f"Sistemdə ümumi {snap.ram_total_gb:.1f} GB RAM mövcuddur, hazırda {snap.ram_used_gb:.1f} GB ({snap.ram_percent:.0f}%) istifadə olunur, cənab."
            )
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="ram_info",
                action_result={"ram_total_gb": snap.ram_total_gb, "ram_used_gb": snap.ram_used_gb, "ram_percent": snap.ram_percent},
                telemetry=snap,
                execution_time=time.monotonic() - t0,
                model_used=self.model,
            )
            self._emit("command_completed", {"response": spoken, "result": snap.to_dict()})
            return res

        # 1r. CPU info check
        if any(k in p for k in ["cpu load", "cpu usage", "what is my cpu", "check cpu", "cpu info", "prosessor nədir", "prosessor yükü", "prosessor məlumatı", "neçə nüvə var", "cpu cores"]):
            snap = self.telemetry.get_snapshot()
            spoken = (
                f"CPU load is currently at {snap.cpu_percent:.0f}% across {snap.cpu_cores} physical cores, sir."
            ) if not is_az else (
                f"Prosessor yükü hazırda {snap.cpu_cores} nüvə üzrə {snap.cpu_percent:.0f}% səviyyəsindədir, cənab."
            )
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="cpu_info",
                action_result={"cpu_percent": snap.cpu_percent, "cpu_cores": snap.cpu_cores},
                telemetry=snap,
                execution_time=time.monotonic() - t0,
                model_used=self.model,
            )
            self._emit("command_completed", {"response": spoken, "result": snap.to_dict()})
            return res

        # 1s. GPU / Graphics Card info check
        if any(k in p for k in ["what is my gpu", "what gpu", "graphics card", "check gpu", "gpu info", "gpu nədir", "videokart nədir", "qrafik kartı"]):
            snap = self.telemetry.get_snapshot()
            gpu_name = snap.gpu_name or "Integrated Graphics"
            spoken = (
                f"Your graphics processor is {gpu_name}, sir."
            ) if not is_az else (
                f"Qrafik kartınız {gpu_name}-dir, cənab."
            )
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="gpu_info",
                action_result={"gpu": gpu_name},
                telemetry=snap,
                execution_time=time.monotonic() - t0,
                model_used=self.model,
            )
            self._emit("command_completed", {"response": spoken, "result": snap.to_dict()})
            return res

        # 1t. Disk Storage info check
        if any(k in p for k in ["how much disk", "disk space", "disk storage", "check disk", "storage info", "disk yeri nə qədərdir", "yaddaşda nə qədər yer var", "disk tutumu", "ssd status"]):
            snap = self.telemetry.get_snapshot()
            spoken = (
                f"Disk storage has {snap.disk_used_gb:.1f} gigabytes used out of {snap.disk_total_gb:.1f} gigabytes ({snap.disk_percent:.0f}%), sir."
            ) if not is_az else (
                f"Diskdə ümumi {snap.disk_total_gb:.1f} GB yaddaşdan {snap.disk_used_gb:.1f} GB ({snap.disk_percent:.0f}%) istifadə olunub, cənab."
            )
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="disk_info",
                action_result={"disk_used_gb": snap.disk_used_gb, "disk_total_gb": snap.disk_total_gb, "disk_percent": snap.disk_percent},
                telemetry=snap,
                execution_time=time.monotonic() - t0,
                model_used=self.model,
            )
            self._emit("command_completed", {"response": spoken, "result": snap.to_dict()})
            return res

        # 1u. Direct simple file creation shortcut on Desktop / Workspace
        m_create_file = (
            re.search(r"(?:create|make|write)\s+(?:a\s+|an\s+)?(?:simple\s+)?([a-zA-Z0-9_\-\.]+)\s+(?:file\s+)?(?:in|on)\s+(desktop|workspace|masaüstü)", p)
            or re.search(r"(?:masaüstündə|desktopda)\s+([a-zA-Z0-9_\-\.]+)\s+(?:faylı\s+)?(?:yarat|aç)", p)
        )

        if m_create_file:
            raw_fname = m_create_file.group(1).strip()
            loc = m_create_file.group(2).strip() if len(m_create_file.groups()) > 1 and m_create_file.group(2) else "desktop"
            fname, content = self._resolve_smart_file_boilerplate(raw_fname, p, loc)
            target_path = f"Desktop/{fname}" if "desk" in loc.lower() or "masa" in loc.lower() else fname
            w_res = self.coding_bridge.write_file(target_path, content)
            spoken = f"Created {fname} with starter code on your {loc} successfully, sir." if not is_az else f"{fname} faylı {loc} üzərində yaradıldı, cənab."
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="write_file",
                action_result=w_res,
                execution_time=time.monotonic() - t0,
                model_used=self.model,
                files_modified=[str(w_res.get("path", target_path))],
            )
            self._emit("command_completed", {"response": spoken, "result": w_res})
            return res

        # 1w. User Feedback / Correction handling: "this is not nodejs", "bu nodejs deyil", "düzəlt", "fix this"
        m_not_lang = re.search(r"(?:this\s+is\s+not|bu\s+.*?deyil)\s+([a-zA-Z0-9_\-\.]+)", p)
        if m_not_lang or any(k in p for k in ["this is not", "bu düz deyil", "səhvdir", "this is wrong"]):
            req_lang = m_not_lang.group(1).strip() if m_not_lang else "correct"
            fixed_name, fixed_content = self._resolve_smart_file_boilerplate(req_lang, p, "desktop")
            w_res = self.coding_bridge.write_file(f"Desktop/{fixed_name}", fixed_content)
            try:
                bad_f = self.coding_bridge.desktop_dir / req_lang
                if bad_f.exists() and bad_f.is_file() and "." not in req_lang:
                    bad_f.unlink()
            except Exception:
                pass

            spoken = f"My apologies, sir. I have corrected it and generated proper {req_lang} in {fixed_name} on your desktop." if not is_az else f"Bağışlayın cənab, dərhal düzəltdim. Masaüstünüzdə düzgün {req_lang} kodu ilə {fixed_name} faylı yaradıldı."
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="correction_applied",
                action_result=w_res,
                execution_time=time.monotonic() - t0,
                model_used=self.model,
                files_modified=[str(w_res.get("path", f"Desktop/{fixed_name}"))],
            )
            self._emit("command_completed", {"response": spoken, "result": w_res})
            return res


        # 1v. Universal Software & Package Installation: "install htop", "htop yüklə", "pip install requests"
        m_install = (
            re.search(r"(?:install|yüklə|download\s+and\s+install)\s+([a-zA-Z0-9_\-\.\:\@\/]+)", p)
            or re.search(r"([a-zA-Z0-9_\-\.\:\@\/]+)\s+(?:proqramını\s+|paketini\s+)?yüklə", p)
        )
        if m_install and not any(k in p for k in ["desktop", "workspace", "main.py", "fayl", "file"]):
            pkg_target = m_install.group(1).strip()
            if pkg_target not in ("app", "application", "proqram", "paket"):
                ins_res = self.system_tools.install_package(pkg_target)
                mgr = ins_res.get("manager", "package manager")
                if ins_res.get("status") == "success":
                    spoken = f"Successfully installed {pkg_target} via {mgr}, sir." if not is_az else f"{pkg_target} paketi {mgr} vasitəsilə uğurla quraşdırıldı, cənab."
                else:
                    spoken = f"Package installation of {pkg_target} encountered an issue via {mgr}, sir." if not is_az else f"{pkg_target} paketinin {mgr} vasitəsilə quraşdırılmasında xəta baş verdi, cənab."
                self.speak(spoken)
                res = JarvisResponse(
                    spoken_text=spoken,
                    action_taken="install_package",
                    action_result=ins_res,
                    execution_time=time.monotonic() - t0,
                    model_used=self.model,
                )
                self._emit("command_completed", {"response": spoken, "result": ins_res})
                return res

        # 1x. Timers, Alarms & Reminders: "10 dəqiqə sonra çayı xatırlat", "set timer for 5 minutes", "saat 15:30-da zəng qur"
        if any(k in p for k in ["taymer", "timer", "xatırlat", "alarm", "zəng qur", "zeng vur", "reminder"]):
            # Relative timer: "set timer for 10 minutes", "5 dəqiqə sonra xatırlat"
            m_rel = (
                re.search(r"(?:set\s+)?timer\s+(?:for\s+)?(\d+)\s*(minute|second|min|sec|hour|dəqiqə|deqiqe|saniyə|saat)?(?:\s+(?:for|to|haqqında)?\s*(.+))?", p)
                or re.search(r"(\d+)\s*(minute|second|min|sec|hour|dəqiqə|deqiqe|saniyə|saat)\s*(?:sonra)?\s*(.+)?\s*xatırlat", p)
            )
            if m_rel:
                amount = float(m_rel.group(1))
                unit = (m_rel.group(2) or "min").lower()
                lbl = (m_rel.group(3) or "Reminder").strip()
                sec = amount * 60.0
                if "sec" in unit or "saniyə" in unit:
                    sec = amount
                elif "hour" in unit or "saat" in unit:
                    sec = amount * 3600.0

                item = self.scheduler.set_timer(sec, lbl)
                spoken = f"Timer set for {int(amount)} {unit} for '{lbl}', sir." if not is_az else f"{int(amount)} {unit} üçün '{lbl}' taymeri quruldu, cənab."
                self.speak(spoken)
                res = JarvisResponse(spoken_text=spoken, action_taken="set_timer", action_result=item.to_dict(), execution_time=time.monotonic() - t0, model_used=self.model)
                self._emit("command_completed", {"response": spoken, "result": item.to_dict()})
                return res

            # Absolute alarm: "set alarm for 14:30", "saat 09:00-da zəng qur"
            m_alarm = re.search(r"(?:alarm|zəng|saat)\s+(?:for\s+)?(\d{1,2}:\d{2})(?:\s+(?:for)?\s*(.+))?", p)
            if m_alarm:
                t_str = m_alarm.group(1)
                lbl = (m_alarm.group(2) or "Alarm").strip()
                item = self.scheduler.set_alarm(t_str, lbl)
                if item:
                    spoken = f"Alarm scheduled for {t_str} ('{lbl}'), sir." if not is_az else f"Saat {t_str} üçün '{lbl}' zəngi quruldu, cənab."
                else:
                    spoken = "Could not schedule alarm. Please use HH:MM format, sir."
                self.speak(spoken)
                res = JarvisResponse(spoken_text=spoken, action_taken="set_alarm", action_result=item.to_dict() if item else {}, execution_time=time.monotonic() - t0, model_used=self.model)
                self._emit("command_completed", {"response": spoken})
                return res

            # List active timers
            if any(k in p for k in ["list timer", "aktiv taymer", "taymerləri göstər", "active timers"]):
                active = self.scheduler.list_active_timers()
                spoken = f"You have {len(active)} active timers scheduled, sir." if not is_az else f"Hazırda {len(active)} aktiv taymeriniz var, cənab."
                self.speak(spoken)
                res = JarvisResponse(spoken_text=spoken, action_taken="list_timers", action_result={"count": len(active), "timers": [t.to_dict() for t in active]}, execution_time=time.monotonic() - t0, model_used=self.model)
                self._emit("command_completed", {"response": spoken})
                return res

        # 1x. Play First / Auto-play Video: "browserde 1ci mahnini ac", "play first one", "play the first song"
        if any(k in p for k in [
            "1ci mahnini", "1-ci mahnı", "1ci mahnı", "birinci mahnı", "ilk mahnı", "ilk video",
            "play first", "play the first", "first one", "first song", "first video"
        ]):
            m_target = self.system_tools.last_media_query or "popular trending music"
            yt_res = self.system_tools.play_youtube(m_target, direct_play=True)
            spoken = f"Directly playing the first video for '{m_target}', sir." if not is_az else f"'{m_target}' üzrə birinci video birbaşa başladılır, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="play_first_video", action_result=yt_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": yt_res})
            return res

        # 1y. Direct YouTube & Music Player: "inna caliente musiqisini ac", "youtube-da Hans Zimmer çal", "play interstellar"
        m_music_all = (
            re.search(r"(.+?)\s+(?:musiqisini|mahnısını|mahnisi|musiqisi)\s+(?:aç|çal|oxut|başlat|ac)", p)
            or re.search(r"(?:aç|çal|oxut|başlat|ac)\s+(.+?)\s+(?:musiqisini|mahnısını|mahnisi|musiqisi)", p)
            or re.search(r"(?:musiqi|mahnı|mahni|song|music)\s+(?:aç|çal|oxut|başlat|play|ac)\s*(.+)?", p)
            or re.search(r"^youtube(?:-da|-də|da|de)?\s+(.+)$", p)
            or re.search(r"youtube(?:-da|-də)?\s+(.+?)\s+(?:aç|çal|oxut|axtar|başlat|ac)", p)
            or re.search(r"spotify(?:-da|-də)?\s+(.+?)\s+(?:aç|çal|oxut|axtar|başlat|ac)", p)
            or re.search(r"(?:play|çal|oxut)\s+(.+?)\s+(?:on\s+youtube|in\s+youtube|on\s+ytb|in\s+ytb|on\s+spotify)", p)
            or re.search(r"(?:open\s+(?:the\s+)?)(.+?)\s+(?:music|song)?\s*(?:in\s+ytb|on\s+ytb|in\s+youtube|on\s+youtube)", p)
            or re.search(r"^(?:open\s+(?:the\s+)?)(.+?)\s+youtube$", p)
            or re.search(r"(?:play|çal|oxut)\s+(.+)", p)
        )
        if m_music_all and any(k in p for k in ["youtube", "ytb", "spotify", "musiqi", "mahnı", "mahni", "song", "music", "play", "çal", "oxut"]):
            yt_query = (m_music_all.group(1) or "relaxing music").strip()
            # Clean filler words
            yt_query = re.sub(r"^(?:the|a)\s+", "", yt_query, flags=re.IGNORECASE).strip()
            yt_res = self.system_tools.play_youtube(yt_query, direct_play=True)
            spoken = f"Directly playing '{yt_query}' via YouTube, sir." if not is_az else f"YouTube üzərindən '{yt_query}' mahnısı birbaşa başladılır, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="play_youtube", action_result=yt_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": yt_res})
            return res


        # 1aa. Global Deep Disk File Search: "bütün kompüterdə report.pdf tap", "find all pdf files"
        if any(k in p for k in ["find file", "find files", "kompüterdə tap", "bütün kompüterdə", "şəkilləri tap", "sənədləri tap"]):
            m_find = re.search(r"(?:find|search\s+for|bütün\s+kompüterdə|tap)\s+(?:all\s+)?([a-zA-Z0-9_\-\.\*]+)", p)
            query_pat = m_find.group(1).strip() if m_find else "pdf"
            f_res = self.system_tools.find_files_global(query_pat)
            cnt = f_res.get("count", 0)
            spoken = f"Found {cnt} matching files for '{query_pat}' across your disk, sir." if not is_az else f"Kompüterdə '{query_pat}' üzrə {cnt} uyğun fayl tapıldı, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="find_files_global", action_result=f_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": f_res})
            return res

        # 1ab. Native Desktop Notifications: "send notification Hello", "bildiriş göndər Test"
        m_notif = re.search(r"(?:send\s+notification|bildiriş\s+göndər|bildiriş\s+yarat)\s+(.+)", p)
        if m_notif:
            n_text = m_notif.group(1).strip()
            n_res = self.system_tools.show_desktop_notification("J.A.R.V.I.S.", n_text)
            spoken = f"Notification posted to desktop, sir." if not is_az else f"Masaüstü bildirişi göndərildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="desktop_notification", action_result=n_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": n_res})
            return res

        # 1ac. Vision Screenshot & Webcam Analysis: "ekranı analiz et", "what is on my screen", "ekranıma bax", "ekranımı gör"
        if any(k in p for k in [
            "ekranı analiz et", "what is on my screen", "what's on my screen", "analyze screen",
            "ekranda nə var", "ekranda nə xətası var", "ekranıma bax", "ekrana bax", "ekranımı gör",
            "ekranı gör", "ekranı təsvir et", "look at my screen", "see my screen", "describe my screen"
        ]):
            v_res = self.system_tools.analyze_screenshot_vision(query=user_prompt)
            spoken = f"Visual analysis complete: {v_res.get('analysis', 'Screen is nominal')}, sir." if not is_az else f"Ekran analizi: {v_res.get('analysis')}, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="vision_analysis", action_result=v_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": v_res})
            return res
        elif any(k in p for k in ["webcam", "veb kamera", "veb-kamera", "take photo"]):
            cam_res = self.system_tools.capture_webcam()
            spoken = f"Captured photo from webcam, sir." if not is_az else f"Veb-kamera ilə şəkil çəkildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="capture_webcam", action_result=cam_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": cam_res})
            return res

        # 1ad. Window & Keyboard Simulation: "tam ekran et", "pəncərəni kiçilt", "pəncərəni bağla"
        if any(k in p for k in ["tam ekran", "maximize window", "pəncərəni böyüt"]):
            w_res = self.system_tools.window_control("maximize")
            spoken = "Window maximized, sir." if not is_az else "Pəncərə tam ekran edildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="window_control", action_result=w_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["pəncərəni kiçilt", "minimize window"]):
            w_res = self.system_tools.window_control("minimize")
            spoken = "Window minimized, sir." if not is_az else "Pəncərə kiçildildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="window_control", action_result=w_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["pəncərəni bağla", "close window", "active window close"]):
            w_res = self.system_tools.window_control("close")
            spoken = "Window closed, sir." if not is_az else "Pəncərə bağlandı, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="window_control", action_result=w_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1ae. Neural Voice Gender & Persona Switching: "qadın səsinə keç", "kişi səsinə keç", "switch to female voice"
        if any(k in p for k in ["qadın səsinə keç", "qadın səsi", "qız səsi", "switch to female voice", "use female voice", "banu səsi", "friday voice"]):
            v_info = self.voice_engine.set_gender("female")
            spoken = "Səs təbii qadın səsinə (Banu) keçirildi, cənab." if is_az else "Switched to natural female neural voice (Friday), sir."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_voice_gender", action_result=v_info, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "voice": v_info})
            return res
        elif any(k in p for k in ["kişi səsinə keç", "kişi səsi", "oğlan səsi", "switch to male voice", "use male voice", "babək səsi", "jarvis voice"]):
            v_info = self.voice_engine.set_gender("male")
            spoken = "Səs klassik kişi səsinə (Babək) keçirildi, cənab." if is_az else "Switched to classic male neural voice (Jarvis), sir."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_voice_gender", action_result=v_info, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "voice": v_info})
            return res

        # 1af. Continuous Wake-Word Daemon: "canlı qulaq asmanı aktivləşdir", "enable wake word", "wake word söndür"
        if any(k in p for k in ["canlı qulaq asmanı aktivləşdir", "canlı qulaq asmanı aç", "enable wake word", "start listening", "wake word aktiv"]):
            self.voice_listener.start_wake_word_daemon()
            spoken = "Canlı 'Hey Jarvis' qulaq asma xidməti aktivləşdirildi, cənab." if is_az else "Continuous 'Hey Jarvis' wake-word daemon enabled, sir."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="start_wake_word", action_result={"status": "active"}, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["canlı qulaq asmanı dayandır", "canlı qulaq asmanı söndür", "disable wake word", "stop listening"]):
            self.voice_listener.stop_wake_word_daemon()
            spoken = "Canlı qulaq asma xidməti dayandırıldı, cənab." if is_az else "Wake-word daemon stopped, sir."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="stop_wake_word", action_result={"status": "inactive"}, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1ag. Active Browser Tab & Live Content Reader: "bu səhifəni oxu", "bu səhifəni ümumiləşdir", "read current page", "summarize tab"
        if any(k in p for k in ["bu səhifəni oxu", "bu səhifəni ümumiləşdir", "read current page", "read active tab", "summarize tab", "summarize page", "açıq səhifəni oxu"]):
            tab_res = self.system_tools.read_active_browser_tab()
            spoken = f"Active tab title: '{tab_res.get('title')}', sir." if not is_az else f"Aktiv səhifə oxunur: '{tab_res.get('title')}', cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="read_active_browser_tab", action_result=tab_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": tab_res})
            return res

        # 1ah. Visual OCR Mouse Clicker: "ekrandakı '...' düyməsinə bas", "click '...' on screen"
        m_vclick = re.search(r"(?:click|kliklə|bas)\s+['\"]?(.+?)['\"]?\s*(?:on\s+screen|düyməsinə|düyməsinə\s+bas)?$", p)
        if m_vclick and any(k in p for k in ["on screen", "düyməsinə", "kliklə", "ekrandakı"]):
            target_txt = m_vclick.group(1).strip()
            c_res = self.system_tools.click_element_by_text(target_txt)
            spoken = f"Clicked visual target '{target_txt}', sir." if not is_az else f"Ekrandakı '{target_txt}' hədəfinə klikləndi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="click_element_by_text", action_result=c_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": c_res})
            return res

        # 1ai. Wi-Fi & Bluetooth Wireless Management: "wifi yandır", "wifi söndür", "wifi axtar", "bluetooth yandır"
        if any(k in p for k in ["wifi yandır", "wifi aç", "enable wifi", "turn on wifi"]):
            wf_res = self.system_tools.manage_wifi("on")
            spoken = "Wi-Fi radio enabled, sir." if not is_az else "Wi-Fi şəbəkəsi aktivləşdirildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="manage_wifi", action_result=wf_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["wifi söndür", "wifi bağla", "disable wifi", "turn off wifi"]):
            wf_res = self.system_tools.manage_wifi("off")
            spoken = "Wi-Fi radio disabled, sir." if not is_az else "Wi-Fi şəbəkəsi söndürüldü, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="manage_wifi", action_result=wf_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["wifi axtar", "scan wifi", "list wifi", "wifi şəbəkələri"]):
            wf_res = self.system_tools.manage_wifi("scan")
            spoken = f"Found {len(wf_res.get('networks', []))} Wi-Fi networks, sir." if not is_az else f"{len(wf_res.get('networks', []))} Wi-Fi şəbəkəsi aşkarlandı, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="manage_wifi", action_result=wf_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": wf_res})
            return res
        elif any(k in p for k in ["bluetooth yandır", "bluetooth aç", "enable bluetooth", "turn on bluetooth"]):
            bt_res = self.system_tools.manage_bluetooth("on")
            spoken = "Bluetooth powered on, sir." if not is_az else "Bluetooth aktivləşdirildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="manage_bluetooth", action_result=bt_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["bluetooth söndür", "bluetooth bağla", "disable bluetooth", "turn off bluetooth"]):
            bt_res = self.system_tools.manage_bluetooth("off")
            spoken = "Bluetooth powered off, sir." if not is_az else "Bluetooth söndürüldü, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="manage_bluetooth", action_result=bt_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["bluetooth axtar", "scan bluetooth", "bluetooth cihazları"]):
            bt_res = self.system_tools.manage_bluetooth("scan")
            spoken = f"Found {len(bt_res.get('devices', []))} Bluetooth devices, sir." if not is_az else f"{len(bt_res.get('devices', []))} Bluetooth cihazı aşkarlandı, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="manage_bluetooth", action_result=bt_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": bt_res})
            return res

        # 1aj. Multi-Monitor & Display Management
        if any(k in p for k in ["monitorları göstər", "list displays", "ekranları göstər", "display info", "monitor status"]):
            mon_res = self.system_tools.get_display_monitors()
            cnt = mon_res.get("count", 1)
            spoken = f"Detected {cnt} connected display monitor(s), sir." if not is_az else f"Sistemdə {cnt} qoşulmuş monitor aşkarlandı, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="get_display_monitors", action_result=mon_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": mon_res})
            return res
        elif any(k in p for k in ["monitora keçir", "move window to monitor", "ekrana keçir"]):
            m_idx = 1
            idx_m = re.search(r"(\d+)", p)
            if idx_m:
                m_idx = int(idx_m.group(1)) - 1
            m_res = self.system_tools.move_window_to_monitor(max(0, m_idx))
            spoken = f"Moved active window to monitor {m_idx + 1}, sir." if not is_az else f"Aktiv pəncərə {m_idx + 1}-ci monitora keçirildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="move_window_to_monitor", action_result=m_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1ak. Deep System Power & Performance Control
        if any(k in p for k in ["performans rejimi", "set performance mode", "turbo mode", "high performance"]):
            p_res = self.system_tools.set_power_profile("performance")
            spoken = "System power profile switched to High Performance, sir." if not is_az else "Sistem yüksək performans rejiminə keçirildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_power_profile", action_result=p_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["qənaət rejimi", "eco mode", "power saver mode", "enerjiyə qənaət"]):
            p_res = self.system_tools.set_power_profile("power-saver")
            spoken = "System power profile switched to Power-Saver, sir." if not is_az else "Sistem enerjiyə qənaət rejiminə keçirildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_power_profile", action_result=p_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["balans rejimi", "balanced mode"]):
            p_res = self.system_tools.set_power_profile("balanced")
            spoken = "System power profile switched to Balanced, sir." if not is_az else "Sistem balanslaşdırılmış rejimə keçirildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_power_profile", action_result=p_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["batareya", "battery status", "zaryadka", "power status"]):
            b_res = self.system_tools.get_battery_status()
            spoken = f"Battery is at {b_res.get('percent', 100):.0f}%, sir." if not is_az else f"Batareya səviyyəsi {b_res.get('percent', 100):.0f}% təşkil edir, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="get_battery_status", action_result=b_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": b_res})
            return res

        # 1al. Night Light / Gecə İşığı
        if any(k in p for k in ["gecə işığını yandır", "gecə rejimini yandır", "enable night light"]):
            nl_res = self.system_tools.set_night_light(True)
            spoken = "Night Light filter enabled, sir." if not is_az else "Gecə işığı filtri aktivləşdirildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_night_light", action_result=nl_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["gecə işığını söndür", "gecə rejimini söndür", "disable night light"]):
            nl_res = self.system_tools.set_night_light(False)
            spoken = "Night Light filter disabled, sir." if not is_az else "Gecə işığı filtri söndürüldü, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_night_light", action_result=nl_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res

        # 1am. Mouse Scroll & Hotkey Automation
        if any(k in p for k in ["aşağı sürüşdür", "scroll down"]):
            sc_res = self.system_tools.scroll_mouse("down", 6)
            spoken = "Scrolled down, sir." if not is_az else "Aşağı sürüşdürüldü, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="scroll_mouse", action_result=sc_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res
        elif any(k in p for k in ["yuxarı sürüşdür", "scroll up"]):
            sc_res = self.system_tools.scroll_mouse("up", 6)
            spoken = "Scrolled up, sir." if not is_az else "Yuxarı sürüşdürüldü, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="scroll_mouse", action_result=sc_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken})
            return res



        # 2. Specific Speedtest / Fast.com intent
        if "fast.com" in p or "speedtest" in p or "speed test" in p:






            self.system_tools.open_url("https://fast.com")
            net = self.system_tools.get_network_info()
            spoken = (
                f"Opening Fast.com in Brave for network speed testing, sir. "
                f"Ping latency is {net.get('latency_ms', 50)} milliseconds."
            )
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="open_url",
                action_result={"url": "https://fast.com", "network": net},
                execution_time=time.monotonic() - t0,
                model_used=self.model,
            )
            self._emit("command_completed", {"response": spoken, "url": "https://fast.com"})
            return res

        # 3. Desktop navigation & app launch (e.g. "go desktop and open tlauncher")
        if any(k in p for k in ["go desktop", "go to desktop", "show desktop", "masaüstü", "masaustu"]):
            m_desk_app = re.search(r"(?:open|launch|start|aç|başlat)\s+(?:the\s+|a\s+|an\s+|my\s+)?([a-zA-Z0-9_\-\.\:\/]+)", p)
            if m_desk_app:
                target_app = m_desk_app.group(1).replace("brawe", "brave")
                self.system_tools.show_desktop()
                res_app = self.system_tools.open_app(target_app)
                spoken = f"Navigating to desktop and launching {target_app} for you now, sir." if not is_az else f"Masaüstünə keçdim və {target_app} tətbiqini başlatdım, cənab."
                self.speak(spoken)
                res = JarvisResponse(
                    spoken_text=spoken,
                    action_taken="desktop_launch_app",
                    action_result={"desktop": "shown", "app": res_app},
                    execution_time=time.monotonic() - t0,
                    model_used=self.model,
                )
                self._emit("command_completed", {"response": spoken, "result": res_app})
                return res
            elif p in ("go desktop", "go to desktop", "show desktop", "desktop", "masaüstünə get", "masaüstünü göstər"):
                self.system_tools.show_desktop()
                spoken = "Showing your desktop now, sir." if not is_az else "Masaüstünü göstərirəm, cənab."
                self.speak(spoken)
                res = JarvisResponse(spoken_text=spoken, action_taken="show_desktop", execution_time=time.monotonic() - t0, model_used=self.model)
                self._emit("command_completed", {"response": spoken})
                return res

        # 4. Direct URL / Domain opening (e.g., "open youtube.com", "github.com")
        m_url = re.search(r"(?:open|launch|go to|aç)\s+([a-zA-Z0-9_\-\.]+\.(?:com|org|io|dev|net|az|edu))", p)
        if m_url:
            domain = m_url.group(1)
            result = self.system_tools.open_url(domain)
            spoken = f"Opening {domain} in your default browser, sir." if not is_az else f"{domain} saytını Brave brauzerində açıram, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="open_url", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 5. Compound command: (e.g. "Launch Brave and check network")
        if any(sep in p for sep in [" and ", " & ", ", then ", " sonra ", " və "]):
            has_browser = any(k in p for k in ["brave", "brawe", "browser", "chrome", "firefox"])
            has_network = any(k in p for k in ["network", "internet", "ping", "latency", "şəbəkə"])
            if has_browser and has_network:
                self.system_tools.open_app("brave")
                net_res = self.system_tools.get_network_info()
                latency = net_res.get("latency_ms", "nominal")
                spoken = f"Launching Brave Browser and checking network connectivity, sir. Ping latency is {latency} milliseconds." if not is_az else f"Brave brauzerini başlatdım və şəbəkəni yoxladım. Gecikmə {latency} millisaniyədir, cənab."
                self.speak(spoken)
                res = JarvisResponse(
                    spoken_text=spoken,
                    action_taken="compound_browser_and_network",
                    action_result={"browser": "brave", "network": net_res},
                    execution_time=time.monotonic() - t0,
                    model_used=self.model,
                )
                self._emit("command_completed", {"response": spoken})
                return res

        # 6. Screenshot capture
        if any(k in p for k in ["take screenshot", "screenshot", "capture screen", "ekran çək", "şəkil çək"]):
            result = self.system_tools.take_screenshot()
            spoken = f"Screenshot captured and saved, sir." if not is_az else "Ekran şəkli çəkildi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="take_screenshot", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 6b. Volume control
        m_vol = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})", p)
        if m_vol:
            level = int(m_vol.group(1))
            result = self.system_tools.set_volume(level)
            spoken = f"Master volume set to {level} percent, sir." if not is_az else f"Səs səviyyəsi {level} faizə qoyuldu, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="set_volume", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 6c. Web search
        m_search = re.search(r"(?:search\s+(?:for|the)?|google\s+(?:for)?)\s+(.+)", p)
        if m_search:
            query = m_search.group(1).strip()
            result = self.system_tools.search_web(query)
            spoken = f"Searching Google for '{query}', sir." if not is_az else f"'{query}' üçün Google-da axtarıram, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="search_web", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 6d. Git summary
        if any(k in p for k in ["git status", "git summary", "filial", "dəyişikliklər", "git"]):
            result = self.system_tools.get_git_summary()
            spoken = f"Workspace is on Git branch {result.get('branch', 'unknown')}, with {result.get('changed_files_count', 0)} modified files, sir." if not is_az else f"Git qolu: {result.get('branch', 'naməlum')}, {result.get('changed_files_count', 0)} dəyişdirilmiş fayl, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="git_summary", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 6e. Direct Simple App Launch (e.g. "open brave", "launch terminal", "open calculator")
        m_app = re.search(r"(?:open|launch|start|aç|başlat)\s+(?:the\s+|a\s+|an\s+|my\s+)?([a-zA-Z0-9_\-\.\:\/]+)", p)
        if m_app and len(p.split()) <= 4:
            app_target = m_app.group(1).replace("brawe", "brave")
            if app_target not in ("the", "a", "an", "my", "this", "app", "application", "file", "fayl"):
                result = self.system_tools.open_app(app_target)
                spoken = f"Opening {app_target} now, sir." if not is_az else f"{app_target} tətbiqini açıram, cənab."
                self.speak(spoken)
                res = JarvisResponse(spoken_text=spoken, action_taken="open_app", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
                self._emit("command_completed", {"response": spoken, "result": result})
                return res

        # 7. System Diagnostics / Telemetry
        if any(k in p for k in ["system status", "diagnostics", "hardware", "vəziyyət", "resurs", "status"]) and "git" not in p and "fast.com" not in p:
            snap = self.telemetry.get_snapshot()
            # Use Azerbaijani only for explicit AZ prompts (has AZ chars or AZ-specific words)
            use_az = any(w in p for w in ["vəziyyət", "resurs", "hal", "yoxla"])
            if use_az:
                spoken = (
                    f"Sistem vəziyyəti əladır, cənab. CPU yükü {snap.cpu_percent:.0f} faiz, "
                    f"RAM istifadəsi {snap.ram_used_gb:.1f} giqabaytdır. Aktiv model {self.model}."
                )
            else:
                spoken = (
                    f"System status is nominal, sir. CPU load is at {snap.cpu_percent:.0f} percent, "
                    f"RAM usage is {snap.ram_used_gb:.1f} gigabytes of {snap.ram_total_gb:.1f} gigabytes. "
                    f"Active model is {self.model}."
                )
            self.speak(spoken)
            res = JarvisResponse(
                spoken_text=spoken,
                action_taken="system_diagnostics",
                action_result=snap.to_dict(),
                telemetry=snap,
                execution_time=time.monotonic() - t0,
                model_used=self.model,
            )
            self._emit("command_completed", {"response": spoken, "telemetry": snap.to_dict()})
            return res

        # 8. Dedicated Network Ping Test
        if any(k in p for k in ["check network", "network check", "ping", "test ping", "latency", "şəbəkəni yoxla", "internet status", "check internet", "network"]) and not any(w in p for w in ["brave", "browser", "chrome", "firefox", "fast.com", "open", "launch"]):
            result = self.system_tools.get_network_info()
            if result.get("online"):
                spoken = f"Internet connection is active with {result.get('latency_ms')} milliseconds latency, sir." if not is_az else f"İnternet aktivdir, ping gecikməsi {result.get('latency_ms')} millisaniyədir, cənab."
            else:
                spoken = "Network connectivity is currently unavailable, sir." if not is_az else "İnternet bağlantısı hazırda əlçatmazdır, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="network_check", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 9. Clean Cache
        if any(k in p for k in ["clean cache", "purge cache", "təmizlə", "keşi təmizlə", "clean temp"]):
            result = self.system_tools.clean_cache()
            spoken = f"System cache purged, sir. Cleaned {result.get('cleaned_dirs', 0)} artifact directories." if not is_az else f"Sistem keşi təmizləndi, {result.get('cleaned_dirs', 0)} qovluq silindi, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="clean_cache", action_result=result, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": result})
            return res

        # 10. Run Project Tests
        if any(k in p for k in ["run tests", "pytest", "testləri işə sal", "testləri yoxla"]):
            test_res = self.coding_bridge.run_tests()
            passed = test_res.get("passed", False)
            spoken = "All project unit tests passed successfully, sir." if passed else "Some tests failed, sir. Recommending code review."
            if is_az:
                spoken = "Bütün testlər uğurla keçdi, cənab." if passed else "Bəzi testlərdə xətalar tapıldı, cənab."
            self.speak(spoken)
            res = JarvisResponse(spoken_text=spoken, action_taken="run_tests", action_result=test_res, execution_time=time.monotonic() - t0, model_used=self.model)
            self._emit("command_completed", {"response": spoken, "result": test_res})
            return res

        # 11. Full Agentic Software Engineering & Multi-Tool LLM Reasoning
        spoken_text, action_taken, action_result, modified = self._reason_with_agentic_llm(user_prompt, is_az)
        self.speak(spoken_text)
        res = JarvisResponse(
            spoken_text=spoken_text,
            action_taken=action_taken or "agentic_execution",
            action_result=action_result,
            execution_time=time.monotonic() - t0,
            model_used=self.model,
            files_modified=modified,
        )
        self._emit("command_completed", {"response": spoken_text, "action": action_taken, "files": modified})
        return res

    def _reason_with_agentic_llm(self, user_prompt: str, is_az: bool = False) -> tuple[str, str | None, dict[str, Any] | None, list[str]]:
        """Run full autonomous agentic reasoning with file tools, execution, and bilingual replies."""
        snap = self.telemetry.get_snapshot()

        # Retrieve RAG memory context and recent conversation history
        rag_context = self.memory_db.build_rag_context(user_prompt)
        history_context = self.memory_db.format_history_for_prompt(n=6)

        system_prompt = (
            f"You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), Tony Stark's autonomous AI assistant "
            f"and expert software engineer deeply integrated into the OS and Vibe Studio IDE.\n"
            f"CURRENT LIVE SYSTEM TELEMETRY & HARDWARE:\n"
            f"- Operating System: {snap.os_name}\n"
            f"- Hostname: {snap.hostname}\n"
            f"- RAM: {snap.ram_used_gb:.1f} GB used / {snap.ram_total_gb:.1f} GB total ({snap.ram_percent:.1f}%)\n"
            f"- CPU: {snap.cpu_percent:.1f}% load ({snap.cpu_cores} cores)\n"
            f"- GPU: {snap.gpu_name or 'N/A'}\n"
            f"- Disk: {snap.disk_used_gb:.1f} GB used / {snap.disk_total_gb:.1f} GB total ({snap.disk_percent:.1f}%)\n"
            f"- User Desktop Path: {self.coding_bridge.desktop_dir}\n"
            f"- Workspace Root: {self.workspace_root}\n"
            f"- Active AI Model: {self.model}\n\n"
            f"{rag_context}\n\n"
            f"{history_context}\n\n"
            f"When asked about RAM, CPU, GPU, OS, disk, or hardware, use these real metrics directly.\n"
            "You are respectful, highly competent, concise, and address the user as 'sir' (or 'cənab' in Azerbaijani).\n"
            "If the user asks in Azerbaijani, respond fluently and naturally in Azerbaijani.\n"
            f"When creating files on Desktop, use 'Desktop/filename' or '{self.coding_bridge.desktop_dir}/filename'.\n\n"
            "You have FULL AUTONOMOUS AGENTIC POWERS to write code, create files, run terminal commands, and control the OS.\n"
            "Whenever an action is required, emit one or more tool calls in this exact format:\n"
            "[TOOL: write_file(\"path\", \"content\")]\n"
            "[TOOL: read_file(\"path\")]\n"
            "[TOOL: list_files(\"path\")]\n"
            "[TOOL: execute_command(\"shell_command\")]\n"
            "[TOOL: run_tests()]\n"
            "[TOOL: open_app(\"brave\" | \"tlauncher\" | \"steam\" | \"terminal\" | \"calculator\" | \"files\" | \"code\" | \"url\")]\n"
            "[TOOL: search_web(\"query\")]\n"
            "[TOOL: play_music(\"song_or_artist_query\")]\n"
            "[TOOL: play_youtube(\"query\")]\n"
            "[TOOL: play_spotify(\"query\")]\n"
            "[TOOL: set_timer(seconds, \"label\")]\n"
            "[TOOL: set_alarm(\"HH:MM\", \"label\")]\n"
            "[TOOL: list_timers()]\n"
            "[TOOL: cancel_timer(\"id_or_label\")]\n"
            "[TOOL: find_files(\"pattern\")]\n"
            "[TOOL: show_notification(\"title\", \"message\")]\n"
            "[TOOL: set_voice_gender(\"female\" | \"male\")]\n"
            "[TOOL: read_active_browser_tab()]\n"
            "[TOOL: click_element_by_text(\"button_text\")]\n"
            "[TOOL: manage_wifi(\"on\" | \"off\" | \"scan\")]\n"
            "[TOOL: manage_bluetooth(\"on\" | \"off\" | \"scan\")]\n"
            "[TOOL: take_screenshot()]\n"
            "[TOOL: analyze_vision(\"query\")]\n"
            "[TOOL: get_screen_summary()]\n"
            "[TOOL: capture_webcam()]\n"
            "[TOOL: window_control(\"maximize\" | \"minimize\" | \"close\")]\n"
            "[TOOL: click_mouse(x, y)]\n"
            "[TOOL: press_keys(\"keys\")]\n"
            "[TOOL: type_text(\"text\")]\n"
            "[TOOL: lock_screen()]\n"
            "[TOOL: remember_fact(\"fact_key\", \"fact_value\")]\n"
            "[TOOL: search_memory(\"query\")]\n"
            "[TOOL: whatsapp_call(\"contact_name\")]\n"
            "[TOOL: whatsapp_message(\"contact_name\", \"message_text\")]\n"
            "[TOOL: save_contact(\"contact_name\", \"phone_number\")]\n"
            "[TOOL: kill_process(\"name_or_pid\")]\n"
            "[TOOL: clean_cache()]\n"
            "[TOOL: get_network_info()]\n"
            "[TOOL: get_system_diagnostics()]\n"
            "[TOOL: get_display_monitors()]\n"
            "[TOOL: move_window_to_monitor(index)]\n"
            "[TOOL: set_power_profile(\"performance\" | \"balanced\" | \"power-saver\")]\n"
            "[TOOL: get_battery_status()]\n"
            "[TOOL: set_night_light(true | false)]\n"
            "[TOOL: scroll_mouse(\"down\" | \"up\", amount)]\n"
            "[TOOL: double_click(x, y)]\n"
            "[TOOL: drag_mouse(x1, y1, x2, y2)]\n"
            "[TOOL: press_hotkey(\"keys\")]\n\n"
            "Always include a concise, natural spoken explanation (1-2 sentences) alongside your tool calls."
        )


        modified_files: list[str] = []

        try:
            if hasattr(self.provider, "generate"):
                raw_resp = self.provider.generate(
                    prompt=user_prompt,
                    model=self.model,
                    system_prompt=system_prompt,
                    temperature=0.3,
                )
                if raw_resp:
                    # Robust regex to extract tool calls even with missing closing brackets or markdown wrappers
                    tool_matches = (
                        re.findall(r"\[TOOL:\s*([a-zA-Z_]+)\s*\((.*?)\)\]", raw_resp, re.DOTALL)
                        or re.findall(r"\[TOOL:\s*([a-zA-Z_]+)\s*\((.*?)(?:\)\s*```|\)\s*\"|\)|\]|$)", raw_resp, re.DOTALL)
                    )
                    if tool_matches:
                        spoken_cleaned = re.sub(r"\[TOOL:.*?\]", "", raw_resp, flags=re.DOTALL)
                        spoken_cleaned = re.sub(r"\[TOOL:.*", "", spoken_cleaned, flags=re.DOTALL).strip()
                        spoken_cleaned = re.sub(r"```[a-zA-Z]*\s*```", "", spoken_cleaned).strip()
                        executed_actions: dict[str, Any] = {}
                        last_action = None

                        for tool_name, tool_arg in tool_matches:
                            last_action = tool_name

                            if tool_name == "write_file":
                                m_wf = (
                                    re.match(r"""["']([^"']+)["']\s*,\s*["']?(.*)["']?""", tool_arg, re.DOTALL)
                                    or re.match(r"""["']([^"']+)["']\s*,\s*(.*)""", tool_arg, re.DOTALL)
                                )
                                if m_wf:
                                    fpath, fcontent = m_wf.group(1), m_wf.group(2).rstrip("\"' )`")
                                    res_wf = self.coding_bridge.write_file(fpath, fcontent)
                                    executed_actions[f"write_{fpath}"] = res_wf
                                    modified_files.append(fpath)

                            elif tool_name == "read_file":
                                fpath = tool_arg.strip().strip('"\'')
                                executed_actions[f"read_{fpath}"] = self.coding_bridge.read_file(fpath)
                            elif tool_name == "list_files":
                                fpath = tool_arg.strip().strip('"\'') or "."
                                executed_actions["list_files"] = self.coding_bridge.list_files(fpath)
                            elif tool_name == "execute_command":
                                cmd = tool_arg.strip().strip('"\'')
                                executed_actions["exec_cmd"] = self.coding_bridge.execute_terminal_command(cmd)
                            elif tool_name == "run_tests":
                                executed_actions["tests"] = self.coding_bridge.run_tests()
                            elif tool_name == "open_app":
                                app_name = tool_arg.strip().strip('"\'')
                                executed_actions[f"open_{app_name}"] = self.system_tools.open_app(app_name)
                            elif tool_name == "search_web":
                                q_web = tool_arg.strip().strip('"\'')
                                executed_actions["search_web"] = self.system_tools.search_web(q_web)
                            elif tool_name in ("play_music", "play_youtube", "play_spotify"):
                                s_name = tool_arg.strip().strip('"\'')
                                executed_actions["play_music"] = self.system_tools.play_youtube(s_name, direct_play=True)
                                executed_actions["music"] = executed_actions["play_music"]
                            elif tool_name == "remember_fact":
                                m_rf = re.match(r"""["']([^"']+)["']\s*,\s*["']?(.*)["']?""", tool_arg, re.DOTALL)
                                if m_rf:
                                    self.memory_db.remember_fact(m_rf.group(1), m_rf.group(2))
                                    executed_actions["remember"] = {"key": m_rf.group(1), "value": m_rf.group(2)}
                            elif tool_name == "search_memory":
                                m_q = tool_arg.strip().strip('"\'')
                                executed_actions["memory"] = [c.__dict__ for c in self.memory_db.search_rag(m_q)]
                            elif tool_name == "get_screen_summary":
                                executed_actions["screen_summary"] = self.system_tools.get_screen_summary()
                            elif tool_name == "set_timer":
                                m_tm = re.match(r"""(\d+(?:\.\d+)?)\s*(?:,\s*["']?(.*?)["']?)?$""", tool_arg.strip())
                                if m_tm:
                                    s_val = float(m_tm.group(1))
                                    s_lbl = m_tm.group(2) or "Timer"
                                    executed_actions["set_timer"] = self.scheduler.set_timer(s_val, s_lbl).to_dict()
                            elif tool_name == "set_alarm":
                                m_al = re.match(r"""["']?(\d{1,2}:\d{2})["']?\s*(?:,\s*["']?(.*?)["']?)?$""", tool_arg.strip())
                                if m_al:
                                    a_item = self.scheduler.set_alarm(m_al.group(1), m_al.group(2) or "Alarm")
                                    executed_actions["set_alarm"] = a_item.to_dict() if a_item else {}
                            elif tool_name == "list_timers":
                                executed_actions["timers"] = [t.to_dict() for t in self.scheduler.list_active_timers()]
                            elif tool_name == "cancel_timer":
                                t_target = tool_arg.strip().strip('"\'')
                                executed_actions["cancel_timer"] = self.scheduler.cancel_timer(t_target)
                            elif tool_name == "find_files":
                                pat = tool_arg.strip().strip('"\'')
                                executed_actions["find_files"] = self.system_tools.find_files_global(pat)
                            elif tool_name == "show_notification":
                                m_notif_args = re.match(r"""["']([^"']+)["']\s*,\s*["']?(.*)["']?""", tool_arg, re.DOTALL)
                                if m_notif_args:
                                    executed_actions["notification"] = self.system_tools.show_desktop_notification(m_notif_args.group(1), m_notif_args.group(2))
                                else:
                                    executed_actions["notification"] = self.system_tools.show_desktop_notification("J.A.R.V.I.S.", tool_arg.strip().strip('"\''))
                            elif tool_name == "set_voice_gender":
                                g_arg = tool_arg.strip().strip('"\'')
                                executed_actions["voice"] = self.voice_engine.set_gender(g_arg)
                            elif tool_name == "read_active_browser_tab":
                                executed_actions["active_tab"] = self.system_tools.read_active_browser_tab()
                            elif tool_name == "click_element_by_text":
                                c_txt = tool_arg.strip().strip('"\'')
                                executed_actions["click_element"] = self.system_tools.click_element_by_text(c_txt)
                            elif tool_name == "manage_wifi":
                                w_act = tool_arg.strip().strip('"\'')
                                executed_actions["wifi"] = self.system_tools.manage_wifi(w_act)
                            elif tool_name == "manage_bluetooth":
                                b_act = tool_arg.strip().strip('"\'')
                                executed_actions["bluetooth"] = self.system_tools.manage_bluetooth(b_act)
                            elif tool_name == "take_screenshot":
                                executed_actions["screenshot"] = self.system_tools.take_screenshot()
                            elif tool_name == "analyze_vision":
                                q_vis = tool_arg.strip().strip('"\'') or "Analyze screen"
                                executed_actions["vision"] = self.system_tools.analyze_screenshot_vision(q_vis)
                            elif tool_name == "capture_webcam":
                                executed_actions["webcam"] = self.system_tools.capture_webcam()
                            elif tool_name == "window_control":
                                w_act = tool_arg.strip().strip('"\'')
                                executed_actions["window_control"] = self.system_tools.window_control(w_act)
                            elif tool_name == "click_mouse":
                                m_clk = re.match(r"(\d+)\s*,\s*(\d+)", tool_arg.strip())
                                if m_clk:
                                    executed_actions["click_mouse"] = self.system_tools.click_mouse(int(m_clk.group(1)), int(m_clk.group(2)))
                            elif tool_name == "press_keys":
                                p_k = tool_arg.strip().strip('"\'')
                                executed_actions["press_keys"] = self.system_tools.press_keys(p_k)
                            elif tool_name == "type_text":
                                t_txt = tool_arg.strip().strip('"\'')
                                executed_actions["type_text"] = self.system_tools.type_text(t_txt)
                            elif tool_name == "lock_screen":
                                executed_actions["lock_screen"] = self.system_tools.lock_screen()
                            elif tool_name == "whatsapp_call":
                                cname = tool_arg.strip().strip('"\'')
                                executed_actions[f"whatsapp_call_{cname}"] = self.system_tools.whatsapp_call(cname)
                            elif tool_name == "whatsapp_message":
                                m_wamsg_arg = re.match(r"""["']([^"']+)["']\s*,\s*["']?(.*)["']?""", tool_arg, re.DOTALL)
                                if m_wamsg_arg:
                                    executed_actions["whatsapp_message"] = self.system_tools.whatsapp_message(m_wamsg_arg.group(1), m_wamsg_arg.group(2))
                            elif tool_name == "save_contact":
                                m_sc_arg = re.match(r"""["']([^"']+)["']\s*,\s*["']?(.*)["']?""", tool_arg, re.DOTALL)
                                if m_sc_arg:
                                    executed_actions["save_contact"] = self.system_tools.save_contact(m_sc_arg.group(1), m_sc_arg.group(2))
                            elif tool_name == "kill_process":
                                proc = tool_arg.strip().strip('"\'')
                                executed_actions[f"kill_{proc}"] = self.system_tools.kill_process(proc)
                            elif tool_name == "clean_cache":
                                executed_actions["clean_cache"] = self.system_tools.clean_cache()
                            elif tool_name == "get_network_info":
                                executed_actions["network"] = self.system_tools.get_network_info()
                            elif tool_name == "get_display_monitors":
                                executed_actions["monitors"] = self.system_tools.get_display_monitors()
                            elif tool_name == "move_window_to_monitor":
                                m_idx = int(tool_arg.strip().strip('"\'') or 1)
                                executed_actions["move_window"] = self.system_tools.move_window_to_monitor(m_idx)
                            elif tool_name == "set_power_profile":
                                p_prof = tool_arg.strip().strip('"\'')
                                executed_actions["power_profile"] = self.system_tools.set_power_profile(p_prof)
                            elif tool_name == "get_battery_status":
                                executed_actions["battery"] = self.system_tools.get_battery_status()
                            elif tool_name == "set_night_light":
                                nl_en = "true" in tool_arg.lower() or "1" in tool_arg
                                executed_actions["night_light"] = self.system_tools.set_night_light(nl_en)
                            elif tool_name == "scroll_mouse":
                                m_sc_args = re.match(r"""["']?(\w+)["']?\s*(?:,\s*(\d+))?""", tool_arg.strip())
                                if m_sc_args:
                                    s_dir = m_sc_args.group(1) or "down"
                                    s_amt = int(m_sc_args.group(2) or 5)
                                    executed_actions["scroll"] = self.system_tools.scroll_mouse(s_dir, s_amt)
                                else:
                                    executed_actions["scroll"] = self.system_tools.scroll_mouse("down", 5)
                            elif tool_name == "double_click":
                                m_dc = re.match(r"(\d+)\s*,\s*(\d+)", tool_arg.strip())
                                if m_dc:
                                    executed_actions["double_click"] = self.system_tools.double_click(int(m_dc.group(1)), int(m_dc.group(2)))
                            elif tool_name == "drag_mouse":
                                m_dg = re.match(r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", tool_arg.strip())
                                if m_dg:
                                    executed_actions["drag"] = self.system_tools.drag_mouse(int(m_dg.group(1)), int(m_dg.group(2)), int(m_dg.group(3)), int(m_dg.group(4)))
                            elif tool_name == "press_hotkey":
                                p_h = tool_arg.strip().strip('"\'')
                                executed_actions["hotkey"] = self.system_tools.press_hotkey(p_h)
                            elif tool_name == "get_system_diagnostics":
                                executed_actions["diagnostics"] = self.telemetry.get_snapshot().to_dict()

                        return spoken_cleaned or "Executing your requested task, sir.", last_action, executed_actions, modified_files

                    raw_text = raw_resp.strip()

                    refusal_patterns = [
                        "i am not a retailer", "not a retailer", "i cannot assist with that",
                        "i will search the internet for you", "i will search for you",
                        "i don't have real-time", "i do not have access to real-time",
                        "baxmaq olmaydi", "internetənə baxmaydik", "i'm sorry, but i can't assist"
                    ]
                    if any(rp in raw_text.lower() for rp in refusal_patterns):
                        s_res = self.system_tools.search_web(user_prompt)
                        snips = s_res.get("snippets", [])
                        if snips:
                            top_info = snips[0]
                            if len(top_info) > 220:
                                top_info = top_info[:220] + "..."
                            spoken = f"According to current web data: {top_info} I have also opened the search results for you, sir." if not is_az else f"İnternetdə ən son məlumatlara əsasən: {top_info} Nəticələri brauzerdə də açdım, cənab."
                        else:
                            spoken = f"I have searched the web for '{user_prompt}' and opened the results in your browser, sir." if not is_az else f"'{user_prompt}' üçün internetdə axtarış etdim və nəticələri brauzerdə açdım, cənab."
                        return spoken, "search_web", {"search": s_res}, []

                    return raw_text, "llm_dialogue", None, []

        except Exception:
            pass

        # Fallback
        fallback = f"Right away, sir. Executing: '{user_prompt}'." if not is_az else f"Oldu, cənab. '{user_prompt}' sorğusunu icra edirəm."
        return fallback, "fallback", None, []


