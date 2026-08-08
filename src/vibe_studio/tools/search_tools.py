from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from vibe_studio.security.path_security import PathSecurity


class SearchTools:
    """Implement high-performance project text, regex, symbol, import, and reference search tools with ripgrep fallback."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)
        self._rg_path = shutil.which("rg")

    def _should_skip(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.workspace_root).as_posix()
        except ValueError:
            return True
        parts = rel.split("/")
        ignored = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache", ".egg-info", "venv", "target", ".mypy_cache"}
        return any(part in ignored or part.endswith(".egg-info") for part in parts)

    def search_text(
        self,
        query: str,
        case_sensitive: bool = False,
        include_patterns: list[str] | None = None,
        max_results: int = 200,
    ) -> list[dict[str, Any]]:
        # Fast path using ripgrep if available and no complex include patterns
        if self._rg_path and not include_patterns:
            try:
                cmd = [self._rg_path, "--line-number", "--no-heading", "--color=never"]
                if not case_sensitive:
                    cmd.append("-i")
                cmd.extend(["--fixed-strings", query, str(self.workspace_root)])
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if res.returncode in (0, 1):
                    matches = []
                    for line in res.stdout.splitlines():
                        if ":" in line:
                            parts = line.split(":", 2)
                            if len(parts) == 3:
                                file_path, line_no, content = parts
                                try:
                                    rel_file = Path(file_path).relative_to(self.workspace_root).as_posix()
                                except ValueError:
                                    rel_file = file_path
                                matches.append({
                                    "file": rel_file,
                                    "line": int(line_no),
                                    "content": content.strip(),
                                })
                                if len(matches) >= max_results:
                                    return matches
                    if matches:
                        return matches
            except Exception:
                pass  # Fall back to pure Python implementation

        matches = []
        q = query if case_sensitive else query.lower()

        for path in self.workspace_root.rglob("*"):
            if not path.is_file() or self._should_skip(path):
                continue

            rel_str = path.relative_to(self.workspace_root).as_posix()
            if include_patterns:
                if not any(fnmatch.fnmatch(rel_str, pat) or pat in rel_str for pat in include_patterns):
                    continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for idx, line in enumerate(content.splitlines(), start=1):
                target_line = line if case_sensitive else line.lower()
                if q in target_line:
                    matches.append({
                        "file": rel_str,
                        "line": idx,
                        "content": line.strip(),
                    })
                    if len(matches) >= max_results:
                        return matches
        return matches

    def search_regex(self, pattern: str, flags: int = 0, max_results: int = 200) -> list[dict[str, Any]]:
        matches = []
        try:
            regex = re.compile(pattern, flags)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}")

        for path in self.workspace_root.rglob("*"):
            if not path.is_file() or self._should_skip(path):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for idx, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    matches.append({
                        "file": path.relative_to(self.workspace_root).as_posix(),
                        "line": idx,
                        "content": line.strip(),
                    })
                    if len(matches) >= max_results:
                        return matches
        return matches

    def search_filename(self, pattern: str) -> list[str]:
        pattern_lower = pattern.lower()
        results = []
        for path in self.workspace_root.rglob("*"):
            if self._should_skip(path):
                continue
            rel = path.relative_to(self.workspace_root).as_posix()
            if pattern_lower in rel.lower() or fnmatch.fnmatch(rel.lower(), f"*{pattern_lower}*"):
                results.append(rel)
        return sorted(results)[:100]

    def search_symbol(self, name: str) -> list[dict[str, Any]]:
        pattern = r"(?i)\b(def|class|function|const|let|var|type|interface|enum|struct|fn|trait|void)\s+" + re.escape(name) + r"\b"
        return self.search_regex(pattern)

    def search_import(self, module_name: str) -> list[dict[str, Any]]:
        pattern = r"(?i)\b(import|from|require|use|include)\s+.*" + re.escape(module_name)
        return self.search_regex(pattern)

    def find_references(self, symbol_name: str) -> list[dict[str, Any]]:
        pattern = r"\b" + re.escape(symbol_name) + r"\b"
        return self.search_regex(pattern)

    def find_definition(self, symbol_name: str) -> list[dict[str, Any]]:
        pattern = r"(?i)\b(def|class|function|fn|struct|interface|type)\s+" + re.escape(symbol_name) + r"\b"
        return self.search_regex(pattern)

    def search_definitions_in_file(self, file_path: str, symbol_name: str | None = None) -> list[dict[str, Any]]:
        """Find symbol definitions scoped to a specific file."""
        target = PathSecurity.validate_workspace_path(file_path, self.workspace_root)
        if not target.exists():
            return []
        content = target.read_text(encoding="utf-8", errors="replace")
        rel_str = target.relative_to(self.workspace_root).as_posix()
        
        if symbol_name:
            pattern = r"(?i)\b(def|class|function|fn|struct|interface|type)\s+" + re.escape(symbol_name) + r"\b"
        else:
            pattern = r"(?i)\b(def|class|function|fn|struct|interface|type)\s+([A-Za-z0-9_]+)\b"
            
        regex = re.compile(pattern)
        results = []
        for idx, line in enumerate(content.splitlines(), start=1):
            if regex.search(line):
                results.append({
                    "file": rel_str,
                    "line": idx,
                    "content": line.strip(),
                })
        return results
