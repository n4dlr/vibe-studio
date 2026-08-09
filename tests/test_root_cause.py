"""Tests for RootCauseAnalyzer — DataFlowTrace and ErrorFingerprint."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.agents.root_cause_analyzer import (
    DataFlowTrace, ErrorFingerprint, RootCauseAnalyzer
)


class TestErrorFingerprint:
    def test_hash_stable(self):
        fp1 = ErrorFingerprint("TypeError", "src/foo.py", 42)
        fp2 = ErrorFingerprint("TypeError", "src/foo.py", 42)
        assert fp1.hash == fp2.hash

    def test_hash_differs_on_line(self):
        fp1 = ErrorFingerprint("TypeError", "src/foo.py", 42)
        fp2 = ErrorFingerprint("TypeError", "src/foo.py", 99)
        assert fp1.hash != fp2.hash

    def test_equality(self):
        fp1 = ErrorFingerprint("ValueError", "a.py", 1)
        fp2 = ErrorFingerprint("ValueError", "a.py", 1)
        assert fp1 == fp2

    def test_hashable(self):
        fp = ErrorFingerprint("TypeError", "a.py", 10)
        s = {fp, fp}
        assert len(s) == 1


class TestDataFlowTrace:
    def test_prompt_hint_no_definitions(self):
        t = DataFlowTrace(variable="result", file_path="a.py", error_line=10)
        assert "result" in t.prompt_hint
        assert "no tracked assignment" in t.prompt_hint

    def test_prompt_hint_with_definitions(self):
        t = DataFlowTrace(
            variable="result",
            file_path="a.py",
            error_line=20,
            definitions=[(5, "result = compute(x)"), (12, "result = fallback")],
        )
        hint = t.prompt_hint
        assert "result" in hint
        assert "line 5" in hint

    def test_prompt_hint_with_call_chain(self):
        t = DataFlowTrace(
            variable="data",
            file_path="b.py",
            error_line=30,
            definitions=[(10, "data = fetch()")],
            call_chain=["fetch", "process"],
        )
        hint = t.prompt_hint
        assert "fetch" in hint


class TestRootCauseAnalyzer:
    def test_analyze_name_error(self):
        rca = RootCauseAnalyzer()
        tb = (
            'Traceback (most recent call last):\n'
            '  File "src/app.py", line 15, in run\n'
            "NameError: name 'config' is not defined"
        )
        result = rca.analyze(tb, file_path="src/app.py")
        assert result is not None
        assert result.variable == "config"
        assert result.error_line == 15

    def test_analyze_attribute_error(self):
        rca = RootCauseAnalyzer()
        tb = (
            'Traceback (most recent call last):\n'
            '  File "src/model.py", line 8, in predict\n'
            "AttributeError: 'NoneType' object has no attribute 'transform'"
        )
        result = rca.analyze(tb, file_path="src/model.py")
        assert result is not None
        assert result.variable == "transform"

    def test_analyze_with_source_code(self):
        rca = RootCauseAnalyzer()
        source = "def run():\n    result = compute()\n    return result\n"
        tb = (
            'Traceback (most recent call last):\n'
            '  File "mod.py", line 3, in run\n'
            "NameError: name 'result' is not defined"
        )
        trace = rca.analyze(tb, source_code=source, file_path="mod.py")
        assert trace is not None
        assert trace.variable == "result"

    def test_fingerprint_counter(self):
        rca = RootCauseAnalyzer()
        tb = 'File "x.py", line 5\nValueError: bad value'
        rca.analyze(tb, file_path="x.py")
        rca.analyze(tb, file_path="x.py")
        count = rca.fingerprint_count(tb, file_path="x.py")
        assert count >= 1

    def test_analyze_returns_none_for_no_error(self):
        rca = RootCauseAnalyzer()
        result = rca.analyze("")
        assert result is None

    def test_analyze_unknown_var_no_crash(self):
        rca = RootCauseAnalyzer()
        tb = 'File "foo.py", line 1\nAssertionError'
        result = rca.analyze(tb, file_path="foo.py")
        # May return DataFlowTrace with empty variable or None — no crash
        assert result is None or isinstance(result, DataFlowTrace)
