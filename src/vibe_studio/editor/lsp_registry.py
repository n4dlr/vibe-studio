"""LSP Server Registry & Discovery Engine.

Manages language-to-server metadata, priority, command arguments, and discovery
of available external Language Server executables.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LSPServerConfig:
    language_id: str
    display_name: str
    file_extensions: list[str]
    command: str
    args: list[str] = field(default_factory=list)
    priority: int = 10  # Higher = preferred candidate
    install_hint: str = ""


class LSPServerRegistry:
    """Registry of known Language Servers and discovery engine."""

    DEFAULT_SERVERS: dict[str, list[LSPServerConfig]] = {
        "python": [
            LSPServerConfig(
                language_id="python",
                display_name="Pyright",
                file_extensions=[".py", ".pyi"],
                command="pyright-langserver",
                args=["--stdio"],
                priority=20,
                install_hint="npm install -g pyright",
            ),
            LSPServerConfig(
                language_id="python",
                display_name="Python LSP Server (pylsp)",
                file_extensions=[".py", ".pyi"],
                command="pylsp",
                args=[],
                priority=10,
                install_hint="pip install python-lsp-server",
            ),
        ],
        "typescript": [
            LSPServerConfig(
                language_id="typescript",
                display_name="TypeScript Language Server",
                file_extensions=[".ts", ".tsx"],
                command="typescript-language-server",
                args=["--stdio"],
                priority=10,
                install_hint="npm install -g typescript-language-server typescript",
            ),
        ],
        "javascript": [
            LSPServerConfig(
                language_id="javascript",
                display_name="TypeScript/JavaScript Language Server",
                file_extensions=[".js", ".jsx", ".mjs", ".cjs"],
                command="typescript-language-server",
                args=["--stdio"],
                priority=10,
                install_hint="npm install -g typescript-language-server typescript",
            ),
        ],
        "go": [
            LSPServerConfig(
                language_id="go",
                display_name="gopls",
                file_extensions=[".go"],
                command="gopls",
                args=[],
                priority=10,
                install_hint="go install golang.org/x/tools/gopls@latest",
            ),
        ],
        "rust": [
            LSPServerConfig(
                language_id="rust",
                display_name="rust-analyzer",
                file_extensions=[".rs"],
                command="rust-analyzer",
                args=[],
                priority=10,
                install_hint="rustup component add rust-analyzer",
            ),
        ],
        "c": [
            LSPServerConfig(
                language_id="c",
                display_name="clangd",
                file_extensions=[".c", ".h"],
                command="clangd",
                args=[],
                priority=10,
                install_hint="apt install clangd / brew install llvm",
            ),
        ],
        "cpp": [
            LSPServerConfig(
                language_id="cpp",
                display_name="clangd",
                file_extensions=[".cpp", ".hpp", ".cc", ".cxx"],
                command="clangd",
                args=[],
                priority=10,
                install_hint="apt install clangd / brew install llvm",
            ),
        ],
        "html": [
            LSPServerConfig(
                language_id="html",
                display_name="HTML Language Server",
                file_extensions=[".html", ".htm"],
                command="vscode-html-language-server",
                args=["--stdio"],
                priority=10,
                install_hint="npm install -g vscode-langservers-extracted",
            ),
        ],
        "css": [
            LSPServerConfig(
                language_id="css",
                display_name="CSS Language Server",
                file_extensions=[".css", ".scss", ".less"],
                command="vscode-css-language-server",
                args=["--stdio"],
                priority=10,
                install_hint="npm install -g vscode-langservers-extracted",
            ),
        ],
        "json": [
            LSPServerConfig(
                language_id="json",
                display_name="JSON Language Server",
                file_extensions=[".json", ".jsonc"],
                command="vscode-json-language-server",
                args=["--stdio"],
                priority=10,
                install_hint="npm install -g vscode-langservers-extracted",
            ),
        ],
    }

    def __init__(self):
        self._servers: dict[str, list[LSPServerConfig]] = dict(self.DEFAULT_SERVERS)

    def register_server(self, config: LSPServerConfig) -> None:
        """Register or override a language server configuration."""
        lang = config.language_id.lower()
        if lang not in self._servers:
            self._servers[lang] = []
        self._servers[lang].append(config)
        self._servers[lang].sort(key=lambda s: s.priority, reverse=True)

    def find_available_server(self, language: str) -> LSPServerConfig | None:
        """Find the highest-priority installed server executable for a language."""
        lang = language.lower()
        candidates = self._servers.get(lang, [])
        for config in candidates:
            if shutil.which(config.command):
                return config
        return None

    def get_server_for_file(self, file_path: str | Path) -> LSPServerConfig | None:
        """Find a suitable language server matching a file's extension."""
        ext = Path(file_path).suffix.lower()
        if not ext:
            return None

        for lang, configs in self._servers.items():
            for config in configs:
                if ext in config.file_extensions:
                    if shutil.which(config.command):
                        return config
        return None

    def get_all_supported_languages(self) -> list[str]:
        return sorted(list(self._servers.keys()))


default_lsp_registry = LSPServerRegistry()
