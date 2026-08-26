#!/usr/bin/env python3
"""Convenience entrypoint: python build_linux.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from packaging.linux.build_deb import build

if __name__ == "__main__":
    build()
