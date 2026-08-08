"""SelfLearningTests — identifies untested functions and generates unit test boilerplate templates."""
from __future__ import annotations

import ast
from pathlib import Path
from dataclasses import dataclass


@dataclass
class UntestedFunction:
    file: str
    function_name: str
    line: int


class SelfLearningTests:
    """Scans project modules to discover functions without corresponding test coverage."""

    def find_untested_functions(self, workspace_root: Path) -> list[UntestedFunction]:
        untested: list[UntestedFunction] = []
        test_file_names: set[str] = set()

        for p in workspace_root.rglob("*"):
            if p.is_file() and p.name.startswith("test_") and p.suffix == ".py":
                try:
                    test_file_names.add(p.read_text(encoding="utf-8", errors="replace").lower())
                except Exception:
                    pass

        skip = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", "tests"}
        for p in workspace_root.rglob("*.py"):
            if not p.is_file() or any(part in skip for part in p.parts) or p.name.startswith("test_"):
                continue

            try:
                rel = p.relative_to(workspace_root).as_posix()
                tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name.startswith("_"):
                            continue
                        # Check if function name appears in test suite text
                        is_tested = any(node.name.lower() in t_text for t_text in test_file_names)
                        if not is_tested:
                            untested.append(
                                UntestedFunction(
                                    file=rel,
                                    function_name=node.name,
                                    line=getattr(node, "lineno", 1),
                                )
                            )
            except Exception:
                continue

        return untested

    def generate_test_template(self, func: UntestedFunction) -> str:
        mod_name = Path(func.file).stem
        return f"""import pytest
from {mod_name} import {func.function_name}

def test_{func.function_name}_default():
    # TODO: Implement unit test for {func.function_name}
    result = {func.function_name}()
    assert result is not None
"""
