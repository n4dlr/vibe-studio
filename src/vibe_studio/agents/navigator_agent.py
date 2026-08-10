"""NavigatorAgent — explores project files, identifies entry points, and provides structural summaries."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from vibe_studio.project.project_scanner import ProjectScanner


class NavigatorAgent:
    """Specialized agent focused on codebase navigation, file mapping, and dependency discovery.

    Relevance ranking strategy (in priority order):
      1. Filename contains the topic keyword
      2. Symbol name (function/class) contains the topic keyword
      3. File content contains the topic keyword (for small files ≤ 64 KB)
      4. For very short topic words, also check imports and docstrings
    """

    # Files larger than this are not content-scanned (performance guard)
    _MAX_CONTENT_SCAN_BYTES = 65_536  # 64 KB

    # File extensions eligible for content scanning
    _SCANNABLE_EXTS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
        ".kt", ".cs", ".php", ".rb", ".c", ".cpp", ".h", ".hpp",
        ".html", ".css", ".scss", ".vue", ".svelte",
        ".yaml", ".yml", ".json", ".toml", ".md", ".txt",
    }

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.scanner = ProjectScanner(self.workspace_root)

    def discover_relevant_files(self, topic: str) -> list[str]:
        """Return up to 15 files most relevant to *topic*.

        Uses a scored approach:
          - filename match     : +10
          - symbol name match  : +8
          - content keyword    : +4
          - import match       : +3
          - multiple matches   : additive
        """
        if not topic or not topic.strip():
            return []

        summary = self.scanner.scan()
        topic_lower = topic.lower().strip()

        # Extract meaningful keywords from topic (skip common stop words)
        _STOP_WORDS = {
            "the", "a", "an", "in", "to", "of", "and", "or", "is", "are",
            "was", "be", "for", "with", "on", "at", "by", "from", "this",
            "that", "it", "its", "as", "but", "add", "əlavə", "create", "yarat",
            "write", "yaz", "make", "file", "fayl", "new", "into", "also",
        }
        raw_keywords = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", topic_lower)
        keywords = [k for k in raw_keywords if len(k) >= 3 and k not in _STOP_WORDS]
        # Always include the full topic string as a keyword
        keywords_set = set(keywords)

        scores: dict[str, float] = {}

        for f in summary.files:
            path_lower = f.path.lower()
            fname_lower = Path(f.path).name.lower()
            score = 0.0

            # 1. Filename match
            for kw in keywords:
                if kw in fname_lower:
                    score += 10.0
            if topic_lower in path_lower:
                score += 5.0

            # 2. Symbol name match
            for sym in f.symbols:
                sym_lower = sym.name.lower()
                for kw in keywords:
                    if kw in sym_lower:
                        score += 8.0
                        break

            # 3. Content scan (for scannable extensions within size limit)
            ext = Path(f.path).suffix.lower()
            if score == 0 and ext in self._SCANNABLE_EXTS:
                abs_path = self.workspace_root / f.path
                try:
                    if abs_path.exists() and abs_path.stat().st_size <= self._MAX_CONTENT_SCAN_BYTES:
                        content_lower = abs_path.read_text(encoding="utf-8", errors="replace").lower()
                        for kw in keywords:
                            if kw in content_lower:
                                score += 4.0
                            # Bonus for import or def/class match
                            if re.search(rf"\b(def|class|function|func|fn)\s+\w*{re.escape(kw)}\w*", content_lower):
                                score += 6.0
                except OSError:
                    pass
            elif score > 0 and ext in self._SCANNABLE_EXTS:
                # File already scored but do a content check for additive bonus
                abs_path = self.workspace_root / f.path
                try:
                    if abs_path.exists() and abs_path.stat().st_size <= self._MAX_CONTENT_SCAN_BYTES:
                        content_lower = abs_path.read_text(encoding="utf-8", errors="replace").lower()
                        for kw in keywords:
                            if kw in content_lower:
                                score += 2.0
                except OSError:
                    pass

            if score > 0:
                scores[f.path] = score

        # Sort by score descending, return top 15
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [path for path, _ in ranked[:15]]

    def get_structure_map(self) -> dict[str, Any]:
        summary = self.scanner.scan()
        return {
            "languages": summary.languages,
            "frameworks": summary.frameworks,
            "entry_points": summary.entry_points,
            "total_files": len(summary.files),
        }
