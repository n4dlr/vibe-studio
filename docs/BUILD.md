# Building J.A.R.V.I.S from Source

This guide covers building production-ready standalone packages for Linux and Windows.

---

## 1. Prerequisites

### Universal Requirements
- Python 3.11 or 3.12 (64-bit)
- `pip`, `setuptools >= 68.0`, `wheel`
- `PyInstaller >= 6.0`

### Linux Build Host Requirements
- Ubuntu 22.04+, Debian 12+, Fedora 38+, Arch Linux
- `dpkg-dev` (for `dpkg-deb`)
- System libraries: `libgl1`, `libegl1`, `libasound2-dev`

```bash
sudo apt-get update
sudo apt-get install -y dpkg-dev build-essential libasound2-dev libgl1-mesa-dev
```

### Windows Build Host Requirements
- Windows 10/11 x64
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (for building `JARVIS-Setup-x64.exe`)

---

## 2. Quick Build Commands

### Build Everything for Current Platform
```bash
python build_all.py
```

### Build Linux Debian Package (`.deb`)
```bash
python build_linux.py
```
**Output**: `dist/jarvis_<version>_amd64.deb`

### Build Windows Packages (`.exe` Installer + `.zip` Portable)
```bash
python build_windows.py
```
**Output**:
- `dist/JARVIS-Setup-x64.exe`
- `dist/JARVIS-Portable-Windows-x64.zip`

### Unified CLI
```bash
python -m packaging.build --target [linux|windows|portable|all]
```

---

## 3. Build Pipeline Details

1. **PyInstaller Compilation**:
   - Bundles Python runtime, Qt6 / PySide6 shared libraries, and audio/vision tool modules into `dist/jarvis/`.
   - Strips non-essential developer and testing dependencies.

2. **Debian Package Assembly** (Linux):
   - Copies bundle to staging directory `/opt/jarvis/`.
   - Generates `/usr/share/applications/jarvis.desktop`.
   - Links maintainer scripts (`postinst`, `prerm`, `postrm`).
   - Compiles package using `dpkg-deb --build --root-owner-group`.

3. **Inno Setup Compilation** (Windows):
   - Packages `dist/jarvis` directory into a modern wizard installer.
   - Configures Start Menu shortcuts and uninstaller.
