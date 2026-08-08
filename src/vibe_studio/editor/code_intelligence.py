"""CodeIntelligenceEngine — LSP-first code intelligence router with AST/regex fallbacks.

Routing Architecture:
Editor / Agent / Problems Panel
       ↓
CodeIntelligenceEngine (IntelligenceRouter)
       ↓
LSP Server (when available & healthy)
       ↓
AST (Python) / Regex (JS/TS/other) / ProjectScanner fallback (when LSP fails or unavailable)
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vibe_studio.editor.lsp_client import LSPClient, LSPClientState
from vibe_studio.editor.lsp_registry import default_lsp_registry
from vibe_studio.project.project_scanner import ProjectScanner, SymbolInfo
from vibe_studio.security.path_security import PathSecurity, PathSecurityError


@dataclass
class DefinitionResult:
    file: str
    line: int
    column: int = 0
    symbol: str = ""
    kind: str = "symbol"
    source: str = "lsp"  # "lsp" or "fallback"


@dataclass
class HoverInfo:
    symbol: str
    kind: str
    file: str
    line: int
    docstring: str = ""
    source: str = "lsp"


class CompletionOption(str):
    label: str
    kind: str
    detail: str
    documentation: str
    insert_text: str
    source: str

    def __new__(
        cls,
        label: str,
        kind: str = "Text",
        detail: str = "",
        documentation: str = "",
        insert_text: str = "",
        source: str = "lsp",
    ):
        instance = super().__new__(cls, label)
        instance.label = label
        instance.kind = kind
        instance.detail = detail
        instance.documentation = documentation
        instance.insert_text = insert_text or label
        instance.source = source
        return instance


@dataclass
class SymbolIndex:
    """In-memory symbol table keyed by symbol name."""
    symbols: dict[str, list[SymbolInfo]] = field(default_factory=dict)


class CodeIntelligenceEngine:
    """LSP-first intelligence router with automatic AST & regex fallback."""

    SKIP = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache"}

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)
        self._index: SymbolIndex | None = None
        self._lsp_clients: dict[str, LSPClient] = {}
        self._diagnostics_listeners: list[Callable[[str, list[dict[str, Any]]], None]] = []

    def get_lsp_client(self, language: str) -> LSPClient | None:
        """Get or initialize LSP client for a language."""
        lang = language.lower()
        if lang not in self._lsp_clients:
            client = LSPClient(lang, self.workspace_root)
            if client.is_available():
                client.on_diagnostics(self._on_lsp_diagnostics)
                if client.start():
                    self._lsp_clients[lang] = client
                else:
                    return None
            else:
                return None
        client = self._lsp_clients.get(lang)
        if client and client.is_running:
            return client
        return None

    def on_diagnostics(self, callback: Callable[[str, list[dict[str, Any]]], None]) -> None:
        """Register a callback for live LSP diagnostics."""
        self._diagnostics_listeners.append(callback)

    def _on_lsp_diagnostics(self, uri: str, diagnostics: list[dict[str, Any]]) -> None:
        for cb in list(self._diagnostics_listeners):
            try:
                cb(uri, diagnostics)
            except Exception:
                pass

    def get_status(self, language: str) -> str:
        """Return human-readable status for a language server."""
        lang = language.lower()
        client = self._lsp_clients.get(lang)
        if not client:
            srv = default_lsp_registry.find_available_server(lang)
            if not srv:
                return f"{language.title()}: LSP unavailable (using AST/regex fallback)"
            return f"{language.title()}: LSP stopped"

        if client.state == LSPClientState.RUNNING:
            name = client.server_config.display_name if client.server_config else "LSP"
            return f"{language.title()}: {name} Ready"
        elif client.state == LSPClientState.STARTING:
            return f"{language.title()}: LSP Starting..."
        elif client.state == LSPClientState.ERROR:
            return f"{language.title()}: LSP Error (using fallback)"
        return f"{language.title()}: LSP {client.state.value}"

    # ------------------------------------------------------------------
    # Index management (for fallback mode)
    # ------------------------------------------------------------------

    def build_index(self) -> SymbolIndex:
        scanner = ProjectScanner(self.workspace_root)
        summary = scanner.scan()
        index: dict[str, list[SymbolInfo]] = {}
        for fs in summary.files:
            for sym in fs.symbols:
                if sym.name not in index:
                    index[sym.name] = []
                index[sym.name].append(sym)
        self._index = SymbolIndex(symbols=index)
        return self._index

    def _get_index(self) -> SymbolIndex:
        if self._index is None:
            self.build_index()
        return self._index  # type: ignore[return-value]

    def invalidate_index(self) -> None:
        """Call when disk files change to invalidate fallback caches."""
        self._index = None

    # ------------------------------------------------------------------
    # Go-to-Definition (LSP → Fallback)
    # ------------------------------------------------------------------

    def find_definition(
        self,
        symbol: str,
        file_path: str | Path | None = None,
        line: int = 1,
        column: int = 0,
    ) -> list[DefinitionResult]:
        # 1. Try LSP first if file path provided
        if file_path:
            p = Path(file_path)
            lang = p.suffix.lstrip(".") or "python"
            client = self.get_lsp_client(lang)
            if client:
                raw_defs = client.goto_definition(file_path, line, column)
                if raw_defs:
                    results = []
                    for d in raw_defs:
                        target_uri = d.get("uri") or d.get("targetUri", "")
                        range_info = d.get("range") or d.get("targetSelectionRange") or d.get("targetRange", {})
                        start_pos = range_info.get("start", {})
                        def_line = start_pos.get("line", 0) + 1
                        def_col = start_pos.get("character", 0)

                        try:
                            target_path = Path(target_uri.replace("file://", "")).relative_to(self.workspace_root).as_posix()
                        except ValueError:
                            target_path = target_uri.replace("file://", "")

                        results.append(DefinitionResult(
                            file=target_path,
                            line=def_line,
                            column=def_col,
                            symbol=symbol,
                            kind="symbol",
                            source="lsp",
                        ))
                    if results:
                        return results

        # 2. Fallback to SymbolIndex
        index = self._get_index()
        syms = index.symbols.get(symbol, [])
        return [
            DefinitionResult(file=s.file, line=s.line, column=0, symbol=s.name, kind=s.kind, source="fallback")
            for s in syms
        ]

    # ------------------------------------------------------------------
    # Find References (LSP → Fallback)
    # ------------------------------------------------------------------

    def find_references(
        self,
        symbol: str,
        current_file: str | Path | None = None,
        line: int = 1,
        column: int = 0,
    ) -> list[dict[str, Any]]:
        if current_file:
            p = Path(current_file)
            lang = p.suffix.lstrip(".") or "python"
            client = self.get_lsp_client(lang)
            if client:
                raw_refs = client.find_references(current_file, line, column)
                if raw_refs:
                    results = []
                    for r in raw_refs:
                        uri = r.get("uri", "")
                        range_info = r.get("range", {})
                        start_pos = range_info.get("start", {})
                        ref_line = start_pos.get("line", 0) + 1
                        try:
                            rel_path = Path(uri.replace("file://", "")).relative_to(self.workspace_root).as_posix()
                        except ValueError:
                            rel_path = uri.replace("file://", "")

                        results.append({
                            "file": rel_path,
                            "line": ref_line,
                            "column": start_pos.get("character", 0),
                            "content": f"Reference to {symbol}",
                            "source": "lsp",
                        })
                    if results:
                        return results

        # Fallback to regex search across project files
        results: list[dict[str, Any]] = []
        pattern = re.compile(r"\b" + re.escape(symbol) + r"\b")

        for path in self.workspace_root.rglob("*"):
            if not path.is_file() or any(part in self.SKIP for part in path.parts):
                continue
            if path.suffix not in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            rel = path.relative_to(self.workspace_root).as_posix()
            for idx, l_str in enumerate(lines, start=1):
                if pattern.search(l_str):
                    results.append({"file": rel, "line": idx, "content": l_str.strip(), "source": "fallback"})
            if len(results) >= 200:
                break
        return results

    # ------------------------------------------------------------------
    # Hover Information (LSP → Fallback)
    # ------------------------------------------------------------------

    def get_hover_info(
        self,
        symbol: str,
        file_path: str | Path | None = None,
        line: int = 1,
        column: int = 0,
    ) -> HoverInfo | None:
        if file_path:
            p = Path(file_path)
            lang = p.suffix.lstrip(".") or "python"
            client = self.get_lsp_client(lang)
            if client:
                hover_text = client.hover(file_path, line, column)
                if hover_text:
                    return HoverInfo(
                        symbol=symbol,
                        kind="lsp_hover",
                        file=str(file_path),
                        line=line,
                        docstring=hover_text,
                        source="lsp",
                    )

        # Fallback to AST docstrings or index
        index = self._get_index()
        syms = index.symbols.get(symbol, [])
        if not syms:
            return None

        best = syms[0]
        docstring = ""
        full_path = self.workspace_root / best.file
        if full_path.suffix == ".py" and full_path.exists():
            try:
                tree = ast.parse(full_path.read_text(encoding="utf-8", errors="replace"))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name == symbol:
                            docstring = ast.get_docstring(node) or ""
                            break
            except Exception:
                pass

        return HoverInfo(
            symbol=best.name,
            kind=best.kind,
            file=best.file,
            line=best.line,
            docstring=docstring[:300] if docstring else f"{best.kind} `{best.name}` in {best.file}:{best.line}",
            source="fallback",
        )

    # ------------------------------------------------------------------
    # Auto-Completions (LSP → Fallback)
    # ------------------------------------------------------------------

    def get_completions(
        self,
        prefix: str,
        current_file: str | Path | None = None,
        line: int = 1,
        column: int = 0,
    ) -> list[CompletionOption]:
        if current_file:
            p = Path(current_file)
            lang = p.suffix.lstrip(".") or "python"
            client = self.get_lsp_client(lang)
            if client:
                _, raw_items = client.get_completions(current_file, line, column)
                if raw_items:
                    opts = []
                    for item in raw_items[:30]:
                        label = item.get("label", "")
                        insert_text = item.get("insertText") or item.get("textEdit", {}).get("newText") or label
                        doc = item.get("documentation", "")
                        if isinstance(doc, dict):
                            doc = doc.get("value", "")
                        opts.append(CompletionOption(
                            label=label,
                            kind=str(item.get("kind", "Text")),
                            detail=item.get("detail", ""),
                            documentation=str(doc),
                            insert_text=insert_text,
                            source="lsp",
                        ))
                    if opts:
                        return opts

        # Fallback to symbol table matches
        if len(prefix) < 2:
            return []
        index = self._get_index()
        lower_prefix = prefix.lower()
        matches = [
            name for name in index.symbols
            if name.lower().startswith(lower_prefix)
        ]
        return [
            CompletionOption(label=name, insert_text=name, source="fallback")
            for name in sorted(matches)[:20]
        ]

    # ------------------------------------------------------------------
    # Document & Workspace Symbols (LSP → Fallback)
    # ------------------------------------------------------------------

    def get_document_symbols(self, file_path: str | Path) -> list[SymbolInfo]:
        p = Path(file_path)
        lang = p.suffix.lstrip(".") or "python"
        client = self.get_lsp_client(lang)
        if client:
            raw_syms = client.get_document_symbols(file_path)
            if raw_syms:
                results = []
                rel_path = p.relative_to(self.workspace_root).as_posix() if p.is_absolute() else p.as_posix()
                for s in raw_syms:
                    name = s.get("name", "")
                    kind = str(s.get("kind", "symbol"))
                    r = s.get("range") or s.get("selectionRange") or {}
                    line_no = r.get("start", {}).get("line", 0) + 1
                    results.append(SymbolInfo(name=name, kind=kind, file=rel_path, line=line_no))
                if results:
                    return results

        # Fallback to ProjectScanner index
        index = self._get_index()
        rel = Path(file_path)
        if rel.is_absolute():
            try:
                rel = rel.relative_to(self.workspace_root)
            except ValueError:
                return []
        rel_str = rel.as_posix()
        return [
            s for syms in index.symbols.values()
            for s in syms if s.file == rel_str
        ]

    def get_workspace_symbols(self, query: str) -> list[SymbolInfo]:
        for lang in ("python", "typescript", "go", "rust", "c"):
            client = self._lsp_clients.get(lang)
            if client and client.is_running:
                raw = client.workspace_symbols(query)
                if raw:
                    results = []
                    for s in raw:
                        name = s.get("name", "")
                        loc = s.get("location", {})
                        uri = loc.get("uri", "")
                        line_no = loc.get("range", {}).get("start", {}).get("line", 0) + 1
                        try:
                            rel = Path(uri.replace("file://", "")).relative_to(self.workspace_root).as_posix()
                        except ValueError:
                            rel = uri.replace("file://", "")
                        results.append(SymbolInfo(name=name, kind=str(s.get("kind", "")), file=rel, line=line_no))
                    if results:
                        return results

        # Fallback to in-memory symbol index search
        index = self._get_index()
        q_lower = query.lower()
        results = []
        for name, syms in index.symbols.items():
            if q_lower in name.lower():
                results.extend(syms)
        return results[:100]

    def get_diagnostics(self, file_path: str | Path) -> list[dict[str, Any]]:
        p = Path(file_path)
        lang = p.suffix.lstrip(".") or "python"
        client = self._lsp_clients.get(lang)
        if client and client.is_running:
            return client.get_diagnostics(file_path)
        return []
