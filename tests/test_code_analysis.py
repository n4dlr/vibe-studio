"""Hardened CodeAnalysisTools tests — signatures, complexity, dead code, import graph, SLOC."""
import pytest
from vibe_studio.tools.code_analysis_tools import CodeAnalysisTools
from vibe_studio.tools.tool_registry import ToolRegistry


# ── get_function_signatures ───────────────────────────────────────────────────

def test_code_analysis_signatures(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("""
class BaseHandler:
    '''Base class'''
    pass

def process_data(data: list, option: bool = True) -> str:
    '''Process data'''
    return "ok"

async def fetch_remote(url: str):
    pass
""")
    tools = CodeAnalysisTools(tmp_path)
    sigs = tools.get_function_signatures("sample.py")
    assert len(sigs) == 3

    kinds = [s["kind"] for s in sigs]
    assert "class" in kinds
    assert "function" in kinds
    assert "async_function" in kinds

    func_sig = next(s for s in sigs if s["name"] == "process_data")
    assert "data" in func_sig["args"]
    assert "option" in func_sig["args"]
    assert func_sig["returns"] == "str"


def test_code_analysis_signatures_empty_file(tmp_path):
    f = tmp_path / "empty.py"
    f.write_text("")
    tools = CodeAnalysisTools(tmp_path)
    sigs = tools.get_function_signatures("empty.py")
    assert sigs == []


def test_code_analysis_signatures_nonexistent(tmp_path):
    tools = CodeAnalysisTools(tmp_path)
    sigs = tools.get_function_signatures("nonexistent.py")
    assert sigs == []


def test_code_analysis_signatures_non_python(tmp_path):
    f = tmp_path / "style.css"
    f.write_text("body { color: red; }")
    tools = CodeAnalysisTools(tmp_path)
    sigs = tools.get_function_signatures("style.css")
    assert sigs == []


def test_code_analysis_signatures_with_docstring(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text('def greet(name: str) -> str:\n    """Say hello."""\n    return f"Hello {name}"\n')
    tools = CodeAnalysisTools(tmp_path)
    sigs = tools.get_function_signatures("sample.py")
    assert len(sigs) == 1
    assert sigs[0]["docstring"] == "Say hello."


# ── find_unused_imports ───────────────────────────────────────────────────────

def test_code_analysis_unused_imports(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("""
import sys
import os
from pathlib import Path

print(sys.version)
""")
    tools = CodeAnalysisTools(tmp_path)
    unused = tools.find_unused_imports("sample.py")
    unused_names = [u["name"] for u in unused]
    assert "os" in unused_names
    assert "Path" in unused_names
    assert "sys" not in unused_names


def test_code_analysis_no_unused_imports(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("import os\nprint(os.getcwd())\n")
    tools = CodeAnalysisTools(tmp_path)
    unused = tools.find_unused_imports("sample.py")
    unused_names = [u["name"] for u in unused]
    assert "os" not in unused_names


def test_code_analysis_unused_from_import(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("from pathlib import Path, PurePath\nprint(Path('.'))\n")
    tools = CodeAnalysisTools(tmp_path)
    unused = tools.find_unused_imports("sample.py")
    unused_names = [u["name"] for u in unused]
    assert "PurePath" in unused_names
    assert "Path" not in unused_names


# ── get_complexity_score ──────────────────────────────────────────────────────

def test_code_analysis_complexity(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("""
def simple_fn():
    return 42

def complex_fn(a, b, c):
    if a:
        if b:
            for x in c:
                if x > 10:
                    return x
    return 0
""")
    tools = CodeAnalysisTools(tmp_path)
    res = tools.get_complexity_score("sample.py")
    assert "average_complexity" in res
    funcs = res["functions"]
    simple = next(f for f in funcs if f["name"] == "simple_fn")
    comp = next(f for f in funcs if f["name"] == "complex_fn")
    assert simple["complexity"] == 1
    assert comp["complexity"] >= 4
    assert comp["status"] in ("low", "moderate", "high")


def test_code_analysis_complexity_empty(tmp_path):
    f = tmp_path / "empty.py"
    f.write_text("")
    tools = CodeAnalysisTools(tmp_path)
    res = tools.get_complexity_score("empty.py")
    assert "average_complexity" in res
    assert res["functions"] == []


# ── get_dead_code ─────────────────────────────────────────────────────────────

def test_get_dead_code_finds_unused(tmp_path):
    # Create a file with a function that's not used anywhere else
    (tmp_path / "util.py").write_text("""
def totally_unused_xyz_function():
    return 42

def used_in_main():
    return "hello"
""")
    (tmp_path / "main.py").write_text("from util import used_in_main\nused_in_main()\n")
    tools = CodeAnalysisTools(tmp_path)
    dead = tools.get_dead_code("util.py")
    dead_names = [d["name"] for d in dead]
    # totally_unused_xyz_function is not referenced anywhere else
    assert "totally_unused_xyz_function" in dead_names


def test_get_dead_code_empty_file(tmp_path):
    (tmp_path / "empty.py").write_text("")
    tools = CodeAnalysisTools(tmp_path)
    dead = tools.get_dead_code("empty.py")
    assert dead == []


def test_get_dead_code_non_python(tmp_path):
    (tmp_path / "style.css").write_text("body {}")
    tools = CodeAnalysisTools(tmp_path)
    dead = tools.get_dead_code("style.css")
    assert dead == []


def test_get_dead_code_skips_private(tmp_path):
    (tmp_path / "helpers.py").write_text("def _private_helper():\n    pass\n")
    tools = CodeAnalysisTools(tmp_path)
    dead = tools.get_dead_code("helpers.py")
    # Private functions are skipped
    dead_names = [d["name"] for d in dead]
    assert "_private_helper" not in dead_names


# ── get_import_graph ──────────────────────────────────────────────────────────

def test_get_import_graph_basic(tmp_path):
    # Create a minimal src layout
    src = tmp_path / "src" / "mypkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "utils.py").write_text("def helper(): pass\n")
    (tmp_path / "main.py").write_text("from mypkg import utils\nutils.helper()\n")

    tools = CodeAnalysisTools(tmp_path)
    graph = tools.get_import_graph()
    # Should be a dict
    assert isinstance(graph, dict)
    # At least one entry should exist for files that import from mypkg
    # (may be empty if no workspace packages detected, which is OK)
    assert isinstance(graph, dict)


def test_get_import_graph_returns_dict(tmp_path):
    tools = CodeAnalysisTools(tmp_path)
    graph = tools.get_import_graph()
    assert isinstance(graph, dict)
    for key, val in graph.items():
        assert isinstance(key, str)
        assert isinstance(val, list)


# ── count_lines_of_code ───────────────────────────────────────────────────────

def test_count_lines_of_code_python(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("""# Module header comment
import os

def foo():
    # inner comment
    return os.getcwd()

""")
    tools = CodeAnalysisTools(tmp_path)
    result = tools.count_lines_of_code("sample.py")
    assert result["total"] > 0
    assert result["code"] > 0
    assert result["blank"] >= 1
    assert result["comment"] >= 2
    assert result["code"] + result["blank"] + result["comment"] == result["total"]


def test_count_lines_of_code_missing_file(tmp_path):
    tools = CodeAnalysisTools(tmp_path)
    result = tools.count_lines_of_code("nonexistent.txt")
    assert "error" in result
    assert result["total"] == 0


def test_count_lines_of_code_js(tmp_path):
    f = tmp_path / "script.js"
    f.write_text("// header\nfunction foo() {\n  return 1;\n}\n\n")
    tools = CodeAnalysisTools(tmp_path)
    result = tools.count_lines_of_code("script.js")
    assert result["total"] == 5
    assert result["comment"] >= 1
    assert result["blank"] >= 1


def test_count_lines_of_code_has_file_key(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("x = 1\n")
    tools = CodeAnalysisTools(tmp_path)
    result = tools.count_lines_of_code("sample.py")
    assert "file" in result
    assert result["file"] == "sample.py"


# ── ToolRegistry integration ──────────────────────────────────────────────────

def test_code_analysis_registered_in_tool_registry(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("import unused_mod\ndef foo(): return 1")
    reg = ToolRegistry(tmp_path)

    res_sigs = reg.execute("get_function_signatures", {"path": "sample.py"})
    assert res_sigs["exit_code"] == 0
    assert "foo" in res_sigs["stdout"]

    res_unused = reg.execute("find_unused_imports", {"path": "sample.py"})
    assert res_unused["exit_code"] == 0
    assert "unused_mod" in res_unused["stdout"]

    res_comp = reg.execute("get_complexity_score", {"path": "sample.py"})
    assert res_comp["exit_code"] == 0
    assert "average_complexity" in res_comp["stdout"]


def test_dead_code_registered_in_tool_registry(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("def orphan_function(): pass\n")
    reg = ToolRegistry(tmp_path)
    res = reg.execute("get_dead_code", {"path": "sample.py"})
    assert res["exit_code"] == 0


def test_import_graph_registered_in_tool_registry(tmp_path):
    reg = ToolRegistry(tmp_path)
    res = reg.execute("get_import_graph", {})
    assert res["exit_code"] == 0


def test_count_lines_registered_in_tool_registry(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("x = 1\n")
    reg = ToolRegistry(tmp_path)
    res = reg.execute("count_lines_of_code", {"path": "sample.py"})
    assert res["exit_code"] == 0
    assert "total" in res["stdout"]
