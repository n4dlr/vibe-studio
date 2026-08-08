import pytest
from vibe_studio.tools.code_analysis_tools import CodeAnalysisTools
from vibe_studio.tools.tool_registry import ToolRegistry


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
