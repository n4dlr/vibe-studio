from __future__ import annotations

import ctypes.util
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from vibe_studio.app.main_window import MainWindow
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


def main() -> int:
    _configure_qt_platform()

    app = QApplication([])
    app.setApplicationName("Vibe Studio")
    app.setOrganizationName("Vibe Studio")

    app_dir = Path.home() / ".vibe_studio"
    app_dir.mkdir(parents=True, exist_ok=True)
    settings_store = SettingsStore(app_dir / "settings.json")
    settings = settings_store.load()

    logger = build_logger("vibe_studio", app_dir)
    logger.info("Starting Vibe Studio")

    window = MainWindow(settings_store=settings_store, settings=settings)
    window.show()

    return app.exec()
