# Installing J.A.R.V.I.S on Windows

## Method 1: Windows Installer (`JARVIS-Setup-x64.exe`) — Recommended

1. Download `JARVIS-Setup-x64.exe` from the latest release.
2. Double-click the installer and follow the setup wizard:
   - Choose install location (default: `C:\Program Files\JARVIS` or user AppData).
   - Check "Create a Desktop shortcut" (optional).
   - Check "Launch JARVIS on Windows startup" (optional).
3. Click **Install**.
4. Launch JARVIS from the Start Menu or Desktop shortcut.

---

## Method 2: Portable Package (`JARVIS-Portable-Windows-x64.zip`)

For environments where administrator permissions are restricted:

1. Download and extract `JARVIS-Portable-Windows-x64.zip`.
2. Open the extracted `JARVIS/` folder.
3. Run `jarvis.exe`.

---

## First Run & Local AI Model Setup

When launched for the first time:
1. **Hardware Detection**: Automatically detects your CPU cores, RAM, and GPU (NVIDIA RTX / AMD / Intel).
2. **Ollama Verification**: Checks if Ollama is running locally on `127.0.0.1:11434`. If not, starts the background service.
3. **Model Auto-Bootstrap**: Automatically imports the `jarvis-qwen` lightweight 1.5B/3B model.
4. **Ready**: The cyber holographic Cockpit appears and is ready for voice or text commands!

---

## Diagnostics & Troubleshooting

To run diagnostics:
```cmd
jarvis.exe --doctor
```

### Log File Location
Logs are saved in:
```
%LOCALAPPDATA%\JARVIS\logs\jarvis_YYYYMMDD.log
```

### User Configuration
Custom configuration is stored in:
```
%APPDATA%\JARVIS\config\config.json
```
