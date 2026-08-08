"""Hardened DebugAssistant tests — all runtimes + new methods."""
import pytest
from vibe_studio.agents.debug_assistant import DebugAssistant, ErrorRuntime


# ── Python ────────────────────────────────────────────────────────────────────

def test_debug_assistant_python_tb():
    tb = """Traceback (most recent call last):
  File "src/vibe_studio/app/main.py", line 42, in process_task
    result = data["missing_key"]
KeyError: 'missing_key'
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.PYTHON
    assert res.error_type == "KeyError"
    assert res.file_path == "src/vibe_studio/app/main.py"
    assert res.line_number == 42
    assert res.confidence > 0.8
    assert any("dict.get" in s for s in res.suggestions)


def test_debug_assistant_python_attribute_error():
    tb = """Traceback (most recent call last):
  File "app.py", line 5, in main
    result = obj.method()
AttributeError: 'NoneType' object has no attribute 'method'
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.PYTHON
    assert "AttributeError" in res.error_type
    assert any("None" in s for s in res.suggestions)


def test_debug_assistant_python_import_error():
    tb = """Traceback (most recent call last):
  File "main.py", line 1, in <module>
    import nonexistent_package
ModuleNotFoundError: No module named 'nonexistent_package'
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.PYTHON
    assert any("pip install" in s for s in res.suggestions)


# ── Pytest ────────────────────────────────────────────────────────────────────

def test_debug_assistant_pytest_output():
    tb = """================ FAILURES ================
________________ test_example ________________
    def test_example():
>       assert 1 == 2
E       AssertionError: assert 1 == 2
FAILED tests/test_foo.py::test_example - AssertionError: assert 1 == 2
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime in (ErrorRuntime.PYTEST, ErrorRuntime.PYTHON)
    assert "AssertionError" in res.error_type
    assert res.suggestions


def test_debug_assistant_pytest_type_error():
    tb = """FAILED tests/test_service.py::TestService::test_init - TypeError: __init__() got an unexpected keyword argument 'x'"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime in (ErrorRuntime.PYTEST, ErrorRuntime.PYTHON, ErrorRuntime.UNKNOWN)


# ── JavaScript ────────────────────────────────────────────────────────────────

def test_debug_assistant_js_tb():
    tb = """TypeError: Cannot read property 'map' of undefined
    at renderList (src/components/List.js:15:22)
    at App (src/App.js:8:5)
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.JAVASCRIPT
    assert res.error_type == "TypeError"
    assert res.file_path == "src/components/List.js"
    assert res.line_number == 15


def test_debug_assistant_js_range_error():
    tb = """RangeError: Maximum call stack size exceeded
    at recurse (utils.js:10:5)
    at recurse (utils.js:11:5)
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.JAVASCRIPT


# ── Rust ─────────────────────────────────────────────────────────────────────

def test_debug_assistant_rust_panic():
    tb = "thread 'main' panicked at 'index out of bounds: the len is 3 but the index is 5', src/main.rs:24:10"
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.RUST
    assert res.error_type == "panic"
    assert res.file_path == "src/main.rs"
    assert res.line_number == 24


def test_debug_assistant_rust_unwrap_panic():
    tb = "thread 'main' panicked at 'called `Option::unwrap()` on a `None` value', src/lib.rs:88:5"
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.RUST
    assert res.line_number == 88


# ── Go ────────────────────────────────────────────────────────────────────────

def test_debug_assistant_go_panic():
    tb = """goroutine 1 [running]:
panic: runtime error: index out of range [1] with length 0

goroutine 1 [running]:
main.main()
\t/home/user/project/main.go:15 +0x68
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.GO
    assert res.error_type == "panic"
    assert "index out of range" in res.error_message


