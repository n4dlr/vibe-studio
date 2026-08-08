from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SymbolInfo:
    name: str
    kind: str  # class, function, method, interface, type, route, component
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
    """Build a fast multi-ecosystem AST & regex symbol index across the project."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def scan(self) -> ProjectSummary:
        files: list[FileSummary] = []
        languages: dict[str, int] = {}
        frameworks: set[str] = set()
        package_managers: set[str] = set()
        entry_points: list[str] = []
        tests: list[str] = []

        if not self.root.exists():
            return ProjectSummary(
                root=str(self.root),
                files=[],
                languages={},
                frameworks=[],
                package_managers=[],
                entry_points=[],
                tests=[],
            )

        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or self._should_skip(path):
                continue

            rel = path.relative_to(self.root).as_posix()
            language = self._detect_language(path)
            if language:
                languages[language] = languages.get(language, 0) + 1

            if self._is_test_file(rel):
                tests.append(rel)
            if self._is_entry_point(rel):
                entry_points.append(rel)

            pm = self._detect_package_manager(path)
            if pm:
                package_managers.add(pm)

            fw = self._detect_framework(rel, path)
            if fw:
                frameworks.add(fw)

            symbols = self._extract_symbols(path, language)
            files.append(
                FileSummary(
                    path=rel,
                    language=language or "unknown",
                    size=path.stat().st_size if path.exists() else 0,
                    symbols=symbols,
                )
            )

        return ProjectSummary(
            root=str(self.root),
            files=files,
            languages=languages,
            frameworks=sorted(frameworks),
            package_managers=sorted(package_managers),
            entry_points=entry_points,
            tests=tests,
        )

    def _should_skip(self, path: Path) -> bool:
        rel = path.relative_to(self.root).as_posix()
        parts = rel.split("/")
        ignored = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache"}
        return any(p in ignored or p.endswith(".egg-info") for p in parts)

    def _detect_language(self, path: Path) -> str | None:
        suffix = path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".java": "java",
            ".kt": "kotlin",
            ".rs": "rust",
            ".go": "go",
            ".php": "php",
            ".html": "html",
            ".css": "css",
            ".scss": "css",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "shell",
        }
        return mapping.get(suffix)

    def _detect_package_manager(self, path: Path) -> str | None:
        name = path.name.lower()
        if name in {"requirements.txt", "pyproject.toml", "setup.py"}:
            return "pip"
        if name == "package.json":
            return "npm"
        if name == "Cargo.toml":
            return "cargo"
        if name == "go.mod":
            return "go"
        if name in {"pom.xml", "build.gradle"}:
            return "maven/gradle"
        return None

    def _detect_framework(self, rel: str, path: Path) -> str | None:
        lowered = rel.lower()
        if "django" in lowered:
            return "django"
        if "flask" in lowered:
            return "flask"
        if "fastapi" in lowered:
            return "fastapi"
        if "react" in lowered or lowered.endswith((".jsx", ".tsx")):
            return "react"
        if "next" in lowered:
            return "nextjs"
        if "vue" in lowered:
            return "vue"
        if "angular" in lowered:
            return "angular"
        if "pytest" in lowered:
            return "pytest"
        if "pyside6" in lowered or "pyqt" in lowered:
            return "pyside6"
        return None

    def _is_entry_point(self, rel: str) -> bool:
        name = rel.lower()
        return (
            name.endswith("main.py")
            or name.endswith("app.py")
            or name.endswith("server.py")
            or name.endswith("cli.py")
            or name.endswith("__main__.py")
            or name.endswith("index.js")
            or name.endswith("index.ts")
            or name.endswith("main.ts")
            or name.endswith("main.rs")
            or name.endswith("main.go")
        )

    def _is_test_file(self, rel: str) -> bool:
        lower = rel.lower()
        return (
            "test_" in lower
            or lower.endswith("_test.py")
            or "tests/" in lower
            or lower.endswith(".spec.js")
            or lower.endswith(".test.js")
            or lower.endswith(".spec.ts")
            or lower.endswith(".test.ts")
        )

    def _extract_symbols(self, path: Path, language: str | None) -> list[SymbolInfo]:
        if not language:
            return []

        rel_file = path.relative_to(self.root).as_posix()
        items: list[SymbolInfo] = []

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        if language == "python":
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        items.append(SymbolInfo(name=node.name, kind="function", file=rel_file, line=getattr(node, "lineno", 0)))
                    elif isinstance(node, ast.ClassDef):
                        items.append(SymbolInfo(name=node.name, kind="class", file=rel_file, line=getattr(node, "lineno", 0)))
            except Exception:
                pass
        else:
            # Multi-language regex symbol parsing for JS, TS, React, Go, Rust, Java, C/C++
            for idx, line in enumerate(content.splitlines(), start=1):
                func_match = re.search(r"\b(function|fn|def|func|const|let|var)\s+([A-Za-z0-9_]+)\b", line)
                if func_match:
                    items.append(SymbolInfo(name=func_match.group(2), kind="function", file=rel_file, line=idx))

                class_match = re.search(r"\b(class|struct|interface|type|enum)\s+([A-Za-z0-9_]+)\b", line)
                if class_match:
                    items.append(SymbolInfo(name=class_match.group(2), kind="class", file=rel_file, line=idx))

        return items
