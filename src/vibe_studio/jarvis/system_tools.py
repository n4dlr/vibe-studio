"""JarvisSystemTools — Universal Desktop, Application & OS Automation Engine.

Capabilities:
1. Launch ANY application or game on the computer (Desktop shortcuts, TLauncher, Steam, Games, Brave, Chrome, Discord, Spotify)
2. Scan & execute .desktop entries across ~/Desktop, /usr/share/applications, Flatpak, and Snap
3. Desktop navigation (Show desktop, minimize/restore via wmctrl)
4. Full-screen & active window screenshot capture
5. Master volume control, mute, and unmute
6. Process termination & system cache purger
7. Real-time network ping & latency monitor
8. Git status & repository telemetry
9. Web search & URL navigation in default browser
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any


class JarvisSystemTools:
    """Universal OS automation and application launcher for J.A.R.V.I.S."""

    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.home_dir = Path.home()
        self.desktop_dir = self.home_dir / "Desktop"

    def show_desktop(self) -> dict[str, Any]:
        """Minimize windows and reveal the desktop."""
        if shutil.which("wmctrl"):
            try:
                subprocess.run(["wmctrl", "-k", "on"], check=True, timeout=2)
                return {"status": "success", "message": "Showing desktop."}
            except Exception:
                pass
        return {"status": "success", "message": "Desktop focused."}

    def open_url(self, url: str) -> dict[str, Any]:
        """Open a URL in the user's primary/default desktop browser."""
        target = url.strip()
        if not target.startswith(("http://", "https://")):
            target = f"https://{target}"

        # 1. Try gio open (standard on modern Linux desktop environments)
        if shutil.which("gio"):
            try:
                res = subprocess.run(["gio", "open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
                if res.returncode == 0:
                    return {"status": "success", "url": target, "message": f"Opened {target} in default browser."}
            except Exception:
                pass

        # 2. Try xdg-open
        if shutil.which("xdg-open"):
            try:
                subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return {"status": "success", "url": target, "message": f"Opened {target} via xdg-open."}
            except Exception:
                pass

        # 3. Try Flatpak Brave directly if installed
        if shutil.which("flatpak"):
            try:
                subprocess.Popen(["flatpak", "run", "com.brave.Browser", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return {"status": "success", "url": target, "message": f"Opened {target} in Brave Browser."}
            except Exception:
                pass

        # 4. Standard Python webbrowser fallback
        webbrowser.open(target)
        return {"status": "success", "url": target, "message": f"Opened {target} in default browser."}

    def _launch_desktop_file(self, desktop_file_path: Path) -> bool:
        """Launch an application from a .desktop file path."""
        # Try gio launch
        if shutil.which("gio"):
            try:
                subprocess.Popen(["gio", "launch", str(desktop_file_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return True
            except Exception:
                pass

        # Try gtk-launch with base name
        if shutil.which("gtk-launch"):
            try:
                subprocess.Popen(["gtk-launch", desktop_file_path.stem], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return True
            except Exception:
                pass

        # Parse Exec line directly
        try:
            content = desktop_file_path.read_text(encoding="utf-8", errors="ignore")
            exec_match = re.search(r"^Exec\s*=\s*(.*)$", content, re.MULTILINE)
            path_match = re.search(r"^Path\s*=\s*(.*)$", content, re.MULTILINE)
            if exec_match:
                cmd_line = exec_match.group(1).strip()
                # Remove field codes like %f, %F, %u, %U
                cmd_cleaned = re.sub(r"%[a-zA-Z]", "", cmd_line).strip()
                work_dir = path_match.group(1).strip() if path_match else str(self.home_dir)
                subprocess.Popen(cmd_cleaned, shell=True, cwd=work_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return True
        except Exception:
            pass

        return False

    def open_app(self, app_name: str) -> dict[str, Any]:
        """Universal launcher: finds and starts desktop shortcuts, system applications, games, or URLs."""
        name = app_name.strip().lower()

        # URLs or Web links
        if name.startswith(("http://", "https://", "www.")) or any(name.endswith(ext) for ext in [".com", ".org", ".io", ".dev", ".net", ".az"]):
            return self.open_url(name)

        # Generic Browser request -> open default browser home
        if name in ("browser", "web", "internet", "brave", "brawe", "brave-browser", "default-browser"):
            return self.open_url("https://google.com")

        # 1. Check User's Desktop directory (~/Desktop) for matching shortcuts/files
        if self.desktop_dir.exists():
            for f in self.desktop_dir.iterdir():
                clean_stem = f.stem.lower().replace(" ", "").replace("-", "").replace("_", "")
                query_clean = name.replace(" ", "").replace("-", "").replace("_", "")
                if query_clean in clean_stem or clean_stem in query_clean:
                    if f.suffix == ".desktop":
                        if self._launch_desktop_file(f):
                            return {"status": "success", "message": f"Launched {f.name} from Desktop."}
                    elif os.access(f, os.X_OK):
                        subprocess.Popen([str(f)], cwd=str(self.desktop_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                        return {"status": "success", "message": f"Executed {f.name} from Desktop."}

        # 2. Check System Desktop application directories
        app_dirs = [
            self.home_dir / ".local" / "share" / "applications",
            Path("/usr/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications"),
            Path("/var/lib/snapd/desktop/applications"),
            Path("/usr/local/share/applications"),
        ]
        for ad in app_dirs:
            if ad.exists():
                for df in ad.glob("*.desktop"):
                    clean_stem = df.stem.lower().replace(" ", "").replace("-", "").replace("_", "")
                    query_clean = name.replace(" ", "").replace("-", "").replace("_", "")
                    if query_clean in clean_stem or clean_stem in query_clean:
                        if self._launch_desktop_file(df):
                            return {"status": "success", "message": f"Launched {df.stem} application."}

        # 3. Known application mappings
        app_map: dict[str, list[list[str]]] = {
            "tlauncher": [["gtk-launch", "tlauncher"], ["gio", "launch", str(self.desktop_dir / "tlauncher.desktop")]],
            "chrome": [["google-chrome"], ["google-chrome-stable"]],
            "chromium": [["chromium"], ["/snap/bin/chromium"]],
            "firefox": [["firefox"], ["/snap/bin/firefox"]],
            "discord": [["flatpak", "run", "com.discordapp.Discord"], ["discord"]],
            "spotify": [["spotify"], ["snap", "run", "spotify"], ["flatpak", "run", "com.spotify.Client"]],
            "steam": [["steam"], ["gtk-launch", "steam"]],
            "terminal": [["gnome-terminal"], ["x-terminal-emulator"], ["alacritty"], ["kitty"], ["xterm"], ["cmd.exe"]],
            "calculator": [["gnome-calculator"], ["kcalc"], ["calc.exe"]],
            "files": [["nautilus"], ["nemo"], ["dolphin"], ["thunar"], ["xdg-open", "."]],
            "editor": [["code"], ["codium"], ["gedit"], ["kate"]],
            "vscode": [["code"], ["codium"]],
        }

        candidates = app_map.get(name, [[name]])
        for cmd in candidates:
            bin_name = cmd[0]
            if shutil.which(bin_name) or os.path.exists(bin_name):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    return {"status": "success", "message": f"Launched {' '.join(cmd)} successfully."}
                except Exception:
                    continue

        # 4. Fallback to gio / xdg-open for arbitrary desktop files
        if shutil.which("gio"):
            try:
                subprocess.Popen(["gio", "open", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return {"status": "success", "message": f"Opened {name} via system handler."}
            except Exception:
                pass

        if shutil.which("xdg-open"):
            try:
                subprocess.Popen(["xdg-open", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return {"status": "success", "message": f"Opened {name} via xdg-open."}
            except Exception as e:
                return {"status": "error", "message": f"Could not launch '{app_name}': {e}"}

        return {"status": "error", "message": f"Application '{app_name}' not found."}

    def take_screenshot(self, output_path: str = "screenshot.png") -> dict[str, Any]:
        """Capture full screen screenshot and save to workspace."""
        out = self.workspace_root / output_path
        try:
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
        """Search Google in the user's default desktop browser."""
        encoded = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded}"
        res = self.open_url(url)
        return {"status": "success", "query": query, "url": url, "message": f"Searching Google for '{query}'"}

    def kill_process(self, proc_name_or_pid: str) -> dict[str, Any]:
        """Terminate a background process by name or PID."""
        target = proc_name_or_pid.strip()
        try:
            if target.isdigit():
                pid = int(target)
                os.kill(pid, 9)
                return {"status": "success", "message": f"Killed PID {pid} successfully."}
            else:
                if shutil.which("pkill"):
                    subprocess.run(["pkill", "-f", target], check=True)
                    return {"status": "success", "message": f"Terminated process matching '{target}'."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to kill process '{proc_name_or_pid}': {e}"}
        return {"status": "error", "message": f"Process '{proc_name_or_pid}' not found."}

    def get_network_info(self) -> dict[str, Any]:
        """Check network ping latency and connectivity status."""
        try:
            t0 = time.monotonic()
            res = subprocess.run(["ping", "-c", "1", "-W", "2", "8.8.8.8"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            is_online = (res.returncode == 0)
            return {
                "status": "success",
                "online": is_online,
                "latency_ms": latency_ms if is_online else None,
                "message": f"Internet is {'Online (latency: ' + str(latency_ms) + 'ms)' if is_online else 'Offline'}",
            }
        except Exception as e:
            return {"status": "error", "online": False, "message": f"Network check failed: {e}"}

    def clean_cache(self) -> dict[str, Any]:
        """Purge temporary cache and pytest/pycache artifacts."""
        cleaned_dirs = 0
        try:
            for root, dirs, files in os.walk(self.workspace_root):
                for d in list(dirs):
                    if d in ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"):
                        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                        cleaned_dirs += 1
            return {"status": "success", "cleaned_dirs": cleaned_dirs, "message": f"Cleaned {cleaned_dirs} cache directories."}
        except Exception as e:
            return {"status": "error", "message": f"Cache clean failed: {e}"}

    def get_git_summary(self) -> dict[str, Any]:
        """Fetch current Git branch and modification summary."""
        try:
            branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.workspace_root, text=True).strip()
            status_out = subprocess.check_output(["git", "status", "--short"], cwd=self.workspace_root, text=True).strip()
            num_changed = len(status_out.splitlines()) if status_out else 0
            return {
                "status": "success",
                "branch": branch,
                "changed_files_count": num_changed,
                "message": f"Git on branch '{branch}' with {num_changed} changed files.",
            }
        except Exception as e:
            return {"status": "error", "message": f"Git check failed: {e}"}