def test_debug_assistant_go_nil_panic():
    tb = """panic: runtime error: invalid memory address or nil pointer dereference

goroutine 1 [running]:
main.processData(...)
\t/home/user/app/server.go:42 +0x1a
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.GO


# ── Java ─────────────────────────────────────────────────────────────────────

def test_debug_assistant_java_npe():
    tb = """java.lang.NullPointerException: Cannot invoke method getName()
    at com.example.service.UserService.getUser(UserService.java:45)
    at com.example.controller.UserController.handleRequest(UserController.java:23)
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.JAVA
    assert "NullPointerException" in res.error_type
    assert res.line_number == 45


# ── Unknown ───────────────────────────────────────────────────────────────────

def test_debug_assistant_unknown_input():
    da = DebugAssistant()
    res = da.analyze_traceback("something went wrong, maybe")
    assert res.runtime == ErrorRuntime.UNKNOWN
    assert res.suggestions


def test_debug_assistant_empty_input():
    da = DebugAssistant()
    res = da.analyze_traceback("")
    assert res.runtime == ErrorRuntime.UNKNOWN


# ── format_report ─────────────────────────────────────────────────────────────

def test_debug_assistant_format_report():
    tb = """Traceback (most recent call last):
  File "main.py", line 10, in foo
AttributeError: 'NoneType' object has no attribute 'bar'
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    report = res.format_report()
    assert "=== Debug Analysis" in report
    assert "AttributeError" in report
    assert "Suggestions:" in report


def test_debug_assistant_format_report_with_frames():
    tb = """Traceback (most recent call last):
  File "module_a.py", line 5, in outer
    inner()
  File "module_b.py", line 10, in inner
    raise ValueError("bad value")
ValueError: bad value
"""
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    report = res.format_report()
    assert "Call stack" in report


# ── analyze_test_output ───────────────────────────────────────────────────────

def test_analyze_test_output_empty():
    da = DebugAssistant()
    results = da.analyze_test_output("")
    assert results == []


def test_analyze_test_output_single_failure():
    output = """Traceback (most recent call last):
  File "src/utils.py", line 22, in compute
    return data["key"]
KeyError: 'key'
"""
    da = DebugAssistant()
    results = da.analyze_test_output(output)
    assert len(results) >= 1
    assert results[0].error_type == "KeyError"


def test_analyze_test_output_sorted_by_confidence():
    output = """Traceback (most recent call last):
  File "src/utils.py", line 10, in compute
    return data["key"]
KeyError: 'key'
"""
    da = DebugAssistant()
    results = da.analyze_test_output(output)
    if len(results) > 1:
        # Sorted by confidence descending
        for i in range(len(results) - 1):
            assert results[i].confidence >= results[i + 1].confidence


# ── find_fix_location ─────────────────────────────────────────────────────────

def test_find_fix_location_basic():
    tb = """Traceback (most recent call last):
  File "src/main.py", line 7, in run
    process()
RuntimeError: something failed
"""
    da = DebugAssistant()
    analysis = da.analyze_traceback(tb)
    loc = da.find_fix_location(analysis)
    assert "file" in loc
    assert "line" in loc
    assert "error_type" in loc
    assert "message" in loc
    assert "runtime" in loc
    assert "confidence" in loc


def test_find_fix_location_with_workspace(tmp_path):
    tb = f"""Traceback (most recent call last):
  File "{tmp_path}/src/app.py", line 15, in main
    crash()
ValueError: crash
"""
    da = DebugAssistant()
    analysis = da.analyze_traceback(tb)
    loc = da.find_fix_location(analysis, workspace_root=str(tmp_path))
    # Path should be made relative
    assert not loc["file"].startswith(str(tmp_path))


def test_find_fix_location_relative_path():
    tb = """Traceback (most recent call last):
  File "module.py", line 5, in fn
    raise TypeError("oops")
TypeError: oops
"""
    da = DebugAssistant()
    analysis = da.analyze_traceback(tb)
    loc = da.find_fix_location(analysis)
    assert loc["file"] == "module.py"
    assert loc["line"] == 5
