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
│   ├── editor_widget.py       # QPlainTextEdit with line numbers, syntax highlighting
│   ├── syntax_highlighter.py  # Multi-language highlighter
│   └── diff_viewer.py         # Unified diff viewer (accept/reject)
├── filesystem/
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

## Completed 9/10 Production IDE Capabilities & Architecture

- **Multi-Agent Orchestration**: `AgentOrchestrator` (`src/vibe_studio/agents/orchestrator.py`) coordinates `IntentPredictor`, `NavigatorAgent`, `ContextEngine`, `AutonomousAgent`, `ReviewerAgent`, and `DebugAssistant` into a unified pipeline.
- **Code Intelligence & Autocomplete**: AST (Python) and multi-language symbol index providing Go-to-Definition (`F12`), Hover docstrings, Find References, and `QCompleter` autocomplete (`Ctrl+Space`).
- **Real-Time File Watching**: `WorkspaceFileWatcher` (`src/vibe_studio/filesystem/file_watcher.py`) auto-refreshes file explorer, Git status, and open editor tabs on external disk modifications.
- **Large-Project Context Engine**: Import-graph dependency ranking and token-budgeted scoring select relevant files accurately for projects with 1000+ files.
- **Offline & Model Fallback**: Graceful fallback to deterministic rule-based execution when Ollama or remote LLM APIs are offline.
