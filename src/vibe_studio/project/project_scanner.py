from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SymbolInfo:
    name: str
    kind: str
    file: str
    line: int


@dataclass
class FileSummary:
    path: str
    language: str
    size: int
    symbols: list[SymbolInfo] = field(default_factory=list)


@dataclass
class ProjectSummary:
    root: str
    files: list[FileSummary]
    languages: dict[str, int]
    frameworks: list[str]
    package_managers: list[str]
    entry_points: list[str]
    tests: list[str]


class ProjectScanner:
    """Build a lightweight project overview without reading everything into memory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def scan(self) -> ProjectSummary:
        files: list[FileSummary] = []
        languages: dict[str, int] = {}
        frameworks: set[str] = set()
        package_managers: set[str] = set()
        entry_points: list[str] = []
        tests: list[str] = []

        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            language = self._detect_language(path)
            if language:
                languages[language] = languages.get(language, 0) + 1
            if self._is_test_file(rel):
                tests.append(rel)
            if self._is_entry_point(rel):
                entry_points.append(rel)
            if self._detect_package_manager(path):
                package_managers.add(self._detect_package_manager(path))
            if self._detect_framework(rel):
                frameworks.add(self._detect_framework(rel))
            files.append(FileSummary(path=rel, language=language, size=path.stat().st_size if path.exists() else 0, symbols=self._extract_symbols(path)))

        return ProjectSummary(
            root=str(self.root),
            files=files,
            languages=languages,
            frameworks=sorted(frameworks),
            package_managers=sorted(package_managers),
            entry_points=entry_points,
            tests=tests,
        )

    def _detect_language(self, path: Path) -> str | None:
        suffix = path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".java": "java",
            ".kt": "kotlin",
            ".rs": "rust",
            ".go": "go",
            ".html": "html",
            ".css": "css",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "shell",
        }
        return mapping.get(suffix)

    def _detect_package_manager(self, path: Path) -> str | None:
        name = path.name.lower()
        if name == "requirements.txt":
            return "pip"
        if name == "pyproject.toml":
            return "pip"
        if name == "package.json":
            return "npm"
        if name == "Cargo.toml":
            return "cargo"
        if name == "go.mod":
            return "go"
        return None

    def _detect_framework(self, rel: str) -> str | None:
        lowered = rel.lower()
        if "django" in lowered:
            return "django"
        if "flask" in lowered:
            return "flask"
        if "fastapi" in lowered:
            return "fastapi"
        if "react" in lowered:
            return "react"
        if "next" in lowered:
            return "nextjs"
        if "pytest" in lowered:
            return "pytest"
        return None

    def _is_entry_point(self, rel: str) -> bool:
        name = rel.lower()
        return name.endswith("main.py") or name.endswith("app.py") or name.endswith("server.py") or name.endswith("cli.py") or name.endswith("__main__.py")

    def _is_test_file(self, rel: str) -> bool:
        lower = rel.lower()
        return "test_" in lower or lower.endswith("_test.py") or "tests/" in lower or lower.endswith(".spec.js") or lower.endswith(".test.js")

    def _extract_symbols(self, path: Path) -> list[SymbolInfo]:
        if path.suffix.lower() != ".py":
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            return []

        items: list[SymbolInfo] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                items.append(
                    SymbolInfo(
                        name=node.name,
                        kind="class" if isinstance(node, ast.ClassDef) else "function",
                        file=path.name,
                        line=getattr(node, "lineno", 0),
                    )
                )
        return items
