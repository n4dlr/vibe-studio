from __future__ import annotations

import ctypes.util
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from vibe_studio.core.logger import build_logger
from vibe_studio.core.settings import SettingsStore


def _configure_qt_platform() -> None:
    if os.environ.get("QT_QPA_PLATFORM"):
        return

    if sys.platform.startswith("linux"):
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        xcb_library = ctypes.util.find_library("xcb-cursor") or ctypes.util.find_library("xcb")
        if not has_display or not xcb_library:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"


def launch_jarvis_standalone(workspace_root: str | Path = ".") -> int:
    """Launch dedicated standalone J.A.R.V.I.S Cyber Cockpit with Windows Aero Snapping."""
    _configure_qt_platform()

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("J.A.R.V.I.S Cockpit")
    app.setOrganizationName("Vibe Studio")

    from vibe_studio.ui.jarvis_window import JarvisStandaloneWindow

    jarvis_win = JarvisStandaloneWindow(workspace_root=workspace_root)
    jarvis_win.show()

    return app.exec()


def main(standalone_jarvis: bool = False) -> int:
    """Main application launcher."""
    # Check if --jarvis or jarvis flag passed in sys.argv
    if standalone_jarvis or "--jarvis" in sys.argv or (len(sys.argv) > 1 and sys.argv[1] == "jarvis"):
        return launch_jarvis_standalone()

    _configure_qt_platform()

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Vibe Studio")
    app.setOrganizationName("Vibe Studio")

    app_dir = Path.home() / ".vibe_studio"
    app_dir.mkdir(parents=True, exist_ok=True)
    settings_store = SettingsStore(app_dir / "settings.json")
    settings = settings_store.load()

    logger = build_logger("vibe_studio", app_dir)
    logger.info("Starting Vibe Studio")

    from vibe_studio.app.main_window import MainWindow

    window = MainWindow(settings_store=settings_store, settings=settings)
    window.show()

    return app.exec()
