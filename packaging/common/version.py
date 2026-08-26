"""Single source of truth for JARVIS & Vibe Studio application version and build metadata."""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from datetime import datetime, timezone

JARVIS_NAME = "JARVIS"
JARVIS_DISPLAY_NAME = "J.A.R.V.I.S — Autonomous OS"
JARVIS_VERSION = "0.1.0"
JARVIS_VERSION_INFO = (0, 1, 0)
JARVIS_RELEASE_CODENAME = "Omniverse Prime"
JARVIS_VENDOR = "Vibe Studio"
JARVIS_COPYRIGHT = f"Copyright (c) 2024-{datetime.now().year} Vibe Studio. All rights reserved."
JARVIS_LICENSE = "MIT"
JARVIS_DESCRIPTION = "AI-first autonomous operating system, desktop assistant, and coding engine"


@dataclass(frozen=True)
class BuildMetadata:
    version: str
    build_date: str
    target_platform: str
    target_arch: str
    commit_sha: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "name": JARVIS_NAME,
            "display_name": JARVIS_DISPLAY_NAME,
            "version": self.version,
            "build_date": self.build_date,
            "platform": self.target_platform,
            "arch": self.target_arch,
            "commit_sha": self.commit_sha,
            "vendor": JARVIS_VENDOR,
        }


def get_build_metadata() -> BuildMetadata:
    """Retrieve runtime build metadata."""
    build_date = os.environ.get("JARVIS_BUILD_DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"))
    commit_sha = os.environ.get("JARVIS_GIT_COMMIT", None)
    return BuildMetadata(
        version=JARVIS_VERSION,
        build_date=build_date,
        target_platform=platform.system(),
        target_arch=platform.machine(),
        commit_sha=commit_sha,
    )
