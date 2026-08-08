import pytest
from vibe_studio.agents.debug_assistant import DebugAssistant, ErrorRuntime


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


def test_debug_assistant_rust_panic():
    tb = "thread 'main' panicked at 'index out of bounds: the len is 3 but the index is 5', src/main.rs:24:10"
    da = DebugAssistant()
    res = da.analyze_traceback(tb)
    assert res.runtime == ErrorRuntime.RUST
    assert res.error_type == "panic"
    assert res.file_path == "src/main.rs"
    assert res.line_number == 24


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
