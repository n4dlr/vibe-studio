#!/usr/bin/env python3
"""Convenience entrypoint: python build_all.py"""
import sys
from pathlib import Path

# Add repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from packaging.build import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--target", "all"]
    sys.exit(main())
