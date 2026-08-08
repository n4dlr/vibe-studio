"""PerformanceAnalyzer — scans code for O(n^2) nested loops and potential memory leak patterns."""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class PerformanceFinding:
    file: str
    line: int
    severity: str
    message: str
    snippet: str


class PerformanceAnalyzer:
    """Detects algorithmic bottlenecks and performance anti-patterns."""

    NESTED_FOR_PY = re.compile(r"^\s*for\s+.*\s+in\s+.*:")
    GLOBAL_ACCUMULATOR = re.compile(r"^\s*global_cache\.append|^\s*list_buffer\.extend")

    def scan_file(self, file_path: Path, workspace_root: Path) -> list[PerformanceFinding]:
        findings: list[PerformanceFinding] = []
        try:
            rel = file_path.relative_to(workspace_root).as_posix()
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return findings

        for idx, line in enumerate(lines, start=1):
            if self.NESTED_FOR_PY.match(line):
                # Check next 3 lines for nested loop
                for next_idx in range(idx, min(len(lines), idx + 4)):
                    next_line = lines[next_idx]
                    if self.NESTED_FOR_PY.match(next_line) and len(next_line) - len(next_line.lstrip()) > len(line) - len(line.lstrip()):
                        findings.append(
                            PerformanceFinding(
                                file=rel,
                                line=idx + 1,
                                severity="MEDIUM",
                                message="Possible O(n²) nested loop detected",
                                snippet=line.strip() + " -> " + next_line.strip(),
                            )
                        )
                        break

            if self.GLOBAL_ACCUMULATOR.search(line):
                findings.append(
                    PerformanceFinding(
                        file=rel,
                        line=idx,
                        severity="LOW",
                        category="Memory Growth",
                        message="Unbounded list growth pattern detected",
                        snippet=line.strip(),
                    )
                )

        return findings

    def scan_project(self, workspace_root: Path) -> list[PerformanceFinding]:
        findings: list[PerformanceFinding] = []
        skip = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
        for p in workspace_root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in skip for part in p.parts):
                continue
            if p.suffix in {".py", ".js", ".ts"}:
                findings.extend(self.scan_file(p, workspace_root))
        return findings
