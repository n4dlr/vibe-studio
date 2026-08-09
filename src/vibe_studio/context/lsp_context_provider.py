"""LSP Context Provider — proactively queries LSP for symbol information before agent planning.

Provides references, hover info, type hints and call hierarchy
to the coding agent so it makes better-informed decisions.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SymbolInfo:
    name: str
    file: str
    line: int
    kind: str = ""
    docstring: str = ""
    type_hint: str = ""
    references: list[dict[str, Any]] = field(default_factory=list)
    callers: list[str] = field(default_factory=list)


@dataclass
class LSPPreAnalysis:
    symbols_found: list[SymbolInfo] = field(default_factory=list)
    reference_count: int = 0
    affected_files: list[str] = field(default_factory=list)
    summary: str = ""

    def to_prompt_section(self) -> str:
        """Format as a prompt-ready pre-analysis section."""
        if not self.symbols_found and not self.affected_files:
            return ""
        lines = ["PRE-ANALYSIS (LSP Code Intelligence):"]
        if self.affected_files:
            lines.append(f"  Potentially affected files: {', '.join(self.affected_files[:8])}")
        for sym in self.symbols_found[:5]:
            lines.append(f"  Symbol: {sym.name} @ {sym.file}:{sym.line}")
            if sym.docstring:
                lines.append(f"    Doc: {sym.docstring[:120]}")
            if sym.type_hint:
                lines.append(f"    Type: {sym.type_hint}")
            if sym.references:
                ref_files = list({r.get('file', '') for r in sym.references if r.get('file')})[:4]
                lines.append(f"    References in: {', '.join(ref_files)}")
                lines.append(f"    Total references: {len(sym.references)}")
        if self.summary:
            lines.append(f"  Summary: {self.summary}")
        return "\n".join(lines)


class LSPContextProvider:
    """Queries the project's LSP server (via pylsp/pyright CLI) for pre-analysis data."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self._pyright_available: bool | None = None

    def _check_pyright(self) -> bool:
        if self._pyright_available is not None:
            return self._pyright_available
        try:
            result = subprocess.run(
                ["pyright", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            self._pyright_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._pyright_available = False
        return self._pyright_available

    def get_references(self, symbol: str, file_path: str | None = None) -> list[dict[str, Any]]:
        """Find all usages of a symbol across the project using grep (fast fallback)."""
        refs: list[dict[str, Any]] = []
        try:
            cmd = ["grep", "-rn", "--include=*.py", symbol, str(self.workspace_root)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            for line in result.stdout.splitlines()[:30]:
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    refs.append({
                        "file": parts[0].replace(str(self.workspace_root) + "/", ""),
                        "line": int(parts[1]) if parts[1].isdigit() else 0,
                        "content": parts[2].strip() if len(parts) > 2 else "",
                    })
        except Exception:
            pass
        return refs

    def get_hover_info(self, symbol: str, file_path: str | None = None) -> str:
        """Extract docstring / type hints for a symbol using AST inspection."""
        import ast
        import re

        search_file = None
        if file_path:
            p = self.workspace_root / file_path
            if p.exists():
                search_file = p

        if search_file is None:
            # Search for symbol definition across .py files
            try:
                cmd = ["grep", "-rl", "--include=*.py", f"def {symbol}", str(self.workspace_root)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                hits = result.stdout.strip().splitlines()
                if hits:
                    search_file = Path(hits[0])
            except Exception:
                pass

        if search_file is None or not search_file.exists():
            return ""

        try:
            tree = ast.parse(search_file.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == symbol:
                        docstring = ast.get_docstring(node) or ""
                        # Extract return type
                        ret_type = ""
                        if node.returns:
                            try:
                                ret_type = ast.unparse(node.returns)
                            except Exception:
                                pass
                        # Extract arg types
                        arg_types = []
                        for arg in node.args.args:
                            if arg.annotation:
                                try:
                                    arg_types.append(f"{arg.arg}: {ast.unparse(arg.annotation)}")
                                except Exception:
                                    arg_types.append(arg.arg)
                        sig = f"def {symbol}({', '.join(arg_types)})"
                        if ret_type:
                            sig += f" -> {ret_type}"
                        return f"{sig}\n{docstring[:300]}" if docstring else sig
                elif isinstance(node, ast.ClassDef) and node.name == symbol:
                    docstring = ast.get_docstring(node) or ""
                    return f"class {symbol}\n{docstring[:300]}" if docstring else f"class {symbol}"
        except Exception:
            pass
        return ""

    def analyze_prompt(self, prompt: str, active_file: str | None = None) -> LSPPreAnalysis:
        """Extract symbols from prompt and run pre-analysis for agent context."""
        import re

        # Extract potential symbol names (CamelCase + snake_case)
        words = re.findall(r"\b([A-Z][a-zA-Z0-9]+|[a-z][a-z0-9_]{2,}[a-z0-9])\b", prompt)
        # Filter out common English words
        _stop = {"the", "and", "for", "with", "this", "that", "from", "into", "over"}
        candidates = [w for w in words if w.lower() not in _stop][:6]

        symbols_found: list[SymbolInfo] = []
        affected_files_set: set[str] = set()

        for sym in candidates:
            refs = self.get_references(sym, active_file)
            if not refs:
                continue
            hover = self.get_hover_info(sym, active_file)
            affected_files_set.update(r["file"] for r in refs if r.get("file"))
            symbols_found.append(SymbolInfo(
                name=sym,
                file=refs[0]["file"] if refs else (active_file or ""),
                line=refs[0]["line"] if refs else 0,
                docstring=hover,
                references=refs,
            ))

        total_refs = sum(len(s.references) for s in symbols_found)
        summary = ""
        if total_refs > 10:
            summary = f"High-impact change: {total_refs} references found across {len(affected_files_set)} files."
        elif symbols_found:
            summary = f"Found {len(symbols_found)} symbols, {total_refs} total references."

        return LSPPreAnalysis(
            symbols_found=symbols_found,
            reference_count=total_refs,
            affected_files=list(affected_files_set),
            summary=summary,
        )
