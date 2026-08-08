"""AST-powered code analysis tools — provides static code intelligence for AI agent tools."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from vibe_studio.security.path_security import PathSecurity


class CodeAnalysisTools:
    """Provides AST-based inspection of Python source files: signatures, unused imports, cyclomatic complexity."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)

    def _resolve(self, path: str | Path) -> Path:
        return PathSecurity.validate_workspace_path(path, self.workspace_root)

    def get_function_signatures(self, path: str) -> list[dict[str, Any]]:
        """Extract function, method, and class signatures from a Python file using AST."""
        target = self._resolve(path)
        if not target.exists() or target.suffix != ".py":
            return []

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except Exception as exc:
            return [{"error": f"Failed to parse AST: {exc}"}]

        signatures = []

        class SignatureVisitor(ast.NodeVisitor):
            def visit_ClassDef(self, node: ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                signatures.append({
                    "kind": "class",
                    "name": node.name,
                    "bases": bases,
                    "line": node.lineno,
                    "docstring": ast.get_docstring(node) or "",
                })
                self.generic_visit(node)

            def visit_FunctionDef(self, node: ast.FunctionDef):
                self._add_func(node, is_async=False)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                self._add_func(node, is_async=True)

            def _add_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool):
                args = [a.arg for a in node.args.args]
                ret_annotation = ast.unparse(node.returns) if node.returns else None
                signatures.append({
                    "kind": "async_function" if is_async else "function",
                    "name": node.name,
                    "args": args,
                    "returns": ret_annotation,
                    "line": node.lineno,
                    "docstring": ast.get_docstring(node) or "",
                })

        SignatureVisitor().visit(tree)
        return signatures

    def find_unused_imports(self, path: str) -> list[dict[str, Any]]:
        """Identify imported symbols that are not referenced elsewhere in the file."""
        target = self._resolve(path)
        if not target.exists() or target.suffix != ".py":
            return []

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except Exception:
            return []

        imported_names: dict[str, int] = {}  # name -> lineno
        used_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        name = alias.asname or alias.name
                        imported_names[name] = node.lineno
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)

        unused = []
        for name, lineno in imported_names.items():
            if name not in used_names and not name.startswith("_"):
                unused.append({"name": name, "line": lineno})

        return unused

    def get_complexity_score(self, path: str) -> dict[str, Any]:
        """Calculate cyclomatic complexity per function (branches: if, while, for, except, with, and, or)."""
        target = self._resolve(path)
        if not target.exists() or target.suffix != ".py":
            return {"error": "Invalid Python file"}

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except Exception as exc:
            return {"error": f"Failed to parse AST: {exc}"}

        functions_complexity = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = 1  # Base complexity
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.With, ast.AsyncWith)):
                        complexity += 1
                    elif isinstance(child, ast.BoolOp) and isinstance(child.op, (ast.And, ast.Or)):
                        complexity += len(child.values) - 1

                functions_complexity.append({
                    "name": node.name,
                    "line": node.lineno,
                    "complexity": complexity,
                    "status": "high" if complexity > 10 else "moderate" if complexity > 5 else "low",
                })

        avg_comp = (
            sum(f["complexity"] for f in functions_complexity) / len(functions_complexity)
            if functions_complexity else 1.0
        )

        return {
            "file": target.relative_to(self.workspace_root).as_posix(),
            "average_complexity": round(avg_comp, 2),
            "functions": functions_complexity,
        }

    def get_dead_code(self, path: str) -> list[dict[str, Any]]:
        """Identify potentially dead (unreferenced) functions and classes in a Python file.

        A symbol is considered potentially dead if its name does not appear in any
        other Python source file within the workspace (excluding itself and test files).
        Returns a list of dicts with ``name``, ``kind``, and ``line``.
        """
        target = self._resolve(path)
        if not target.exists() or target.suffix != ".py":
            return []

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except Exception:
            return []

        # Collect all top-level definitions
        definitions: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
                if name.startswith("_"):
                    continue  # private/dunder — skip
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                definitions.append({"name": name, "kind": kind, "line": node.lineno})

        if not definitions:
            return []

        # Build a combined text of all OTHER Python files in workspace
        other_text_parts: list[str] = []
        for p in self.workspace_root.rglob("*.py"):
            if p.resolve() == target.resolve():
                continue
            skip = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
            if any(part in skip for part in p.parts):
                continue
            try:
                other_text_parts.append(p.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                pass

        combined = "\n".join(other_text_parts)

        dead = []
        for defn in definitions:
            name = defn["name"]
            # Simple heuristic: whole-word match in other files
            import re as _re
            if not _re.search(r"\b" + _re.escape(name) + r"\b", combined):
                dead.append(defn)

        return dead

    def get_import_graph(self) -> dict[str, list[str]]:
        """Build a module-level import dependency graph for all Python files in the workspace.

        Returns a dict mapping relative file path -> list of imported module names.
        Only workspace-internal imports (relative or matching a workspace package name)
        are tracked to keep the graph focused on project coupling.
        """
        # Collect workspace top-level package names
        pkg_names: set[str] = set()
        for p in self.workspace_root.glob("src/**/__init__.py"):
            # e.g. src/vibe_studio/__init__.py -> "vibe_studio"
            parts = p.relative_to(self.workspace_root).parts
            if len(parts) >= 2:
                pkg_names.add(parts[1])

        graph: dict[str, list[str]] = {}
        for p in self.workspace_root.rglob("*.py"):
            skip = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
            if any(part in skip for part in p.parts):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content)
            except Exception:
                continue

            rel = p.relative_to(self.workspace_root).as_posix()
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root in pkg_names:
                            imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        root = node.module.split(".")[0]
                        if root in pkg_names or node.level > 0:
                            imports.append(node.module)

            if imports:
                graph[rel] = sorted(set(imports))

        return graph

    def count_lines_of_code(self, path: str) -> dict[str, int]:
        """Count source lines of code (SLOC), blank lines, and comment lines for a file.

        Returns a dict with keys: ``total``, ``code``, ``blank``, ``comment``.
        Works for any text-based source file; comment detection is heuristic-based
        and handles ``#`` (Python/Ruby/Shell), ``//`` (JS/Go/Rust/C/Java), and
        ``--`` (SQL/Lua) comment styles.
        """
        target = self._resolve(path)
        if not target.exists():
            return {"error": "File not found", "total": 0, "code": 0, "blank": 0, "comment": 0}

        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            return {"error": str(exc), "total": 0, "code": 0, "blank": 0, "comment": 0}

        total = len(lines)
        blank = 0
        comment = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank += 1
            elif (
                stripped.startswith("#")
                or stripped.startswith("//")
                or stripped.startswith("--")
                or stripped.startswith("/*")
                or stripped.startswith("*")
            ):
                comment += 1

        code = total - blank - comment
        return {
            "file": target.relative_to(self.workspace_root).as_posix(),
            "total": total,
            "code": code,
            "blank": blank,
            "comment": comment,
        }

