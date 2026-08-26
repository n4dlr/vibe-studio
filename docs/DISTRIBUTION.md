# JARVIS Packaging, Architecture & Distribution Reference

## 1. System Architecture

```
Installed System Architecture
=============================
JARVIS Application
│
├── Runtime / Packaged Python Core (/opt/jarvis or C:\Program Files\JARVIS)
│     ├── PySide6 Qt6 GUI Engine (Windows Aero Edge Snapping, Holographic HUD)
│     ├── Autonomous Agent Engine (Task Planning, Reasoning, Code Execution)
│     ├── Native Tool Registry (Filesystem, Terminal, Patching, Browser, Web)
│     ├── PermissionBroker (Mandatory authorization layer for destructive actions)
│     ├── Memory System (SQLite episodic memory, Graph RAG, checkpoints)
│     ├── Bilingual Neural Voice Engine (Edge-TTS / pyttsx3, sounddevice, Whisper)
│     ├── Computer Vision & Screen Tools (Screenshots, visual coordinate locator)
│     ├── Hardware Telemetry & Auto-Tuning (CPU, RAM, NVIDIA CUDA, AMD ROCm)
│     └── Ollama Lifecycle Supervisor (Safe 127.0.0.1 binding, auto-start, health checks)
│
├── Local AI Model (`jarvis-qwen`)
│     ├── Base Architecture: Qwen2.5-Coder-1.5B-Instruct
│     ├── Format: GGUF Q4_K_M (~986 MB)
│     ├── License: Apache 2.0 (Permissive Redistribution)
│     └── Modelfile: Custom JARVIS personality & tool-calling system prompt
│
└── User State & Storage (Isolated from application binaries)
      ├── Linux: ~/.local/share/jarvis, ~/.config/jarvis, ~/.local/state/jarvis/logs
      └── Windows: %LOCALAPPDATA%\JARVIS, %APPDATA%\JARVIS
```

---

## 2. Package Size Breakdown

| Component | Approximate Size | Optimization Strategy |
|---|---|---|
| **Python Runtime & Core Binaries** | ~85 MB | Excluded bloated dev libraries (pytest, mypy, matplotlib) |
| **Qt6 / PySide6 GUI Engine** | ~140 MB | Kept essential GUI plugins (xcb, wayland, windows) |
| **Audio, Speech & Tools** | ~25 MB | Native sounddevice, edge-tts streaming, no bulky static weights |
| **Local Model (`jarvis-qwen` GGUF)**| ~986 MB | High efficiency Q4_K_M quantization |
| **Modelfiles & Assets** | ~2 MB | Minified configs and templates |
| **Total Installed Footprint** | **~1.23 GB** | Well below 2.5 GB target budget |
| **Compressed Installer / Debian .deb**| **~180 MB** (App) + GGUF | Ultra-fast download & installation |

---

## 3. Security & Permission Architecture

1. **Localhost Isolation**: Ollama runtime binds strictly to `127.0.0.1:11434`. It is never exposed to external network interfaces by default.
2. **Permission Broker**: High-risk actions (file deletion, terminal commands, process termination) are routed through `PermissionBroker`. Packaging does NOT bypass or weaken any permission checks.
3. **Secret Masking**: All credentials, tokens, and sensitive configuration values are automatically masked in diagnostic logs and output streams.
4. **Least Privilege**: The application runs completely in user space without requiring root or administrator privileges during normal execution.
