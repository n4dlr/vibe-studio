"""Automated Debian Package (.deb) builder for JARVIS."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Repo paths
REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGING_DIR = REPO_ROOT / "packaging"
SRC_DIR = REPO_ROOT / "src"
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
    """Build standalone PyInstaller distribution directory."""
    print("=" * 70)
    print("  🔨 [1/4] Building Standalone PyInstaller Bundle for Linux x86_64")
    print("=" * 70)

    spec_file = PACKAGING_DIR / "jarvis.spec"
    dist_path = DIST_DIR
    build_path = BUILD_DIR / "pyinstaller"

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
    if not bundle_dir.exists() or not (bundle_dir / "jarvis").exists():
        raise RuntimeError(f"PyInstaller build failed: {bundle_dir} does not exist.")

    print(f"✅ PyInstaller bundle successfully created at: {bundle_dir}\n")
    return bundle_dir


def stage_debian_package(bundle_dir: Path) -> Path:
    """Stage files into standard Debian package directory structure."""
    print("=" * 70)
    print("  📦 [2/4] Assembling Debian Package Filesystem Hierarchy")
    print("=" * 70)

    staging_dir = BUILD_DIR / "deb_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    debian_dir = staging_dir / "DEBIAN"
    opt_jarvis = staging_dir / "opt" / "jarvis"
    apps_dir = staging_dir / "usr" / "share" / "applications"
    systemd_dir = staging_dir / "usr" / "lib" / "systemd" / "user"

    debian_dir.mkdir(parents=True, exist_ok=True)
    opt_jarvis.mkdir(parents=True, exist_ok=True)
    apps_dir.mkdir(parents=True, exist_ok=True)
    systemd_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy PyInstaller bundle to /opt/jarvis
    print(f"Copying application bundle to {opt_jarvis}...")
    shutil.copytree(bundle_dir, opt_jarvis, dirs_exist_ok=True)

    # Make main binary executable
    main_bin = opt_jarvis / "jarvis"
    if main_bin.exists():
        main_bin.chmod(0o755)

    # 2. Copy desktop shortcut
    desktop_src = PACKAGING_DIR / "linux" / "jarvis.desktop"
    if desktop_src.exists():
        shutil.copy(desktop_src, apps_dir / "jarvis.desktop")
        (apps_dir / "jarvis.desktop").chmod(0o644)

    # 3. Copy systemd service
    systemd_src = PACKAGING_DIR / "linux" / "systemd" / "jarvis-ollama.service"
    if systemd_src.exists():
        shutil.copy(systemd_src, systemd_dir / "jarvis-ollama.service")
        (systemd_dir / "jarvis-ollama.service").chmod(0o644)

    # 4. Copy and configure maintainer scripts
    scripts = ["postinst", "prerm", "postrm"]
    for s in scripts:
        src = PACKAGING_DIR / "linux" / "debian" / s
        if src.exists():
            dst = debian_dir / s
            shutil.copy(src, dst)
            dst.chmod(0o755)

    # 5. Calculate installed size in KB
    total_size_kb = 0
    for root, _, files in os.walk(staging_dir):
        for f in files:
            fp = Path(root) / f
            total_size_kb += fp.stat().st_size // 1024

    # 6. Generate control file with dynamic version and size
    control_src = PACKAGING_DIR / "linux" / "debian" / "control"
    with open(control_src, "r", encoding="utf-8") as f:
        control_text = f.read()

    control_text = control_text.replace("Version: 0.1.0", f"Version: {JARVIS_VERSION}")
    control_text = control_text.replace("Installed-Size: 180000", f"Installed-Size: {total_size_kb}")

    with open(debian_dir / "control", "w", encoding="utf-8") as f:
        f.write(control_text)
    (debian_dir / "control").chmod(0o644)

    print(f"✅ Staged Debian package (Installed Size: ~{total_size_kb // 1024} MB)\n")
    return staging_dir


def create_deb_package(staging_dir: Path) -> Path:
    """Invoke dpkg-deb to compile .deb artifact."""
    print("=" * 70)
    print("  🚀 [3/4] Compiling .deb Package via dpkg-deb")
    print("=" * 70)

    if not shutil.which("dpkg-deb"):
        raise RuntimeError("dpkg-deb utility not found. Please install dpkg (sudo apt install dpkg).")

    deb_filename = f"jarvis_{JARVIS_VERSION}_amd64.deb"
    deb_path = DIST_DIR / deb_filename
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    cmd = ["dpkg-deb", "--build", "--root-owner-group", str(staging_dir), str(deb_path)]
    print(f"Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    if not deb_path.exists():
        raise RuntimeError(f"Failed to create Debian package: {deb_path}")

    print(f"✅ Package built: {deb_path}\n")
    return deb_path


def audit_deb_package(deb_path: Path) -> None:
    """Inspect and report .deb structure and metadata."""
    print("=" * 70)
    print("  🔍 [4/4] Auditing Generated Debian Package")
    print("=" * 70)

    size_bytes = deb_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    sha256 = calculate_sha256(deb_path)

    print(f"  • File:     {deb_path.name}")
    print(f"  • Path:     {deb_path.resolve()}")
    print(f"  • Size:     {round(size_mb, 2)} MB ({size_bytes:,} bytes)")
    print(f"  • SHA256:   {sha256}")
    print("\n--- Package Info (dpkg-deb -I) ---")
    subprocess.run(["dpkg-deb", "-I", str(deb_path)], check=True)
    print("=" * 70)


def build() -> Path:
    """Run complete Linux Debian build pipeline."""
    bundle_dir = build_pyinstaller_bundle()
    staging_dir = stage_debian_package(bundle_dir)
    deb_path = create_deb_package(staging_dir)
    audit_deb_package(deb_path)
    return deb_path


if __name__ == "__main__":
    try:
        build()
    except Exception as e:
        print(f"\n❌ Build Failed: {e}", file=sys.stderr)
        sys.exit(1)
