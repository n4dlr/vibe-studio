"""JarvisSystemTools — Operating System, Application & Web Control for JARVIS.

Enables JARVIS to:
1. Open native applications (Browser, Terminal, VS Code, Spotify, Calculator, etc.)
2. Capture full-screen or window screenshots
3. Control volume, mute/unmute, brightness
4. Search the web and fetch live answers
5. Run shell scripts and manage background processes
"""
from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any


class JarvisSystemTools:
    """OS automation and tool execution engine for JARVIS."""

    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def open_app(self, app_name: str) -> dict[str, Any]:
        """Launch an application or URL."""
        name = app_name.strip().lower()
        if name.startswith(("http://", "https://", "www.")):
            url = name if name.startswith("http") else f"https://{name}"
            webbrowser.open(url)
            return {"status": "success", "message": f"Opened {url} in default browser."}

        app_map = {
            "browser": ["google-chrome", "chromium", "firefox", "brave-browser", "xdg-open", "open", "start"],
            "chrome": ["google-chrome", "google-chrome-stable", "chromium-browser"],
            "firefox": ["firefox"],
            "terminal": ["gnome-terminal", "alacritty", "kitty", "xterm", "cmd.exe"],
            "calculator": ["gnome-calculator", "calc.exe", "kcalc"],
            "files": ["nautilus", "dolphin", "explorer.exe", "open"],
            "editor": ["code", "gedit", "kate", "notepad.exe"],
            "vscode": ["code"],
        }

        candidates = app_map.get(name, [name])
        for cand in candidates:
            bin_path = shutil.which(cand)
            if bin_path or cand in ("xdg-open", "open", "start"):
                try:
                    subprocess.Popen([cand], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    return {"status": "success", "message": f"Launched {cand} successfully."}
                except Exception:
                    continue

        # Fallback to xdg-open on linux
        try:
            subprocess.Popen(["xdg-open", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"status": "success", "message": f"Opened {name} via default handler."}
        except Exception as e:
            return {"status": "error", "message": f"Could not launch application '{app_name}': {e}"}

    def take_screenshot(self, output_path: str = "screenshot.png") -> dict[str, Any]:
        """Capture full screen screenshot."""
        out = self.workspace_root / output_path
        try:
            # Try scrot or import or spectacle on Linux
            for cmd in [
                ["scrot", str(out)],
                ["gnome-screenshot", "-f", str(out)],
                ["import", "-window", "root", str(out)],
                ["spectacle", "-b", "-o", str(out)],
            ]:
                if shutil.which(cmd[0]):
                    subprocess.run(cmd, check=True, timeout=5)
                    if out.exists():
                        return {"status": "success", "path": str(out), "message": f"Screenshot saved to {out.name}"}
        except Exception:
            pass

        # Try Pillow ImageGrab if installed
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(str(out))
            return {"status": "success", "path": str(out), "message": f"Screenshot saved to {out.name}"}
        except Exception as e:
            return {"status": "error", "message": f"Screenshot failed: {e}"}

    def set_volume(self, level_percent: int) -> dict[str, Any]:
        """Set master audio volume level (0-100)."""
        level = max(0, min(100, level_percent))
        try:
            if shutil.which("pamixer"):
                subprocess.run(["pamixer", "--set-volume", str(level)], check=True)
                return {"status": "success", "message": f"Volume set to {level}%"}
            elif shutil.which("amixer"):
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{level}%"], check=True)
                return {"status": "success", "message": f"Volume set to {level}%"}
            elif shutil.which("pactl"):
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=True)
                return {"status": "success", "message": f"Volume set to {level}%"}
        except Exception as e:
            return {"status": "error", "message": f"Volume control failed: {e}"}
        return {"status": "error", "message": "No audio mixer utility found."}

    def search_web(self, query: str) -> dict[str, Any]:
        """Search the web for real-time information."""
        import urllib.parse
        encoded = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded}"
        webbrowser.open(url)
        return {"status": "success", "query": query, "url": url, "message": f"Searching Google for '{query}'"}
