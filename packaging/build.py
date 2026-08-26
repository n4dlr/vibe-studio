"""Unified Build & Packaging CLI for JARVIS.

Commands:
  python -m packaging.build --target linux
  python -m packaging.build --target windows
  python -m packaging.build --target portable
  python -m packaging.build --target all
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packaging.common.version import JARVIS_DISPLAY_NAME, JARVIS_VERSION


def build_linux() -> None:
    print(f"\n🐧 Building Linux Debian Package for {JARVIS_DISPLAY_NAME} v{JARVIS_VERSION}...")
    from packaging.linux.build_deb import build
    build()


def build_windows() -> None:
    print(f"\n🪟 Building Windows Packages for {JARVIS_DISPLAY_NAME} v{JARVIS_VERSION}...")
    from packaging.windows.build_windows import build
    build()


def build_portable() -> None:
    print(f"\n📦 Building Portable Distribution Archive...")
    from packaging.windows.build_windows import build_pyinstaller_bundle, create_portable_zip
    bundle = build_pyinstaller_bundle()
    create_portable_zip(bundle)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-build",
        description=f"Unified Build Pipeline for {JARVIS_DISPLAY_NAME} v{JARVIS_VERSION}",
    )
    parser.add_argument(
        "--target",
        choices=["linux", "windows", "portable", "all"],
        default="auto",
        help="Target distribution package to build (default: auto-detect by OS)",
    )

    args = parser.parse_args()
    target = args.target

    if target == "auto":
        target = "windows" if platform.system() == "Windows" else "linux"

    if target in ("linux", "all") and platform.system() != "Windows":
        build_linux()

    if target in ("windows", "all") and platform.system() == "Windows":
        build_windows()

    if target == "portable":
        build_portable()

    if target == "all" and platform.system() != "Windows":
        print("\nℹ️ Target 'all': Building Linux .deb and Portable packages on Linux host.")
        build_portable()

    print(f"\n🎉 Build process completed. Distribution packages available in 'dist/'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
