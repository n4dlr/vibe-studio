from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from vibe_studio.security.path_security import PathSecurity


class SearchTools:
    """Implement high-performance project text, regex, symbol, import, and reference search tools."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)

    def _should_skip(self, path: Path) -> bool:
        rel = path.relative_to(self.workspace_root).as_posix()
        parts = rel.split("/")
        ignored = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache", ".egg-info"}
        return any(part in ignored or part.endswith(".egg-info") for part in parts)

    def search_text(self, query: str, case_sensitive: bool = False, include_patterns: list[str] | None = None) -> list[dict[str, Any]]:
        matches = []
        q = query if case_sensitive else query.lower()

        for path in self.workspace_root.rglob("*"):
            if not path.is_file() or self._should_skip(path):
                continue
            if include_patterns:
                rel_str = path.relative_to(self.workspace_root).as_posix()
                if not any(pat in rel_str for pat in include_patterns):
                    continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for idx, line in enumerate(content.splitlines(), start=1):
                target_line = line if case_sensitive else line.lower()
                if q in target_line:
                    matches.append({
                        "file": path.relative_to(self.workspace_root).as_posix(),
                        "line": idx,
                        "content": line.strip(),
                    })
                    if len(matches) >= 200:
                        return matches
        return matches

    def search_regex(self, pattern: str, flags: int = 0) -> list[dict[str, Any]]:
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
                    if len(matches) >= 200:
                        return matches
        return matches

    def search_filename(self, pattern: str) -> list[str]:
        pattern_lower = pattern.lower()
        results = []
        for path in self.workspace_root.rglob("*"):
            if self._should_skip(path):
                continue
            rel = path.relative_to(self.workspace_root).as_posix()
            if pattern_lower in rel.lower():
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
