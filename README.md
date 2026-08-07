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

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
# .\.venv\Scripts\Activate.ps1
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
pip install -e .[dev]
pytest
```

## Packaging

The package is prepared for local installation and desktop execution. It is intentionally designed so the logic can be separated from GUI concerns for future mobile or CLI reuse.

## Troubleshooting

- If PySide6 fails to install, upgrade pip and install the project again.
- If Ollama is unavailable, configure another provider in Settings.
- If a project folder cannot be opened, ensure the path exists and is readable.

## License

MIT
