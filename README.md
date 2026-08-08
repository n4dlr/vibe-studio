# Vibe Studio — Autonomous AI Desktop IDE

> **A local-first, production-grade AI-powered coding IDE built with PySide6.**  
> Understands your codebase, executes real tools, edits files, runs tests, and self-corrects — all autonomously.

---

## What is Vibe Studio?

Vibe Studio is a VS Code-inspired desktop IDE where an autonomous AI agent actively helps you write, debug, refactor, and understand code. Unlike simple chat-based assistants, the agent:

- **Reads and edits your actual files** — no copy-paste needed
- **Runs tests and fixes failures automatically**
- **Searches symbols, imports, and references** across the whole project
- **Executes shell commands, linters, and formatters**
- **Uses Git** — diffs, logs, branches, commits
- **Self-corrects on errors** — if a tool fails, the agent retries with a fix
- **Works fully offline** with a local Ollama instance

---

## Features

### 🤖 Autonomous AI Agent
- 11-state finite state machine: `IDLE → ANALYZING → PLANNING → EXECUTING → OBSERVING → VALIDATING → FIXING → COMPLETED`
- Multi-step tool execution loop (up to 15 iterations per task)
- Natural language task understanding (English, Azerbaijani, and other languages)
- Self-correction loop — automatically retries on test or build failures
- Three autonomy modes: **Auto**, **Plan** (wait for approval), **Ask** (confirm each step)

### 🛠️ Full Tool Suite
| Category | Tools |
|----------|-------|
| **Filesystem** | `create_file`, `read_file`, `write_file`, `delete_file`, `move_file`, `copy_file`, `rename_file`, `tree` |
| **Search** | `search_text`, `search_regex`, `search_filename`, `search_symbol`, `find_references`, `find_definition` |
| **Code Analysis** | `detect_language`, `detect_framework`, `detect_dependencies`, `detect_entry_points`, `detect_test_framework` |
| **Editing** | `patch_file`, `replace_text`, `insert_text`, `delete_text` |
| **Terminal** | `execute_command`, `run_tests`, `run_linter`, `run_formatter`, `run_build` |
| **Git** | `git_status`, `git_diff`, `git_log`, `git_branch`, `git_commit`, `git_checkout` |

### 🖥️ VS Code-like Desktop Interface
- **Left sidebar**: File Explorer + Git panel
- **Center**: Multi-tab code editor with syntax highlighting and line numbers
- **Right dock**: AI chat, live agent activity feed, model/mode selector, Stop and Undo buttons
- **Bottom panel**: Multi-tab terminal, Problems list, Test Runner
- **Command Palette**: `Ctrl+Shift+P`
- **Right-click AI actions**: Explain, Fix, Refactor, Generate Tests, Add Documentation
- **Diff Viewer**: Side-by-side unified diff with Accept/Reject

### 🔒 Security
- **Workspace sandboxing** — all file operations are restricted to your project directory (path traversal blocked)
- **Secret redaction** — API keys and tokens are stripped from prompts before sending to any LLM
- **Risk-level command classifier** — `LOW / MEDIUM / HIGH / CRITICAL` with destructive command blocking
- **Sensitive file detection** — `.env`, credentials, SSH keys flagged before AI access

### 🔌 AI Provider Support
- **Ollama** (local) — automatic model discovery, auto-selects a running model if the default is unavailable
- **OpenAI-compatible** — any OpenAI API endpoint (GPT-4, Claude via proxy, etc.)
- Streaming responses with live activity feed

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

### 2. Set up Ollama (recommended for local use)

```bash
# Install from https://ollama.com, then pull a model:
ollama pull qwen2.5-coder:7b      # Good balance of speed and quality
# or
ollama pull qwen3:8b
# or
ollama pull deepseek-coder-v2:lite
```

Vibe Studio connects to `http://127.0.0.1:11434` automatically and populates the model selector.

### 3. Launch

```bash
python -m vibe_studio
```

---

## Example Tasks

Type these directly into the AI chat input:

```
Analyze this project and summarize the architecture.
Run the tests and automatically fix any failures.
Create a file with numbers 1 to 20, one per line.
Delete numbers.txt
Login page-in backgroundunu dəyiş.        ← Azerbaijani works too
Bu layihədə bütün TypeScript errorlarını düzəlt.
Add dark mode to this page.
Refactor the auth module to use dependency injection.
```

---

## OpenAI / Custom API Setup

```bash
export OPENAI_API_KEY="sk-..."
export CUSTOM_API_KEY="..."        # For custom OpenAI-compatible endpoints
```

Configure the base URL through the app Settings dialog.

---

## Development

```bash
pip install -e .[dev]
pytest                              # Run all 15 tests
pytest tests/test_tools.py -v       # Run specific test file
```

### Running tests (headless)

```bash
QT_QPA_PLATFORM=offscreen pytest tests/
```

---

## Project Structure

```
src/vibe_studio/
├── agents/         ← Autonomous agent state machine & execution loop
├── ai/             ← ChatService, ModelManager
├── app/            ← MainWindow (VS Code-like desktop layout)
├── context/        ← Multi-factor relevance ranking for prompt context
├── core/           ← Settings, command safety, project memory
├── editor/         ← Code editor, syntax highlighter, diff viewer
├── providers/      ← Ollama, OpenAI-compatible providers
├── project/        ← Multi-ecosystem project scanner (AST + regex)
├── security/       ← Path sandboxing, secret redaction
├── terminal/       ← Embedded terminal widget
├── tools/          ← Full tool suite (filesystem, search, git, terminal, patch)
└── ui/             ← Command palette, panels, activity feed
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `xcb plugin error` on Linux | `sudo apt-get install -y libxcb-cursor0` |
| No desktop session | Set `QT_QPA_PLATFORM=offscreen` (auto-detected) |
| Ollama unavailable | Configure OpenAI-compatible provider in Settings |
| Model not loading | Vibe Studio auto-selects another running model |
| PySide6 install fails | `pip install --upgrade pip && pip install PySide6` |

---

## License

MIT License — Copyright (c) 2026 Vibe Studio

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
