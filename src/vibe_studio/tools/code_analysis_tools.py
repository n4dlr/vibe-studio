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
