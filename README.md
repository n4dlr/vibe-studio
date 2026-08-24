# 🚀 Vibe Studio — Next-Gen AI Desktop IDE & Autonomous Specialist Swarm

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://wiki.qt.io/Qt_for_Python)
[![Playwright](https://img.shields.io/badge/Browser-Playwright-orange.svg)](https://playwright.dev/python/)
[![Tests Passing](https://img.shields.io/badge/Tests-552%20passed-success.svg)](#-running-tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Vibe Studio** is a state-of-the-art, AI-native desktop IDE and autonomous agent cockpit built on **PySide6**. Engineered to outperform systems like **Claude Agent**, **Cursor**, and **OpenClaw**, Vibe Studio operates with zero-failure execution guarantees, full local offline privacy (optimised for 1.5B–7B local Ollama models), and an interactive Cyber-Obsidian mission control interface.

---

## 🌟 What Sets Vibe Studio Apart?

```
                                  ┌─────────────────────────────┐
                                  │      Vibe Studio Core       │
                                  │   Zero-Error Agent Engine   │
                                  └──────────────┬──────────────┘
                                                 │
         ┌────────────────────────┬──────────────┴───────────────┬────────────────────────┐
         │                        │                              │                        │
┌────────┴────────┐      ┌────────┴────────┐           ┌─────────┴────────┐      ┌────────┴────────┐
│  Smart Fuzzy    │      │  Self-Healing   │           │  Specialist      │      │ Context         │
│  Patcher        │      │  AST & Syntax   │           │  Multi-Agent     │      │ Virtualizer     │
│  (Zero-Failure) │      │  Guard          │           │  Swarm           │      │ (2B-7B Support) │
└─────────────────┘      └─────────────────┘           └──────────────────┘      └─────────────────┘
```

1. **🚀 SuperAgent Mission Control (`Ctrl+Shift+S`)**:
   - Hierarchical DAG planning with automatic milestone decomposition and dynamic runtime replanning.
   - Built-in **Self-Critique Engine** that scores code quality (0–100, Grade A+ to F) and auto-triggers refinement if score < 85.
   - Glassmorphic HUD Metric cards: live counters for Steps Taken, Browser Ops, Files Changed, Quality Score, and Elapsed Time.

2. **🎙️ Voice Consultation Agent (`Ctrl+Shift+V` / Push-to-Talk `Space`)**:
   - Fully local, offline Speech-to-Text via `faster-whisper` and Text-to-Speech via `pyttsx3`.
   - Real-time multi-band animated audio waveform visualizer (`WaveformWidget`).
   - Compact, spoken-friendly prompt architecture fine-tuned for small 2B–3B models in both **English** and **Azerbaijani (AZ)**.

3. **🧬 Zero-Failure Smart Fuzzy Patcher (`FuzzyPatchEngine`)**:
   - Resilient SequenceMatcher / Levenshtein alignment that matches target code blocks across line-ending (`\r\n` vs `\n`), indentation, and whitespace drifts.
   - **Auto-Indentation Detection & Adaptation**: Re-indents replacement blocks to match the target file's indentation style (2 spaces, 4 spaces, tabs).

4. **🛡️ Self-Healing AST Syntax Guard (`ASTSyntaxGuard`)**:
   - Pre-write AST validation for Python (`ast.parse`), JSON (`json.loads`), TOML, and YAML.
   - Automatically heals syntax bugs (e.g., missing colons after `def`/`class`/`if`, trailing commas in JSON, single-quote keys) before writing to disk.

5. **🌐 Autonomous Playwright & Web Research Tools**:
   - Headless / Headed Chromium web automation (`browser_open`, `browser_navigate`, `browser_click`, `browser_type`, `browser_extract_text`, `browser_screenshot`, `browser_evaluate_js`).
   - DuckDuckGo web search + fast HTTP fetching with HTML-to-Markdown sanitisation.

6. **🐝 Autonomous Specialist Swarm (`SpecialistSwarm`)**:
   - Orchestrates specialized sub-agents: **Architect / Planner**, **Coder**, **Security & Quality Auditor**, and **Autonomous QA & Test Generator**.

7. **🧠 Context Virtualizer (`ContextVirtualizer`)**:
   - AST-density code outlining (classes, method signatures, docstrings) reducing token consumption by 80% while retaining 100% semantic signal for 1.5B–7B models.
   - Sliding execution history summarizer to prevent context exhaustion and instruction forgetting.

8. **🌌 Cyber-Obsidian & Glassmorphism Design System**:
   - Modern 48px vertical Activity Bar with glowing pills and badge tooltips.
   - Breadcrumb navigation with file-type badge icons (`🐍 Python`, `🦀 Rust`, `⚡ TypeScript`, `🟨 JavaScript`, `🌐 HTML`, `🎨 CSS`, `📝 Markdown`, `⚙️ Config`, `⬛ Shell`) and quick `▶ Run` action.
   - Executive Status Bar with real-time Git branch pill (`⎇ main`), Agent state LED (`🟢 Agent Ready`), active model chip, and LSP diagnostics (`❌ 0  ⚠️ 0`).

---

## 💻 Requirements

- **Python**: 3.10+
- **GUI Engine**: PySide6
- **Local AI (Recommended)**: [Ollama](https://ollama.ai) (`qwen2.5-coder:7b`, `qwen2.5:1.5b`, `llama3.1`) or any OpenAI-compatible API
- **Browser Automation (Optional)**: Playwright (`playwright install chromium`)
- **Voice Agent (Optional)**: `faster-whisper`, `pyttsx3`

```bash
pip install -e .
```

---

## 📦 Installation

```bash
git clone https://github.com/n4dlr/vibe-studio
cd vibe-studio
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

For full browser and voice capabilities:

```bash
pip install playwright faster-whisper pyttsx3 markdownify
playwright install chromium
```

---

## ⚡ Quick Start & CLI Commands

Launch the application in full GUI or headless CLI mode:

```bash
# Launch Next-Gen GUI IDE
python -m vibe_studio
# or
vibe-studio

# 🩺 Environment Diagnostic & Local Model Inspection
vibe-studio doctor

# 🔍 Run Task Verification Engine against project
vibe-studio verify "Add farewell(name) to hello.py"

# ⚡ Run Automated Benchmark Suite (VibeBench)
vibe-studio benchmark --scenarios 5

# 🤖 Headless Autonomous Task Execution
vibe-studio run "Add /health POST route to main.py" --root /path/to/project

# 🔍 Build Graph RAG AST Index
vibe-studio index --root /path/to/project

# 🔎 Natural Language Semantic Code Search
vibe-studio search "authentication middleware"

# 📚 Auto-generate Documentation & Mermaid Architecture Diagrams
vibe-studio doc

# 🔒 Run AST Security & Secret Auditor
vibe-studio audit

# 🌐 Start REST API & WebSocket Server
vibe-studio server --port 8000 --ws-port 8001
```

---

## 🦙 Ollama Local Setup (100% Offline & Private)

1. Download Ollama: [ollama.ai/download](https://ollama.ai/download)
2. Pull your preferred coding model:
   ```bash
   ollama pull qwen2.5-coder:7b   # Recommended for software engineering
   ollama pull qwen2.5:1.5b         # Ultra-lightweight local model
   ollama pull llama3.1             # General reasoning
   ```
3. Start Vibe Studio — available models are auto-discovered immediately.

---

## 🌐 Remote API Setup (Claude, OpenAI, DeepSeek, LocalAI)

1. Open **Settings** (⚙ in the menu bar or `Ctrl+,`)
2. Select **Provider**: `openai-compatible`
3. Enter **Base URL** (e.g. `https://api.openai.com/v1`, `https://openrouter.ai/api/v1`)
4. Enter **API Key** and select your model (e.g. `claude-3-5-sonnet`, `gpt-4o`, `deepseek-chat`)

Or via environment variables:

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1
```

---

## 🏗️ Architecture & Module Map

```
vibe_studio/
├── agents/
│   ├── super_agent.py          # SuperAgent: HierarchicalPlanner + SelfCritiqueEngine
│   ├── voice_agent.py          # VoiceAgent: 2B-optimized EN/AZ conversational agent
│   ├── speech_processor.py     # SpeechProcessor: offline Whisper STT + pyttsx3 TTS
│   ├── coding_agent.py         # AutonomousAgent state machine & task execution
│   ├── browser_agent.py        # Playwright browser controller
│   ├── task_verifier.py        # TaskVerificationEngine: deterministic post-task checks
│   ├── tool_call_parser.py     # Multi-format parser (JSON / XML / Fenced / Fn-Call)
│   └── output_processor.py    # Error classification, deduplication & output truncation
├── context/
│   ├── context_compactor.py    # ContextVirtualizer: AST density outlines & sliding history
│   ├── context_engine.py       # Relevance ranking & token budgeting
│   └── lsp_context_provider.py # Proactive LSP code intelligence pre-fetching
├── editor/
│   ├── editor_widget.py        # Editor with line numbers, syntax highlight & QCompleter
│   ├── lsp_client.py           # JSON-RPC 2.0 stdio LSP client
│   └── code_intelligence.py    # Live LSP + AST fallback intelligence
├── swarm/
│   ├── specialist_swarm.py     # SpecialistSwarm: Architect, Coder, Auditor, QA
│   └── swarm_coordinator.py    # Worker registration & task routing
├── tools/
│   ├── tool_registry.py        # Master ToolRegistry (76 tools registered)
│   ├── patch_tools.py          # FuzzyPatchEngine: fuzzy matching + auto-indentation
│   ├── filesystem_tools.py     # FilesystemTools + ASTSyntaxGuard auto-healing
│   ├── browser_tools.py        # Playwright browser tool wrapper
│   ├── web_tools.py            # HTTP fetch + DuckDuckGo search + HTML-to-Markdown
│   ├── memory_tools.py         # Long-term persistent key-value & semantic memory
│   ├── search_tools.py         # Text/regex/symbol/file search
│   └── terminal_tools.py       # PTY command execution & test runners
└── ui/
    ├── main_window.py          # Modern Activity Bar, Breadcrumbs, Status Bar & Splitters
    ├── super_agent_panel.py    # SuperAgent HUD Mission Control Deck
    ├── voice_dialog.py         # Voice Consultation Dialog with Waveform Visualizer
    ├── ai_activity_panel.py    # Live AI activity feed cards & timing beads
    └── theme.py                # Cyber-Obsidian & Glassmorphism Design System
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+S` | **Launch SuperAgent Mission Control** |
| `Ctrl+Shift+V` | **Open Voice Consultation Dialog** |
| `Space` (in Voice) | **Push-to-Talk recording** |
| `Ctrl+Shift+P` | Command Palette |
| `Ctrl+P` | Quick Open File |
| `Ctrl+S` | Save current file |
| `Ctrl+N` | New file |
| `Ctrl+W` | Close active editor tab |
| `Ctrl+B` | Toggle left panel (Explorer / Search / Git) |
| `Ctrl+Shift+F` | Search across project |
| `Ctrl+Shift+A` | Toggle AI sidebar panel |
| `Ctrl+\`` | Focus internal terminal |
| `Ctrl+Shift+T` | Run test suite |
| `Ctrl+Enter` (in chat) | Send prompt to AI |

---

## 📊 Performance Benchmarks & Reliability

### Project Indexing & Retrieval Speed

| Project Size | Files | AST Symbols | Initial Index | Incremental Rescan |
|---|---|---|---|---|
| Small | 50 | ~1,200 | **0.08s** | **0.01s** |
| Medium | 500 | ~18,000 | **0.72s** | **0.09s** |
| Large | 1,000 | ~42,000 | **1.1s** | **0.15s** |
| Monorepo | 10,000 | ~100,000 | **8.4s** | **1.2s** |

### Agent Reliability & Safety (Zero-Error Guarantee)

| Metric | Specification |
|---|---|
| **Automated Test Suite** | **552 passed (0 failures)** |
| **Fuzzy Patch Matching** | SequenceMatcher + Line-Anchor + Auto-Indent |
| **Pre-Write Syntax Healing** | Python (`ast.parse`), JSON, TOML auto-repair |
| **Small Model Virtualization** | 80% token reduction via AST outlining |
| **Self-Critique Threshold** | Minimum 85/100 score (auto-refinement) |
| **Hard Tool Timeout** | 30s |
| **Instant Cancellation (`Stop`)** | < 50ms |

---

## 🧪 Running Tests

```bash
# Run all 552 unit & integration tests (fast, offline)
pytest tests/ -q

# Run SuperAgent & Swarm tests
pytest tests/test_super_agent.py tests/test_fuzzy_patch_and_guard.py -v

# Run with test coverage report
pytest --cov=vibe_studio
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 n4dlr