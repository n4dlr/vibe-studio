from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vibe_studio.security.path_security import PathSecurity


class CodeTools:
    """Implement code analysis, ecosystem detection, package configuration, and dependency tools."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)

    def detect_language(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".html": "html",
            ".css": "css",
            ".scss": "css",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".java": "java",
            ".kt": "kotlin",
            ".rs": "rust",
            ".go": "go",
            ".php": "php",
            ".sh": "shell",
            ".bash": "shell",
            ".sql": "sql",
        }
        return mapping.get(ext, "unknown")

    def detect_framework(self) -> str:
        res = self.detect_project_type()
        fw = res.get("frameworks", [])
        return fw[0] if fw else "unknown"

    def detect_project_type(self) -> dict[str, Any]:
        root = self.workspace_root
        languages: set[str] = set()
        frameworks: set[str] = set()
        build_systems: set[str] = set()
        test_frameworks: set[str] = set()

        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists() or (root / "setup.py").exists():
            languages.add("python")
            build_systems.add("pip/setuptools")
            if (root / "pytest.ini").exists() or (root / "tests").exists():
                test_frameworks.add("pytest")
        if (root / "package.json").exists():
            languages.add("javascript/typescript")
            build_systems.add("npm/yarn/pnpm")
            try:
                pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "react" in deps:
                    frameworks.add("react")
                if "next" in deps:
                    frameworks.add("nextjs")
                if "vue" in deps:
                    frameworks.add("vue")
                if "@angular/core" in deps:
                    frameworks.add("angular")
                if "jest" in deps or "vitest" in deps:
                    test_frameworks.add("jest/vitest")
            except Exception:
                pass

        if (root / "Cargo.toml").exists():
            languages.add("rust")
            build_systems.add("cargo")

        if (root / "go.mod").exists():
            languages.add("go")
            build_systems.add("go modules")

        if (root / "pom.xml").exists() or (root / "build.gradle").exists():
            languages.add("java/kotlin")
            build_systems.add("maven/gradle")

        if (root / "CMakeLists.txt").exists() or (root / "Makefile").exists():
            languages.add("c/cpp")
            build_systems.add("cmake/make")

        return {
            "root": str(root),
            "languages": sorted(languages),
            "frameworks": sorted(frameworks),
            "build_systems": sorted(build_systems),
            "test_frameworks": sorted(test_frameworks),
        }

    def detect_entry_points(self) -> list[str]:
        entry_points = []
        for p in self.workspace_root.rglob("*"):
            if not p.is_file():
                continue
            name = p.name.lower()
            if name in {"main.py", "app.py", "server.py", "index.js", "index.ts", "main.ts", "main.rs", "main.go", "app.js", "server.js", "App.tsx", "main.tsx"}:
                entry_points.append(p.relative_to(self.workspace_root).as_posix())
        return sorted(entry_points)

    def detect_dependencies(self) -> dict[str, list[str]]:
        deps: dict[str, list[str]] = {"python": [], "npm": []}

        req_file = self.workspace_root / "requirements.txt"
        if req_file.exists():
            for line in req_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    deps["python"].append(line)

        pkg_file = self.workspace_root / "package.json"
        if pkg_file.exists():
            try:
                pkg_data = json.loads(pkg_file.read_text(encoding="utf-8"))
                for k in pkg_data.get("dependencies", {}).keys():
                    deps["npm"].append(k)
            except Exception:
                pass

        return deps

    def detect_build_system(self) -> str:
        res = self.detect_project_type()
        bs = res.get("build_systems", [])
        return bs[0] if bs else "unknown"

    def detect_test_framework(self) -> str:
        res = self.detect_project_type()
        tf = res.get("test_frameworks", [])
        return tf[0] if tf else "unknown"

    def inspect_package_configuration(self) -> dict[str, Any]:
        configs = {}
        for filename in ["package.json", "pyproject.toml", "Cargo.toml", "go.mod", "requirements.txt", "pytest.ini", "tsconfig.json"]:
            f = self.workspace_root / filename
            if f.exists():
                try:
                    configs[filename] = f.read_text(encoding="utf-8", errors="replace")[:2000]
                except Exception:
                    pass
        return configs

    # ------------------------------------------------------------------
    # Agent Semantic LSP Tools
    # ------------------------------------------------------------------

    def lsp_goto_definition(self, file_path: str, line: int = 1, column: int = 0, symbol: str = "") -> list[dict[str, Any]]:
        target = PathSecurity.validate_workspace_path(file_path, self.workspace_root)
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine
        engine = CodeIntelligenceEngine(self.workspace_root)
        defs = engine.find_definition(symbol=symbol, file_path=target, line=line, column=column)
        return [
            {"file": d.file, "line": d.line, "column": d.column, "symbol": d.symbol, "source": d.source}
            for d in defs
        ]

    def lsp_find_references(self, file_path: str, line: int = 1, column: int = 0, symbol: str = "") -> list[dict[str, Any]]:
        target = PathSecurity.validate_workspace_path(file_path, self.workspace_root)
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine
        engine = CodeIntelligenceEngine(self.workspace_root)
        return engine.find_references(symbol=symbol, current_file=target, line=line, column=column)

    def lsp_hover(self, file_path: str, line: int = 1, column: int = 0, symbol: str = "") -> dict[str, Any]:
        target = PathSecurity.validate_workspace_path(file_path, self.workspace_root)
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine
        engine = CodeIntelligenceEngine(self.workspace_root)
        hover_info = engine.get_hover_info(symbol=symbol, file_path=target, line=line, column=column)
        if hover_info:
            return {
                "symbol": hover_info.symbol,
                "kind": hover_info.kind,
                "file": hover_info.file,
                "line": hover_info.line,
                "docstring": hover_info.docstring,
                "source": hover_info.source,
            }
        return {"error": f"No hover info found for symbol '{symbol}'"}

    def lsp_get_diagnostics(self, file_path: str) -> list[dict[str, Any]]:
        target = PathSecurity.validate_workspace_path(file_path, self.workspace_root)
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine
        engine = CodeIntelligenceEngine(self.workspace_root)
        return engine.get_diagnostics(target)

    def lsp_document_symbols(self, file_path: str) -> list[dict[str, Any]]:
        target = PathSecurity.validate_workspace_path(file_path, self.workspace_root)
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine
        engine = CodeIntelligenceEngine(self.workspace_root)
        syms = engine.get_document_symbols(target)
        return [{"name": s.name, "kind": s.kind, "file": s.file, "line": s.line} for s in syms]

    def lsp_workspace_symbols(self, query: str) -> list[dict[str, Any]]:
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine
        engine = CodeIntelligenceEngine(self.workspace_root)
        syms = engine.get_workspace_symbols(query)
        return [{"name": s.name, "kind": s.kind, "file": s.file, "line": s.line} for s in syms]
