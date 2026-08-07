# Vibe Studio

Vibe Studio is a local-first, AI-assisted desktop coding IDE for Linux and Windows. It is designed to help developers open a project, inspect it, reason about the correct changes, and make edits with approval gates and a secure command layer.

## Features

- Modern PySide6 desktop interface inspired by professional IDE layouts
- Project explorer with file and folder operations
- Basic code editor with tabbed editing and unsaved state tracking
- Local project indexing and dependency detection
- Context ranking for relevant files, symbols, and recent changes
- AI provider abstraction for local Ollama and OpenAI-compatible APIs
- Safe command execution with destructive-command restrictions
- Git integration for status, diff, and basic history operations
- Test detection and execution using common project tooling
- Structured logging and settings persistence
- Local-first operation with optional cloud provider support

## Installation

### Option 1: using requirements.txt

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m vibe_studio
```

### Option 2: editable install

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m vibe_studio
```

## Ollama setup

1. Install Ollama from https://ollama.com.
2. Start the local server.
3. Verify the default endpoint: `http://127.0.0.1:11434`
4. Pull models, for example:

```bash
ollama pull llama3.1
```

The application checks the endpoint automatically and shows available models in the model manager.

## API setup

Configure an OpenAI-compatible provider through the app settings. Keep API keys in environment variables whenever possible, such as:

```bash
export OPENAI_API_KEY="..."
export CUSTOM_API_KEY="..."
```

## Security principles

- No API keys are logged.
- Destructive shell commands are blocked by default.
- Local-only mode prevents cloud requests.
- Sensitive files are flagged before external AI calls.

## Development

```bash
pip install -r requirements.txt
pip install -e .[dev]
pytest
```

## Packaging

The package is prepared for local installation and desktop execution. It is intentionally designed so the logic can be separated from GUI concerns for future mobile or CLI reuse.

## Troubleshooting

- If PySide6 fails to install, upgrade pip and install the project again.
- If Ollama is unavailable, configure another provider in Settings.
- If a project folder cannot be opened, ensure the path exists and is readable.
- If Qt fails with an xcb plugin error on Linux, install the runtime library:

```bash
sudo apt-get update
sudo apt-get install -y libxcb-cursor0
```

If no desktop session is available, the app automatically falls back to the offscreen Qt platform.

## License

This project is licensed under the MIT License.

MIT License

Copyright (c) 2026 Vibe Studio

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


