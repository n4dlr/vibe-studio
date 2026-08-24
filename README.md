# 🚀 Vibe Studio — Autonomous AI IDE, J.A.R.V.I.S OS, Obsidian Graph & n8n Automation Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://wiki.qt.io/Qt_for_Python)
[![Playwright](https://img.shields.io/badge/Browser-Playwright-orange.svg)](https://playwright.dev/python/)
[![Tests Passing](https://img.shields.io/badge/Tests-602%20passed-success.svg)](#-running-tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Vibe Studio** is a next-generation AI-native desktop IDE that unifies:
1. **🤖 J.A.R.V.I.S Autonomous Desktop & Voice OS** (Arc Reactor HUD, Windows Aero edge snapping, bilingual Azerbaijani/English neural voice, full agentic coding, WhatsApp/Telegram integration, screen locking & hardware telemetry).
2. **The Autonomous Execution Power of Claude Agent & Devin** (Zero-failure AST guard, smart fuzzy patcher, specialist multi-agent swarm).
3. **The Knowledge & Physics Code Graph of Obsidian** (Interactive 2D force-directed dependency graph, bidirectional `[[WikiLinks]]`, infinite `.canvas` whiteboard).
4. **The Visual Automation & Pipeline Power of n8n** (DAG node-based workflows, automated triggers, Playwright web actions, SuperAgent auto-repair, and live execution playback).
5. **Persistent Cross-Session Learning** (`AgentMemoryGraph` & ADR recorder that gets smarter with every task).

---

## ⚡ Tez və Rahat Başlatma Komandaları (Quick Start)

### 1. 🤖 J.A.R.V.I.S Standalone Cockpit (Birbaşa J.A.R.V.I.S Pəncərəsini Açmaq)
```bash
# Modul kimi (Ən rahat yol):
python3 -m vibe_studio --jarvis

# Və ya CLI vasitəsilə:
vibe-studio jarvis
# və ya
vibe-studio --jarvis
```

### 2. 🌌 Vibe Studio IDE (Əsas Proqramlaşdırma Mühitini Açmaq)
```bash
# Modul kimi:
python3 -m vibe_studio

# Və ya CLI vasitəsilə:
vibe-studio gui
```

### 3. 🌐 Web UI & REST API Serveri
```bash
vibe-studio server --port 8000
```

---

## 🌟 The 5 Core Powerhouses of Vibe Studio

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 VIBE STUDIO TITAN PLATFORM                              │
├───────────────────────────────┬───────────────────────────────┬─────────────────────────┤
│       J.A.R.V.I.S COCKPIT     │       OBSIDIAN SYSTEM         │         N8N ENGINE      │
│  - Holographic Arc Reactor    │  - Interactive Physics Graph  │  - Node-Based Pipelines │
│  - Windows Aero Edge Snapping │  - Bidirectional WikiLinks    │  - Triggers & Actions   │
│  - Bilingual Voice (AZ / EN)  │  - Markdown Whiteboard Canvas │  - Live Variable State  │
│  - Full Agentic OS Automation │  - ADR & Code Architecture    │  - Visual Node Studio   │
└───────────────────────────────┴───────────────────────────────┴─────────────────────────┘
```

---

## 🤖 1. J.A.R.V.I.S Autonomous Desktop & Voice OS (`src/vibe_studio/jarvis/`)

J.A.R.V.I.S istifadəçinin bütün kompüterini və proqramlaşdırma prosesini idarə edən **tam agentik süni intellektdir**.

### 🎮 J.A.R.V.I.S Əmr Bələdçisi (Səslə və ya Mətnlə):

| Kateqoriya | Nümunə Əmrlər | Nəticə |
|---|---|---|
| **🔒 Cihaz Təhlükəsizliyi** | `cihazı kilidlə` / `lock screen` | Linux sessiyasını dərhal kilidləyir |
| **📞 WhatsApp Zəngi** | `whatsapdan tuncayi ara` / `call tuncay on whatsapp` | Birbaşa WhatsApp-da zəng pəncərəsini açır |
| **💬 WhatsApp Mesajı** | `whatsapdan tuncaya yaz salam necesen` | Mesajı hazırlayıb WhatsApp-da açır |
| **✈️ Telegram Çatı** | `telegramdan tuncaya yaz salam` | Telegram-da birbaşa çat açır |
| **📇 Kontakt Kitabçası** | `save contact tuncay +994501234567` | Kontaktı `~/.jarvis_contacts.json` daxilində yadda saxlayır |
| **🎮 Oyun və Tətbiqlər** | `go desktop and open tlauncher`, `open steam`, `open brave` | Masaüstü qısayollarını (`.desktop`) və proqramları açır |
| **☀️ Canlı Hava** | `hava necədir`, `Bakıda hava` | Real-vaxt hava temperaturunu deyir |
| **💡 Ekran Parlaqlığı** | `ekran parlaqlığını 80 faiz et`, `set brightness to 70` | Ekran parlaqlığını dərhal tənzimləyir |
| **🎵 Musiqi İdarəsi** | `musiqini dayandır`, `musiqini oxut`, `növbəti mahnı` | Spotify, Brauzer və media pleyerləri idarə edir |
| **⏰ Saat və Tarix** | `saat neçədir`, `bu gün ayın neçəsidir` | Dəqiq vaxt və tarixi səsli oxuyur |
| **💤 Yuxu Rejimi** | `yuxu rejimi`, `suspend pc` | Kompüteri dərhal yuxu rejiminə keçirir |
| **🚀 Sürət Testi** | `open browser and test internet speed test on fast.com` | Brave brauzerində Fast.com-u açır və ping-i yoxlayır |
| **💻 Agentic Kodlama** | `Mənə bir FastAPI serveri yaz`, `run tests` | Fayllar yaradır, kod yazır, terminal əmrlərini icra edir |

### 🪟 Windows Aero Edge Snapping:
- J.A.R.V.I.S müstəqil detached pəncərədir (`JarvisStandaloneWindow`).
- Pəncərəni **ekranın soluna çəkdikdə** 50% sol yarıya yapışır (`◧`).
- **Sağına çəkdikdə** 50% sağ yarıya yapışır (`◨`).
- **Yuxarıya çəkdikdə** tam ekran böyüyür (`◻`).
- Hər kənara **25px maqnit cəzbetməsi** var.

---

## 🕸️ 2. Obsidian-Grade Knowledge & Physics Code Graph (`src/vibe_studio/knowledge/graph_engine.py`)
- **AST Dependency Graphing**: Scans classes, functions, modules, and imports across Python, TypeScript, Rust, and Go.
- **Obsidian `[[WikiLinks]]`**: Bidirectional backlinks between Markdown architecture docs and source code.
- **PageRank & Degree Centrality**: Mathematically identifies the most critical architectural hubs in your codebase.
- **Interactive Force-Directed Canvas (`KnowledgeGraphPanel`)**: Real-time Coulomb-Hooke physics simulation with glowing hub nodes, search filters, zoom/pan, and double-click to navigate in the editor.

---

## ⚡ 3. n8n-Grade Visual Automation Studio (`src/vibe_studio/workflow/engine.py`)
- **DAG Execution Pipeline**: Connect triggers and actions with topological order and error isolation.
- **Supported Nodes**:
  - **Triggers**: `ManualTrigger`, `CronTrigger`, `FileWatchTrigger`, `GitHookTrigger`.
  - **AI & Automation**: `SuperAgentAction`, `PlaywrightBrowserAction`, `PythonScript`, `ShellCommand`, `HttpRequest`, `NotificationAction`.
  - **Logic & Flow**: `ConditionBranch` (If/Else), `LoopIterator`, `DelayTimer`.
- **Live Variable State**: Automatic `$json`, `$prev`, and `$env` data passing between nodes.

---

## 🧠 4. Persistent Agent Memory Graph & ADRs (`src/vibe_studio/knowledge/memory_graph.py`)
- **Cross-Session Learning**: The agent automatically records task outcomes, error fixes, and code patterns to a SQLite knowledge base. Every run starts with context from past fixes!
- **ADR Browser (`MemoryGraphPanel`)**: Create and browse Architecture Decision Records directly in the IDE.

---

## 💻 Quraşdırma (Installation)

```bash
git clone https://github.com/n4dlr/vibe-studio
cd vibe-studio
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install playwright faster-whisper edge-tts sounddevice numpy markdownify
playwright install chromium
```

---

## ⌨️ Əsas Qısayol Düymələri (Keyboard Shortcuts)

| Qısayol | Funksiya |
|---|---|
| `Ctrl+Shift+J` | **🤖 J.A.R.V.I.S Cyber Cockpit (Ayrı Pəncərə)** |
| `Ctrl+Shift+E` | **📁 Fayl Bələdçisi (Explorer)** |
| `Ctrl+Shift+F` | **🔍 Layihə Boyu Qlobal Axtarış** |
| `Ctrl+Shift+G` | **⎇ Git Mənbə Nəzarəti** |
| `Ctrl+Shift+S` | **🚀 SuperAgent Missiya Mərkəzi** |
| `Ctrl+\`` | **⬛ İnteqrasiya Edilmiş Terminal** |

---

## 🧪 Running Tests

```bash
# Bütün 602 vahid və inteqrasiya testlərini icra etmək:
.venv/bin/pytest tests/ -q

# Yalnız J.A.R.V.I.S testlərini yoxlamaq:
.venv/bin/pytest tests/test_jarvis.py -v
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 n4dlr