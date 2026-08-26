"""Automated Windows Packaging Script for JARVIS.

Produces:
1. Portable Package: dist/JARVIS-Portable-Windows-x64.zip
2. Installer: dist/JARVIS-Setup-x64.exe (via Inno Setup ISCC when available)
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# Repo paths
REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGING_DIR = REPO_ROOT / "packaging"
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packaging.common.version import JARVIS_VERSION


def calculate_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_pyinstaller_bundle() -> Path:
    """Build standalone Windows distribution folder."""
    print("=" * 70)
    print("  🔨 [1/3] Building Standalone PyInstaller Bundle for Windows x64")
    print("=" * 70)

    spec_file = PACKAGING_DIR / "jarvis.spec"
    dist_path = DIST_DIR
    build_path = BUILD_DIR / "pyinstaller_win"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--distpath={dist_path}",
        f"--workpath={build_path}",
        str(spec_file),
    ]

    print(f"Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(REPO_ROOT))

    bundle_dir = dist_path / "jarvis"
    if not bundle_dir.exists():
        raise RuntimeError(f"PyInstaller build failed: {bundle_dir} does not exist.")

    print(f"✅ Standalone bundle ready at: {bundle_dir}\n")
    return bundle_dir


def create_portable_zip(bundle_dir: Path) -> Path:
    """Create zero-install portable zip archive."""
    print("=" * 70)
    print("  📦 [2/3] Creating Portable Zip Archive: JARVIS-Portable-Windows-x64.zip")
    print("=" * 70)

    zip_filename = f"JARVIS-Portable-Windows-x64-v{JARVIS_VERSION}.zip"
    zip_path = DIST_DIR / zip_filename
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for root, _, files in os.walk(bundle_dir):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(bundle_dir)
                zipf.write(full_path, arcname=f"JARVIS/{rel_path}")

    # Also make a canonical symlink/copy named JARVIS-Portable-Windows-x64.zip
    canonical_zip = DIST_DIR / "JARVIS-Portable-Windows-x64.zip"
    shutil.copyfile(zip_path, canonical_zip)

    size_mb = canonical_zip.stat().st_size / (1024 * 1024)
    print(f"✅ Portable zip created: {canonical_zip} ({round(size_mb, 2)} MB)")
    print(f"   SHA256: {calculate_sha256(canonical_zip)}\n")
    return canonical_zip


def create_inno_setup_installer() -> Path | None:
    """Compile Inno Setup script if ISCC compiler is present."""
    print("=" * 70)
    print("  🚀 [3/3] Compiling Inno Setup Installer: JARVIS-Setup-x64.exe")
    print("=" * 70)

    iss_file = PACKAGING_DIR / "windows" / "installer" / "jarvis_installer.iss"
    if not iss_file.exists():
        print(f"⚠️ Inno Setup script not found at {iss_file}")
        return None

    # Check for ISCC in PATH or typical installation paths
    iscc_candidates = [
        shutil.which("iscc"),
        shutil.which("ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    iscc_bin = next((c for c in iscc_candidates if c and Path(c).exists()), None)

    if not iscc_bin:
        print("ℹ️ Inno Setup compiler (ISCC.exe) not detected in environment.")
        print("   (To generate JARVIS-Setup-x64.exe on Windows, install Inno Setup 6: https://jrsoftware.org/isdl.php)")
        print("   The .iss script is ready for compilation: packaging/windows/installer/jarvis_installer.iss\n")
        return None

    cmd = [str(iscc_bin), f"/DMyAppVersion={JARVIS_VERSION}", str(iss_file)]
    print(f"Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(REPO_ROOT))

    setup_exe = DIST_DIR / "JARVIS-Setup-x64.exe"
    if setup_exe.exists():
        size_mb = setup_exe.stat().st_size / (1024 * 1024)
        print(f"✅ Windows Setup created: {setup_exe} ({round(size_mb, 2)} MB)")
        print(f"   SHA256: {calculate_sha256(setup_exe)}\n")
        return setup_exe

    return None


def build() -> None:
    """Run full Windows build pipeline."""
    bundle = build_pyinstaller_bundle()
    create_portable_zip(bundle)
    create_inno_setup_installer()


if __name__ == "__main__":
    try:
        build()
    except Exception as e:
        print(f"\n❌ Windows Build Failed: {e}", file=sys.stderr)
        sys.exit(1)
