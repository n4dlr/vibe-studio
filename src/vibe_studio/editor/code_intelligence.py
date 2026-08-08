"""CodeIntelligenceEngine — AST/regex-based Go-to-Definition, References, Hover, and Symbol index."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_studio.project.project_scanner import ProjectScanner, SymbolInfo


@dataclass
class DefinitionResult:
    file: str
    line: int
    symbol: str
    kind: str


@dataclass
class HoverInfo:
    symbol: str
    kind: str
    file: str
    line: int
    docstring: str = ""


@dataclass
class SymbolIndex:
    """In-memory symbol table keyed by symbol name."""
    symbols: dict[str, list[SymbolInfo]] = field(default_factory=dict)


class CodeIntelligenceEngine:
    """Provides code intelligence without an external LSP server.

    Falls back to AST (Python) and regex (JS/TS/etc.) symbol indexing.
    """

    SKIP = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache"}

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self._index: SymbolIndex | None = None

    # ------------------------------------------------------------------
    # Index management
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
        """Call when files change on disk to trigger re-indexing on next use."""
        self._index = None

    # ------------------------------------------------------------------
    # Go-to-Definition
    # ------------------------------------------------------------------

    def find_definition(self, symbol: str) -> list[DefinitionResult]:
        index = self._get_index()
        syms = index.symbols.get(symbol, [])
        return [
            DefinitionResult(file=s.file, line=s.line, symbol=s.name, kind=s.kind)
            for s in syms
        ]

    # ------------------------------------------------------------------
    # Find References
    # ------------------------------------------------------------------

    def find_references(self, symbol: str, current_file: str | None = None) -> list[dict[str, Any]]:
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
            for idx, line in enumerate(lines, start=1):
                if pattern.search(line):
                    results.append({"file": rel, "line": idx, "content": line.strip()})
            if len(results) >= 200:
                break
        return results

    # ------------------------------------------------------------------
    # Hover information
    # ------------------------------------------------------------------

    def get_hover_info(self, symbol: str) -> HoverInfo | None:
        index = self._get_index()
        syms = index.symbols.get(symbol, [])
        if not syms:
            return None

        best = syms[0]

        # For Python symbols, attempt to extract docstring
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
        )

    # ------------------------------------------------------------------
    # Document symbols (for symbol outline panel)
    # ------------------------------------------------------------------

    def get_document_symbols(self, file_path: str | Path) -> list[SymbolInfo]:
        index = self._get_index()
        rel = Path(file_path)
        if rel.is_absolute():
            try:
                rel = rel.relative_to(self.workspace_root)
            except ValueError:
                return []
        rel_str = rel.as_posix()
        return [
            s
            for syms in index.symbols.values()
            for s in syms
            if s.file == rel_str
        ]

    # ------------------------------------------------------------------
    # Completion words for autocomplete
    # ------------------------------------------------------------------

    def get_completions(self, prefix: str, current_file: str | None = None) -> list[str]:
        if len(prefix) < 2:
            return []
        index = self._get_index()
        lower_prefix = prefix.lower()
        matches = [
            name for name in index.symbols
            if name.lower().startswith(lower_prefix)
        ]
        return sorted(matches)[:20]
