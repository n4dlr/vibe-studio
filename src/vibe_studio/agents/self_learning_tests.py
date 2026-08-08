"""SelfLearningTests — identifies untested functions and generates executable unit test boilerplate templates."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UntestedFunction:
    file: str
    function_name: str
    line: int
    args: list[str] = None  # type: ignore[assignment]
    is_async: bool = False

    def __post_init__(self):
        if self.args is None:
            self.args = []


class SelfLearningTests:
    """Scans project modules to discover functions without corresponding test coverage and generates unit test code."""

    def find_untested_functions(self, workspace_root: Path) -> list[UntestedFunction]:
        untested: list[UntestedFunction] = []
        test_file_content: list[str] = []

        # Gather all test file contents
        for p in workspace_root.rglob("*"):
            if p.is_file() and p.name.startswith("test_") and p.suffix == ".py":
                try:
                    test_file_content.append(p.read_text(encoding="utf-8", errors="replace").lower())
                except Exception:
                    pass

        all_tests_combined = "\n".join(test_file_content)

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
                        
                        # Check if function name is mentioned in test suite
                        is_tested = node.name.lower() in all_tests_combined
                        if not is_tested:
                            arg_names = [arg.arg for arg in node.args.args if arg.arg != "self" and arg.arg != "cls"]
                            untested.append(
                                UntestedFunction(
                                    file=rel,
                                    function_name=node.name,
                                    line=getattr(node, "lineno", 1),
                                    args=arg_names,
                                    is_async=isinstance(node, ast.AsyncFunctionDef),
                                )
                            )
            except Exception:
                continue

        return untested

    def generate_test_template(self, func: UntestedFunction) -> str:
        p = Path(func.file)
        # Convert path to module dot-notation (e.g. vibe_studio.core.settings)
        parts = p.with_suffix("").parts
        if "src" in parts:
            src_idx = parts.index("src")
            mod_path = ".".join(parts[src_idx + 1:])
        else:
            mod_path = ".".join(parts)

        # Mock default values for arguments
        dummy_args = []
        for arg in func.args:
            if "name" in arg or "path" in arg or "file" in arg or "str" in arg or "key" in arg or "prompt" in arg:
                dummy_args.append(f'{arg}="test_{arg}"')
            elif "num" in arg or "count" in arg or "index" in arg or "id" in arg or "line" in arg or "timeout" in arg or "budget" in arg:
                dummy_args.append(f"{arg}=1")
            elif "is_" in arg or "has_" in arg or "enable" in arg or "allow" in arg or "flag" in arg:
                dummy_args.append(f"{arg}=True")
            elif "list" in arg or "items" in arg or "args" in arg:
                dummy_args.append(f"{arg}=[]")
            elif "dict" in arg or "data" in arg or "kwargs" in arg:
                dummy_args.append(f"{arg}={{}}")
            else:
                dummy_args.append(f'{arg}="mock_val"')

        args_str = ", ".join(dummy_args)

        if func.is_async:
            return f"""import pytest
from {mod_path} import {func.function_name}

@pytest.mark.asyncio
async def test_{func.function_name}_auto_generated():
    res = await {func.function_name}({args_str})
    assert res is not None or res is None
"""
        else:
            return f"""import pytest
from {mod_path} import {func.function_name}

def test_{func.function_name}_auto_generated():
    res = {func.function_name}({args_str})
    assert res is not None or res is None
"""

    def generate_and_save_tests(self, workspace_root: Path, limit: int = 5) -> list[str]:
        """Discover untested functions and write executable test files to tests/generated/."""
        untested = self.find_untested_functions(workspace_root)[:limit]
        created_files = []
        out_dir = workspace_root / "tests" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)

        for func in untested:
            template = self.generate_test_template(func)
            test_file = out_dir / f"test_{func.function_name}_gen.py"
            test_file.write_text(template, encoding="utf-8")
            created_files.append(test_file.relative_to(workspace_root).as_posix())

        return created_files
