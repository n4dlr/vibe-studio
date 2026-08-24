# 🚀 Vibe Studio — Autonomous AI IDE, J.A.R.V.I.S OS, Obsidian Graph & n8n Automation Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://wiki.qt.io/Qt_for_Python)
[![Playwright](https://img.shields.io/badge/Browser-Playwright-orange.svg)](https://playwright.dev/python/)
[![Tests Passing](https://img.shields.io/badge/Tests-579%20passed-success.svg)](#-running-tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Vibe Studio** is a next-generation AI-native desktop IDE that unifies:
1. **🤖 J.A.R.V.I.S Autonomous Desktop & Voice OS** (Arc Reactor HUD, real-time hardware telemetry, app control, voice speech synthesis & diagnostics).
2. **The Autonomous Execution Power of Claude Agent & Devin** (Zero-failure AST guard, smart fuzzy patcher, specialist multi-agent swarm).
3. **The Knowledge & Physics Code Graph of Obsidian** (Interactive 2D force-directed dependency graph, bidirectional `[[WikiLinks]]`, infinite `.canvas` whiteboard).
4. **The Visual Automation & Pipeline Power of n8n** (DAG node-based workflows, automated triggers, Playwright web actions, SuperAgent auto-repair, and live execution playback).
5. **Persistent Cross-Session Learning** (`AgentMemoryGraph` & ADR recorder that gets smarter with every task).

---

## 🌟 The 5 Core Powerhouses of Vibe Studio

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 VIBE STUDIO TITAN PLATFORM                              │
├───────────────────────────────┬───────────────────────────────┬─────────────────────────┤
│       J.A.R.V.I.S COCKPIT     │       OBSIDIAN SYSTEM         │         N8N ENGINE      │
│  - Holographic Arc Reactor    │  - Interactive Physics Graph  │  - Node-Based Pipelines │
│  - Real-Time Telemetry Gauges │  - Bidirectional WikiLinks    │  - Triggers & Actions   │
│  - Spoken Voice Speech (TTS)  │  - Markdown Whiteboard Canvas │  - Live Variable State  │
│  - OS & App Control Engine    │  - ADR & Code Architecture    │  - Visual Node Studio   │
└───────────────────────────────┴───────────────────────────────┴─────────────────────────┘
```

### 1. 🤖 J.A.R.V.I.S Autonomous Desktop & Voice OS (`src/vibe_studio/jarvis/`)
- **Cyber-Holographic Arc Reactor HUD (`JarvisHUDPanel`)**: Pulsing energy reactor with rotating rings and dynamic frequency waves.
- **Spoken Voice Speech (TTS)**: Offline local text-to-speech feedback with authentic JARVIS personality.
- **Live Hardware Telemetry (`SystemTelemetry`)**: Real-time CPU, RAM, Disk, GPU, and Battery status monitoring.
- **OS & App Control Engine (`JarvisSystemTools`)**: Launch browser, open native apps, take screenshots, manage audio volume, and search the web.
- **Quick Keyboard Shortcut**: Press `Ctrl+Shift+J` or click `🤖` in the Activity Bar to engage JARVIS.

### 2. 🕸️ Obsidian-Grade Knowledge & Physics Code Graph (`src/vibe_studio/knowledge/graph_engine.py`)
- **AST Dependency Graphing**: Scans classes, functions, modules, and imports across Python, TypeScript, Rust, and Go.
- **Obsidian `[[WikiLinks]]`**: Bidirectional backlinks between Markdown architecture docs and source code.
- **PageRank & Degree Centrality**: Mathematically identifies the most critical architectural hubs in your codebase.
- **Interactive Force-Directed Canvas (`KnowledgeGraphPanel`)**: Real-time Coulomb-Hooke physics simulation with glowing hub nodes, search filters, zoom/pan, and double-click to navigate in the editor.

### 2. 📋 Obsidian-Style Infinite Whiteboard Canvas (`src/vibe_studio/knowledge/canvas_engine.py`)
- Compatible with the **Obsidian `.canvas` format**.
- Sticky notes, code blocks, connected arrows, and AI reasoning cards in an infinite 2D thinking space.

### 3. ⚡ n8n-Grade Visual Automation Studio (`src/vibe_studio/workflow/engine.py`)
- **DAG Execution Pipeline**: Connect triggers and actions with topological order and error isolation.
- **Supported Nodes**:
  - **Triggers**: `ManualTrigger`, `CronTrigger`, `FileWatchTrigger`, `GitHookTrigger`.
  - **AI & Automation**: `SuperAgentAction`, `PlaywrightBrowserAction`, `PythonScript`, `ShellCommand`, `HttpRequest`, `NotificationAction`.
  - **Logic & Flow**: `ConditionBranch` (If/Else), `LoopIterator`, `DelayTimer`.
- **Live Variable State**: Automatic `$json`, `$prev`, and `$env` data passing between nodes.
- **Visual Studio (`WorkflowPanel`)**: Draggable node cards, glowing cables, live step-by-step playback with glowing animation, and parameter inspector.

### 4. 🧠 Persistent Agent Memory Graph & ADRs (`src/vibe_studio/knowledge/memory_graph.py`)
- **Cross-Session Learning**: The agent automatically records task outcomes, error fixes, and code patterns to a SQLite knowledge base. Every run starts with context from past fixes!
- **ADR Browser (`MemoryGraphPanel`)**: Create and browse Architecture Decision Records directly in the IDE.

---

## 🚀 Autonomous Coding Engine (Beyond Claude Agent & OpenClaw)

- **🧬 Zero-Failure Smart Fuzzy Patcher (`FuzzyPatchEngine`)**: SequenceMatcher-based fuzzy matching with auto-indentation alignment.
- **🛡️ Pre-Write AST Syntax Guard (`ASTSyntaxGuard`)**: Validates and auto-repairs Python syntax (`ast.parse`), JSON, and TOML before writing to disk.
- **🐝 Specialist Multi-Agent Swarm (`SpecialistSwarm`)**: Dedicated Architect, Coder, Security Auditor, and Autonomous QA roles.
- **🎙️ Voice Consultation Agent (`Ctrl+Shift+V` / Push-to-Talk `Space`)**: Local offline STT (`faster-whisper`), TTS (`pyttsx3`), and real-time waveform visualizer (English & Azerbaijani support).
- **🧠 Context Virtualizer (`ContextVirtualizer`)**: AST-density outlining that reduces token overhead by 80% for 1.5B–7B local Ollama models.

---

## 💻 Requirements & Installation

- **Python**: 3.10+
- **GUI Engine**: PySide6
- **Local AI (Recommended)**: [Ollama](https://ollama.ai) (`qwen2.5-coder:7b`, `qwen2.5:1.5b`, `llama3.1`) or OpenAI-compatible API
- **Browser Automation (Optional)**: Playwright (`playwright install chromium`)
- **Voice Agent (Optional)**: `faster-whisper`, `pyttsx3`

```bash
git clone https://github.com/n4dlr/vibe-studio
cd vibe-studio
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install playwright faster-whisper pyttsx3 markdownify
playwright install chromium
```

---

## ⌨️ Activity Bar & Keyboard Shortcuts

| Icon / Shortcut | Feature |
|---|---|
| `📁` `Ctrl+Shift+E` | File Explorer |
| `🔍` `Ctrl+Shift+F` | Full Project Search |
| `⎇` `Ctrl+Shift+G` | Git Source Control |
| `🕸️` **Graph** | **Obsidian Knowledge & Code Physics Graph** |
| `⚡` **Workflows** | **n8n Visual Automation Studio** |
| `📋` **Canvas** | **Obsidian Infinite Whiteboard Canvas** |
| `🧠` **Memory** | **Agent Memory Graph & ADR Browser** |
| `🚀` `Ctrl+Shift+S` | **SuperAgent Mission Control Kokpit** |
| `🎙️` `Ctrl+Shift+V` | **Voice Consultation Dialog (Push-to-Talk `Space`)** |
| `⬛` `Ctrl+\`` | Integrated Multi-Session Terminal |

---

## 🧪 Running Tests

```bash
# Run all 566 unit & integration tests
pytest tests/ -q

# Run Knowledge Graph & Workflow tests
pytest tests/test_knowledge_and_workflow.py -v
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 n4dlr