"""Comprehensive test suite for FuzzyPatchEngine, ASTSyntaxGuard, ContextVirtualizer, and SpecialistSwarm."""
from __future__ import annotations

from pathlib import Path
import pytest

from vibe_studio.tools.patch_tools import FuzzyPatchEngine, PatchTools
from vibe_studio.tools.filesystem_tools import ASTSyntaxGuard, FilesystemTools
from vibe_studio.context.context_compactor import ContextVirtualizer
from vibe_studio.swarm.specialist_swarm import SpecialistSwarm


def test_fuzzy_patch_engine_whitespace_tolerance():
    old = (
        "def compute_total(items):\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        total += item.price\n"
        "    return total\n"
    )
    # Target has slightly different whitespace / indentation
    target = (
        "  for item in items:\n"
        "      total += item.price\n"
    )
    match = FuzzyPatchEngine.find_best_match(old, target)
    assert match is not None
    start, end, matched = match
    assert "for item in items:" in matched


def test_fuzzy_patch_indentation_alignment():
    target_block = "        total += item.price\n"
    replacement_block = "total += item.discounted_price\n"
    aligned = FuzzyPatchEngine.align_indentation(target_block, replacement_block)
    assert aligned.startswith("        ")
    assert "discounted_price" in aligned


def test_patch_tools_fuzzy_replace(tmp_path: Path):
    pt = PatchTools(tmp_path)
    file = tmp_path / "app.py"
    file.write_text(
        "class OrderService:\n"
        "    def checkout(self):\n"
        "        print('Starting checkout')\n"
        "        return True\n"
    )
    # Patch with slight whitespace variation
    res = pt.patch_file("app.py", target_text="    def checkout(self):\n        print('Starting checkout')", replacement_text="    def checkout(self):\n        logger.info('Starting checkout')")
    assert res["status"] == "success"
    assert "logger.info" in file.read_text()


def test_ast_syntax_guard_python_colon_healing():
    broken_py = "def calculate_discount(price, rate)\n    return price * rate\n"
    healed, warnings = ASTSyntaxGuard.validate_and_heal("calc.py", broken_py)
    assert "def calculate_discount(price, rate):" in healed
    assert len(warnings) > 0


def test_ast_syntax_guard_json_trailing_comma_healing():
    import json
    broken_json = '{\n  "name": "vibe_studio",\n  "version": "1.0",\n}'
    healed, warnings = ASTSyntaxGuard.validate_and_heal("config.json", broken_json)
    data = json.loads(healed)
    assert data["version"] == "1.0"


def test_filesystem_tools_write_with_guard(tmp_path: Path):
    ft = FilesystemTools(tmp_path)
    ft.write_file("main.py", "def greet(name)\n    print('Hello ' + name)\n")
    content = (tmp_path / "main.py").read_text()
    assert "def greet(name):" in content


def test_context_virtualizer_outline_python():
    code = (
        "import os\n\n"
        "class UserManager:\n"
        "    '''Manager for users.'''\n"
        "    def create_user(self, username: str, email: str) -> bool:\n"
        "        # internal complex logic\n"
        "        x = 10\n"
        "        return True\n\n"
        "def helper_func(data: list) -> int:\n"
        "    return len(data)\n"
    )
    outline = ContextVirtualizer.outline_python(code)
    assert "class UserManager" in outline
    assert "def create_user(self, username, email)" in outline
    assert "def helper_func(data)" in outline
    assert "x = 10" not in outline  # Compressed out implementation details


def test_context_virtualizer_compress_history():
    history = [
        {"tool": "read_file", "args": {"path": "main.py"}, "observation": {"exit_code": 0}},
        {"tool": "search_text", "args": {"query": "auth"}, "observation": {"exit_code": 0}},
        {"tool": "patch_file", "args": {"path": "auth.py"}, "observation": {"exit_code": 0}},
        {"tool": "run_tests", "args": {}, "observation": {"exit_code": 0, "stdout": "3 passed"}},
    ]
    summary = ContextVirtualizer.compress_history(history, keep_recent=2)
    assert "Prior Steps Summary" in summary
    assert "Recent Detailed Steps" in summary


def test_specialist_swarm_mission(tmp_path: Path):
    swarm = SpecialistSwarm(tmp_path)
    result = swarm.execute_mission("Create Python Hello World application with tests")
    assert result.success is True
    assert result.quality_score.score >= 70
    assert "main.py" in result.files_changed
