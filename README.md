# Vibe Studio

An AI-native desktop IDE built on PySide6. The AI agent can autonomously read, search, edit, test, and repair your project — you describe what you want in plain language.

## What it actually does

```
User: "Login səhifəsinin backgroundunu dəyiş."

Agent:
  1. Scans project → detects framework/language
  2. Searches for "login" in filenames + symbols
  3. Reads the relevant file(s)
  4. Plans the minimal change
  5. Patches the file (conflict-safe)
  6. Runs validation (tests / lint)
  7. Self-corrects on failure (up to 3 cycles)
  8. Shows diff in Changes panel
  9. Reports result
```

The user does not need to know the filename, directory, framework, or CSS system.

---

## Requirements

- Python 3.10+
- PySide6
- [Ollama](https://ollama.ai) (recommended for local/private use) or any OpenAI-compatible API

```bash
pip install -e .
# or
pip install PySide6 requests
```

---

## Installation

```bash
git clone https://github.com/n4dlr/vibe-studio
cd vibe-studio
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

---

## Running

```bash
python -m vibe_studio
```

Or if installed as a script:

```bash
vibe-studio
```

---

## Ollama Setup

1. Install Ollama: https://ollama.ai/download
2. Pull a coding model:
   ```bash
   ollama pull qwen2.5-coder:7b   # recommended
   # or
   ollama pull llama3.1
   ollama pull deepseek-coder-v2:lite
   ```
3. Start Ollama (runs automatically on most systems)
4. Open Vibe Studio → the model list populates automatically

Ollama runs entirely locally — no data is sent to external servers.

---

## Remote API Setup

1. Open **Settings** (⚙ in the menu bar)
2. Set Provider to `openai-compatible`
3. Enter Base URL (e.g. `https://api.openai.com/v1`)
4. Enter API Key
5. Set Model name (e.g. `gpt-4o-mini`)

Or set environment variables:

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1   # optional
```

**Privacy note:** When using a remote provider, project file snippets are sent to that API. Use Ollama for private codebases.

---

## Architecture

```
vibe_studio/
├── agents/
│   ├── coding_agent.py        # AutonomousAgent — state machine, tool loop, self-correction
│   ├── tool_call_parser.py    # Multi-format parser: JSON/fenced/XML/OpenAI fn-call
│   └── output_processor.py   # Output truncation, error classification, deduplication
├── ai/
│   ├── chat_service.py        # Conversation history, provider wiring, streaming
│   └── model_manager.py       # Model discovery and selection
├── app/
│   ├── application.py         # Entry point
│   └── main_window.py         # VS Code-like main window
├── context/
│   └── context_engine.py      # Relevance ranking, token budgeting
├── core/
│   ├── command_safety.py      # Risk classification, workspace sandboxing
│   ├── project_memory.py      # Per-project persistent memory
│   └── settings.py            # AppSettings, SettingsStore
├── editor/
│   ├── editor_widget.py       # QPlainTextEdit with line numbers, syntax highlighting, QCompleter
│   ├── lsp_client.py          # JSON-RPC 2.0 stdio LSP client (pylsp, pyright, tsserver, gopls, clangd)
│   ├── code_intelligence.py   # Code intelligence engine with live LSP + AST/Regex fallback
│   ├── syntax_highlighter.py  # Multi-language highlighter
│   └── diff_viewer.py         # Unified diff viewer (accept/reject)
├── filesystem/
│   ├── file_watcher.py        # Real-time QFileSystemWatcher with 300ms debounced auto-refresh
│   └── project_manager.py     # Project open/close
├── git/
│   └── git_service.py         # Git status helper
├── project/
│   └── project_scanner.py     # AST + regex symbol index, framework detection
├── providers/
│   ├── base.py                # Protocol + ModelInfo + ProviderError
│   ├── capability_detector.py # Native tool-calling, context window, json_mode
│   ├── ollama_provider.py     # Ollama /api/chat + /api/generate, streaming
│   └── openai_compatible_provider.py  # SSE streaming, Bearer auth
├── security/
│   ├── path_security.py       # Workspace boundary enforcement
│   └── sensitive_file_detector.py     # Secret detection and redaction
├── terminal/
│   └── terminal_widget.py     # Multi-session terminal, cross-platform shell detection
├── tools/
│   ├── tool_registry.py       # Tool lifecycle: schema, risk, coercion, execution
│   ├── filesystem_tools.py    # list/read/write/create/delete/move/copy/rename
│   ├── search_tools.py        # text/regex/filename/symbol/references/imports
│   ├── patch_tools.py         # Patch/replace/insert/delete + conflict detection + undo
│   ├── terminal_tools.py      # execute_command/run_tests/run_build/run_linter
│   ├── git_tools.py           # status/diff/log/stage/unstage/commit/restore
│   └── code_tools.py          # detect_project_type/frameworks/dependencies
└── ui/
    ├── ai_activity_panel.py   # Real-time event feed
    ├── command_palette.py     # Ctrl+Shift+P
    ├── git_panel.py           # Stage/unstage/commit/restore UI
    ├── problems_panel.py      # Ruff/mypy/eslint/pytest output parser + navigate
    ├── search_panel.py        # Project-wide search with threading
    ├── test_runner_panel.py   # Test output + Run & Fix button
    └── theme.py               # Dark/light theme
```

### Agent State Machine

```
IDLE → ANALYZING → PLANNING → [WAITING_APPROVAL] → EXECUTING
     → OBSERVING → VALIDATING → [FIXING → EXECUTING] → REVIEWING → COMPLETED

Exits: FAILED | CANCELLED | BLOCKED
```

### Tool-Call Protocol

The agent sends tool calls in this JSON format:

```json
{
  "tool": "tool_name",
  "args": {
    "param": "value"
  }
}
```

Supported response formats (all parsed automatically):
- Fenced JSON block (` ```json ... ``` `)
- Bare JSON object in prose
- XML format (`<tool_call>`)
- OpenAI function-calling schema

Each tool call is schema-validated before execution.

### File Safety

Before patching any file, the agent records a hash of the file at read time. Before writing, it checks whether the file changed externally (conflict detection). If it did, it re-reads before patching — it never silently overwrites user edits.

All file operations are sandboxed to the open project directory. Path traversal (`../`), symlink escapes, and absolute path escapes are blocked.

---

## Supported Languages / Frameworks

Detection (not execution — graceful degradation for unsupported):

| Language       | Framework detection                    |
|----------------|----------------------------------------|
| Python         | Django, Flask, FastAPI, pytest, PySide6 |
| JavaScript     | React, Next.js, Vue, Angular, Express, Svelte |
| TypeScript     | Same as JS                             |
| Rust           | Cargo                                  |
| Go             | go modules                             |
| Java/Kotlin    | Maven, Gradle                          |
| C/C++          | CMake, Make                            |
| HTML/CSS       | — (always detected)                    |

---

## Agent Modes

| Mode | Behaviour |
|------|-----------|
| **Auto** | Safe operations execute automatically. Dangerous ops (delete, git destructive) log a warning. |
| **Plan** | Agent produces a plan and waits for user approval before executing. |
| **Ask** | Agent asks before each individual tool call. |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+P` | Command palette |
| `Ctrl+P` | Quick open file |
| `Ctrl+S` | Save current file |
| `Ctrl+N` | New file |
| `Ctrl+W` | Close tab |
| `Ctrl+B` | Toggle explorer |
| `Ctrl+Shift+F` | Find in project |
| `Ctrl+Shift+A` | Toggle AI panel |
| `Ctrl+\`` | Focus terminal |
| `Ctrl+Shift+T` | Run tests |
| `Ctrl+Enter` (in chat) | Send message |

---

## Security Model

- **Workspace boundary**: The agent cannot read or write files outside the open project directory.
- **Command risk levels**: `SAFE / LOW / MEDIUM / HIGH / CRITICAL`. Critical commands (e.g. `rm -rf /`) are blocked outright.
- **Secret redaction**: API keys, tokens, passwords are redacted before being sent to any remote provider.
- **Local-only mode**: Enable in Settings → Agent → "Local only". Ollama connection is tested first; if unavailable, the offline fallback is used. No data leaves the machine.
- **No auto-commit**: The agent never commits to Git automatically.

---

## Running Tests

```bash
# All tests (fast, offline)
VIBE_STUDIO_OFFLINE=1 pytest

# With coverage
VIBE_STUDIO_OFFLINE=1 pytest --cov=vibe_studio
```

Set `VIBE_STUDIO_OFFLINE=1` to skip real LLM calls and use the deterministic offline fallback. This is the default for CI.

To run tests against a real Ollama instance (slower):

```bash
pytest tests/test_integration.py  # will use running Ollama if available
```

---

## Features

- **Context Engine (Local RAG)**: AST file chunking, SQLite index (`.vibe_studio/index.db`), token budgeting, optional `sentence-transformers` vector search.
- **Multi-Agent Review**: Parallel candidate proposals via `ThreadPoolExecutor`, diff quality evaluated by `ReviewerAgent`.
- **Self-Healing Test Loop**: Auto-transitions to `FIXING` state on test failures; tracks traceback fingerprints to avoid infinite loops.
- **Plugin System (`@vibe_plugin`)**: `PluginManager` loads third-party tools from `.vibe_studio/plugins/` and registers them in `ToolRegistry`.
- **Local Network Streaming**: Live event streaming and peer IDE activity broadcasting via `APIServerHandler`.
- **Monorepo Incremental Scanner**: SQLite symbol index with hash-based incremental rescan; skips unchanged files.
- **LSP Code Intelligence**: `LSPContextProvider` pre-fetches symbol references and hover info before agent planning.
- **Workspace Sandboxing**: Host-native process isolation, workspace boundary enforcement (`PathSecurity`), audit logging.
- **Agent Activity Timeline**: Interactive UI cards showing agent reasoning steps and tool calls in real time.
- **Turbo Mode**: Compact prompt fast-paths for single-file edits; post-write auto-completion.
- **Project Memory**: SQLite-backed memory (`.vibe_studio/memory.db`) stores task history, error fixes, and context hints.
- **Chat Persistence**: Conversation history auto-saved to `.vibe_studio/chat_history.json`; Markdown export (`📥`).

### LSP Protocol & Fallback

- **Routing**: All go-to-definition, references, hover, completion, and symbol requests go through LSP first — falls back to AST (Python) or regex when LSP is unavailable or times out.
- **Server Discovery**: Auto-detects `pyright-langserver`, `pylsp`, `typescript-language-server`, `gopls`, `rust-analyzer`, `clangd`, `vscode-langservers-extracted`.
- **Document Sync**: Monotonic version increments across `didOpen`, `didChange`, `didSave`, `didClose`.
- **Diagnostics**: Live `textDocument/publishDiagnostics` piped to Problems Panel with click-to-navigate.
- **UI Safety**: GUI thread never blocks; all LSP calls have timeouts and stale-version guards.
- **Agent tools**: `lsp_goto_definition`, `lsp_find_references`, `lsp_hover`, `lsp_get_diagnostics`, `lsp_document_symbols`, `lsp_workspace_symbols`.

### Agent Pipeline

- **Orchestrator**: `AgentOrchestrator` wires `IntentPredictor` → `NavigatorAgent` → `ContextEngine` → `AutonomousAgent` → `ReviewerAgent` → `DebugAssistant`.
- **Code Intelligence**: Go-to-Definition (`F12`), hover docstrings, Find References, `QCompleter` (`Ctrl+Space`).
- **File Watching**: Auto-refreshes explorer, Git status, and open tabs on external changes; protects unsaved edits.
- **Large Projects**: Import-graph ranking + token budgeting handle 1000+ file codebases.
- **Offline Mode**: Deterministic rule-based fallback when Ollama or remote APIs are unavailable.

---

## ⚠️ Disclaimer & Security

### User Responsibility
**Vibe Studio** is a tool that provides AI-assisted code editing capabilities. The AI agent executes commands based on user input. **The user is solely responsible for:**

- All code changes made by the AI agent
- Any consequences resulting from executed commands
- Ensuring the safety and security of their codebase
- Reviewing all AI-suggested changes before accepting them

### No Warranty
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

### AI Safety Warnings
- **Never run Vibe Studio on production or critical systems without thorough testing**
- **Always review AI-generated code before committing or deploying**
- **The AI agent may produce incorrect, insecure, or harmful code**
- **Use Ollama in local-only mode for maximum privacy**
- **Enable "Plan Mode" to review and approve all AI actions**
- **Regularly backup your projects before using AI agents**

### Liability Waiver
By using Vibe Studio, you acknowledge and agree that:

1. **The author(s) assume NO LIABILITY** for any damages, data loss, security breaches, or legal issues arising from the use of this software
2. **The user assumes ALL RISKS** associated with AI-generated code
3. **The user is responsible** for complying with applicable laws and regulations
4. **The author(s) provide NO GUARANTEE** regarding code quality, security, or fitness for any purpose

### Security Features
Vibe Studio includes safety mechanisms, but these are **not foolproof**:
- Workspace boundary enforcement
- Command risk classification (SAFE → CRITICAL)
- Secret redaction for remote APIs
- Local-only mode (Ollama)

**These features are provided as additional safeguards, NOT as guarantees of security.**

---

## 📋 End-User Agreement (EULA)

By installing or using Vibe Studio, you agree to:

✅ Use the software responsibly and ethically  
✅ Not use the AI agent to create malware, exploits, or harmful code  
✅ Review all AI-suggested changes thoroughly  
✅ Backup your projects before executing AI operations  
✅ Accept full responsibility for all actions performed with Vibe Studio  
❌ Hold the authors harmless from any damages or liabilities  

> **Important:** Vibe Studio is an experimental AI tool. It is NOT certified for safety-critical applications, medical devices, nuclear facilities, or any environment where failure could cause harm.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

MIT License

Copyright (c) 2026 n4dlr

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