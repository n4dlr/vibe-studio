from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from vibe_studio.app.main_window import MainWindow
from vibe_studio.core.logger import build_logger
from vibe_studio.core.settings import SettingsStore


def main() -> int:
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

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
