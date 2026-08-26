# Installing J.A.R.V.I.S on Linux (Debian / Ubuntu / Derivatives)

## Method 1: Installing Debian Package (`.deb`) — Recommended

Download `jarvis_<version>_amd64.deb` from the releases page and install via `apt`:

```bash
sudo apt install ./jarvis_0.1.0_amd64.deb
```

Or using `dpkg`:
```bash
sudo dpkg -i jarvis_0.1.0_amd64.deb
sudo apt-get install -f  # Fix missing system dependencies if any
```

---

## What Gets Installed

- **Main Application**: Installed to `/opt/jarvis/`
- **System Command**: `/usr/bin/jarvis` (global executable in PATH)
- **Desktop Entry**: `/usr/share/applications/jarvis.desktop`
- **Systemd User Service**: `/usr/lib/systemd/user/jarvis-ollama.service`

---

## Launching JARVIS

### 1. From Desktop Application Menu
Search for **JARVIS** or **Autonomous Cockpit** in your GNOME / KDE / XFCE application launcher.

### 2. From Terminal
```bash
jarvis
```

### 3. Run Self-Diagnostics
```bash
jarvis --doctor
```

### 4. Interactive CLI Mode
```bash
jarvis --cli
```

---

## Audio & Screen Automation Prerequisites
For full multimedia automation (screen grabbing, volume adjustments, microphone listening), ensure the following helper packages are present:

```bash
sudo apt install -y wmctrl xdotool ffmpeg libnotify-bin
```

---

## User Data & Storage Paths

In accordance with the XDG Base Directory specification:
- **Persistent Data & Memory DB**: `~/.local/share/jarvis/`
- **Configuration**: `~/.config/jarvis/config.json`
- **Logs**: `~/.local/state/jarvis/logs/`
- **Caches**: `~/.cache/jarvis/`

---

## Uninstallation

To remove the package while preserving your user configurations and memory:
```bash
sudo apt remove jarvis
```

To purge everything completely:
```bash
sudo apt purge jarvis
rm -rf ~/.local/share/jarvis ~/.config/jarvis ~/.local/state/jarvis
```
