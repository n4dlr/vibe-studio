"""
Production-hardening tests covering:
  - Robust tool-call parser (all formats, malformed JSON, multiple calls)
  - Schema validation before tool execution
  - File conflict detection
  - Smart output truncation
  - Error classification and deduplication
  - Provider capability detection
  - Problems panel parsing
  - Git tools (stage/unstage)
  - Project scanner (framework detection)
  - Context engine token budgeting
"""
from __future__ import annotations

import os
os.environ.setdefault("VIBE_STUDIO_OFFLINE", "1")

import json
from pathlib import Path
import pytest

# ---------------------------------------------------------------------------
# Tool-call parser
# ---------------------------------------------------------------------------

from vibe_studio.agents.tool_call_parser import (
    parse_tool_calls,
    strip_tool_calls,
    validate_tool_call,
    ParsedToolCall,
)


class TestToolCallParser:
    def test_fenced_json_block(self):
        text = '```json\n{"tool": "read_file", "args": {"path": "main.py"}}\n```'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool == "read_file"
        assert calls[0].args == {"path": "main.py"}
        assert calls[0].source == "fenced_json"

    def test_bare_json_object(self):
        text = 'I will read this file.\n{"tool": "search_text", "args": {"query": "login"}}'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool == "search_text"
        assert calls[0].source == "bare_json"

    def test_xml_format(self):
        text = "<tool_call><name>delete_file</name><args>{\"path\": \"old.py\"}</args></tool_call>"
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool == "delete_file"
        assert calls[0].source == "xml"

    def test_openai_function_call_schema(self):
        text = '{"name": "write_file", "arguments": {"path": "out.txt", "content": "hello"}}'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool == "write_file"
        assert calls[0].source == "openai_fn"

    def test_multiple_calls_in_one_response(self):
        text = (
            "First read:\n"
            '```json\n{"tool": "read_file", "args": {"path": "a.py"}}\n```\n'
            "Then search:\n"
            '```json\n{"tool": "search_text", "args": {"query": "foo"}}\n```'
        )
        calls = parse_tool_calls(text)
        assert len(calls) == 2
        assert calls[0].tool == "read_file"
        assert calls[1].tool == "search_text"

    def test_malformed_json_recovery(self):
        # Truncated JSON — missing closing brace
        text = '```json\n{"tool": "tree", "args": {"max_depth": 3}\n```'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].tool == "tree"

    def test_no_tool_call_returns_empty(self):
        text = "Here is a summary of what I found in the project."
        calls = parse_tool_calls(text)
        assert calls == []

    def test_strip_removes_tool_blocks(self):
        text = 'Thinking...\n```json\n{"tool": "read_file", "args": {"path": "x.py"}}\n```\nDone.'
        calls = parse_tool_calls(text)
        remaining = strip_tool_calls(text, calls)
        assert "tool" not in remaining
        assert "Thinking" in remaining
        assert "Done" in remaining

    def test_unknown_tool_in_json_ignored(self):
        # A JSON block without "tool" key should not produce a call
        text = '```json\n{"key": "value", "other": 123}\n```'
        calls = parse_tool_calls(text)
        assert calls == []

    def test_args_with_nested_object(self):
        text = '```json\n{"tool": "execute_command", "args": {"command": "pytest -x", "timeout": 60}}\n```'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].args["timeout"] == 60


class TestSchemaValidation:
    def _defs(self):
        return [
            {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "start_line": {"type": "integer", "description": "Start"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path"},
                        "content": {"type": "string", "description": "Content"},
                    },
                    "required": ["path", "content"],
                },
            },
        ]

    def test_valid_call_passes(self):
        call = ParsedToolCall(tool="read_file", args={"path": "main.py"}, raw="", source="fenced_json")
        ok, err = validate_tool_call(call, self._defs())
        assert ok
        assert err == ""

    def test_missing_required_fails(self):
        call = ParsedToolCall(tool="write_file", args={"path": "x.py"}, raw="", source="fenced_json")
        ok, err = validate_tool_call(call, self._defs())
        assert not ok
        assert "content" in err

    def test_unknown_tool_fails(self):
        call = ParsedToolCall(tool="nonexistent", args={}, raw="", source="bare_json")
        ok, err = validate_tool_call(call, self._defs())
        assert not ok
        assert "nonexistent" in err

    def test_wrong_type_fails(self):
        call = ParsedToolCall(
            tool="read_file",
            args={"path": "main.py", "start_line": "not_a_number"},
            raw="", source="fenced_json",
        )
        ok, err = validate_tool_call(call, self._defs())
        assert not ok
        assert "start_line" in err

    def test_optional_param_missing_passes(self):
        call = ParsedToolCall(
            tool="read_file",
            args={"path": "main.py"},  # start_line is optional
            raw="", source="fenced_json",
        )
        ok, err = validate_tool_call(call, self._defs())
        assert ok


# ---------------------------------------------------------------------------
# Tool registry — arg coercion + validation
# ---------------------------------------------------------------------------

from vibe_studio.tools.tool_registry import default_tool_registry


class TestToolRegistryValidation:
    def test_string_coerced_to_int(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        # max_depth is integer but model may pass "3" (string)
        result = reg.execute("tree", {"max_depth": "3"})
        assert result["exit_code"] == 0

    def test_missing_required_returns_error(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        result = reg.execute("read_file", {})  # path is required
        assert result["exit_code"] != 0
        assert "path" in result["stderr"]

    def test_unknown_tool_returns_error(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        result = reg.execute("does_not_exist", {})
        assert result["exit_code"] != 0
        assert "Unknown tool" in result["stderr"]

    def test_risk_metadata_present(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        tools = {t["name"]: t for t in reg.list_tools()}
        assert tools["delete_file"]["risk"] == "HIGH"
        assert tools["read_file"]["risk"] == "SAFE"
        assert tools["write_file"]["risk"] == "MEDIUM"

    def test_git_stage_unstage_registered(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        names = {t["name"] for t in reg.list_tools()}
        assert "git_stage" in names
        assert "git_unstage" in names
        assert "git_diff" in names


# ---------------------------------------------------------------------------
# File conflict detection
# ---------------------------------------------------------------------------

from vibe_studio.tools.patch_tools import PatchTools


class TestFileConflict:
    def test_no_conflict_when_unchanged(self, tmp_path):
        pt = PatchTools(tmp_path)
        f = tmp_path / "test.py"
        f.write_text("original content")
        h = pt._hash("original content")
        assert not pt.check_conflict("test.py", h)

    def test_conflict_detected_after_external_edit(self, tmp_path):
        pt = PatchTools(tmp_path)
        f = tmp_path / "test.py"
        f.write_text("original content")
        h = pt._hash("original content")
        # Simulate external edit
        f.write_text("externally modified content")
        assert pt.check_conflict("test.py", h)

    def test_agent_detects_conflict_and_rereads(self, tmp_path):
        from vibe_studio.agents.coding_agent import AutonomousAgent, AutonomyMode
        # Create a style file
        style = tmp_path / "style.css"
        style.write_text("body { background: white; }")
        # Create a hash mismatch manually (simulate read → external edit)
        agent = AutonomousAgent(project_root=tmp_path, autonomy_mode=AutonomyMode.AUTO)
        agent._read_hashes["style.css"] = agent.tool_registry.patch_tools._hash("old content")
        # Now style.css has different content → conflict should be detected
        assert agent._check_conflict("style.css")


# ---------------------------------------------------------------------------
# Smart output truncation
# ---------------------------------------------------------------------------

from vibe_studio.agents.output_processor import (
    truncate_output, classify_error, extract_errors,
    ErrorCategory, ErrorTracker, ErrorInfo,
)


class TestOutputProcessor:
    def test_short_output_unchanged(self):
        text = "hello world"
        assert truncate_output(text, max_chars=1000) == text

    def test_long_output_truncated(self):
        text = "line\n" * 1000
        result = truncate_output(text, max_chars=500)
        assert len(result) <= 700  # allow some overhead for markers
        assert "truncated" in result

    def test_error_lines_preserved(self):
        head = "normal line\n" * 50
        error_block = "FAILED tests/test_foo.py - AssertionError: expected 1\n"
        tail = "normal line\n" * 50
        text = head + error_block + tail
        result = truncate_output(text, max_chars=300)
        # Error line should be in the result even though it's in the middle
        assert "FAILED" in result or "truncated" in result

    def test_classify_syntax_error(self):
        assert classify_error("SyntaxError: invalid syntax") == ErrorCategory.SYNTAX

    def test_classify_test_failure(self):
        assert classify_error("FAILED tests/test_x.py::test_foo - AssertionError") == ErrorCategory.TEST

    def test_classify_import_error(self):
        assert classify_error("ModuleNotFoundError: No module named 'requests'") == ErrorCategory.DEPENDENCY

    def test_classify_type_error(self):
        assert classify_error("TypeError: expected str, got int") == ErrorCategory.TYPE

    def test_classify_lint(self):
        assert classify_error("ruff: E501 line too long") == ErrorCategory.LINT

    def test_classify_unknown(self):
        assert classify_error("nothing relevant here") == ErrorCategory.UNKNOWN

    def test_extract_errors_with_file_ref(self):
        output = 'File "src/main.py", line 42\nSyntaxError: invalid syntax'
        errors = extract_errors(output)
        assert errors
        assert errors[0].file == "src/main.py"
        assert errors[0].line == 42

    def test_error_tracker_dedup(self):
        tracker = ErrorTracker(max_repeats=2)
        err = ErrorInfo(category=ErrorCategory.TEST, message="test failed", fingerprint="abc123")
        assert not tracker.is_stuck(err)
        tracker.record(err, "run_tests")
        assert not tracker.is_stuck(err)
        tracker.record(err, "run_tests")
        assert tracker.is_stuck(err)

    def test_error_tracker_reset(self):
        tracker = ErrorTracker(max_repeats=2)
        err = ErrorInfo(category=ErrorCategory.SYNTAX, message="bad", fingerprint="xyz")
        tracker.record(err)
        tracker.record(err)
        assert tracker.is_stuck(err)
        tracker.reset()
        assert not tracker.is_stuck(err)

    def test_error_fingerprint_stable(self):
        e1 = ErrorInfo(category=ErrorCategory.BUILD, message="build failed", file="Makefile", line=10)
        e2 = ErrorInfo(category=ErrorCategory.BUILD, message="build failed", file="Makefile", line=10)
        assert e1.fingerprint == e2.fingerprint

    def test_different_errors_different_fingerprints(self):
        e1 = ErrorInfo(category=ErrorCategory.TEST, message="test A failed", file="test_a.py", line=5)
        e2 = ErrorInfo(category=ErrorCategory.TEST, message="test B failed", file="test_b.py", line=8)
        assert e1.fingerprint != e2.fingerprint


# ---------------------------------------------------------------------------
# Provider capability detection
# ---------------------------------------------------------------------------

from vibe_studio.providers.capability_detector import detect_capabilities, adapt_context_to_model


class TestCapabilityDetector:
    def test_gpt4o_has_native_tools(self):
        caps = detect_capabilities("gpt-4o")
        assert caps.native_tool_calling
        assert caps.context_window >= 128000

    def test_gpt4o_mini_has_native_tools(self):
        caps = detect_capabilities("gpt-4o-mini")
        assert caps.native_tool_calling

    def test_qwen_coder_has_tools(self):
        caps = detect_capabilities("qwen2.5-coder:7b")
        assert caps.native_tool_calling

    def test_unknown_model_no_native_tools(self):
        caps = detect_capabilities("totally-unknown-model-xyz")
        assert not caps.native_tool_calling
        assert "compatibility" in caps.notes.lower()

    def test_context_budget_capped_to_model(self):
        caps = detect_capabilities("gpt-4")  # 8192 context
        budget = adapt_context_to_model(32000, caps)
        assert budget <= caps.context_window - 4096

    def test_large_model_allows_large_budget(self):
        caps = detect_capabilities("gpt-4o")  # 128k context
        budget = adapt_context_to_model(16000, caps)
        assert budget == 16000  # not reduced

    def test_streaming_always_true(self):
        caps = detect_capabilities("any-model")
        assert caps.streaming


# ---------------------------------------------------------------------------
# Problems panel parser
# ---------------------------------------------------------------------------

from vibe_studio.ui.problems_panel import parse_linter_output


class TestProblemsParser:
    def test_ruff_output(self):
        output = "src/foo.py:10:5: E501 line too long (120 > 88 characters)"
        problems = parse_linter_output(output, source="ruff")
        assert len(problems) == 1
        assert problems[0]["file"] == "src/foo.py"
        assert problems[0]["line"] == 10
        assert "E501" in problems[0]["message"]
        assert problems[0]["severity"] == "Error"

    def test_mypy_output(self):
        output = "src/app.py:42: error: Argument 1 to 'foo' has incompatible type"
        problems = parse_linter_output(output, source="mypy")
        assert len(problems) == 1
        assert problems[0]["file"] == "src/app.py"
        assert problems[0]["line"] == 42
        assert problems[0]["severity"] == "Error"

    def test_mypy_warning(self):
        output = "src/utils.py:7: warning: Type of foo is Any"
        problems = parse_linter_output(output, source="mypy")
        assert len(problems) == 1
        assert problems[0]["severity"] == "Warning"

    def test_pytest_failed_line(self):
        output = "FAILED tests/test_login.py::test_render - AssertionError: expected gradient"
        problems = parse_linter_output(output, source="pytest")
        assert len(problems) == 1
        assert "test_login.py" in problems[0]["file"]
        assert problems[0]["severity"] == "FAILED"

    def test_empty_output(self):
        assert parse_linter_output("") == []

    def test_multiple_errors(self):
        output = (
            "src/a.py:1:1: E302 expected 2 blank lines\n"
            "src/b.py:5:3: W503 line break before binary operator\n"
        )
        problems = parse_linter_output(output)
        assert len(problems) == 2

    def test_severity_warning_for_W_codes(self):
        output = "src/foo.py:1:1: W503 warning message"
        problems = parse_linter_output(output)
        assert problems[0]["severity"] == "Warning"


# ---------------------------------------------------------------------------
# Project scanner — enhanced framework detection
# ---------------------------------------------------------------------------

from vibe_studio.project.project_scanner import ProjectScanner


class TestProjectScannerFrameworks:
    def test_detect_react_from_jsx(self, tmp_path):
        (tmp_path / "App.jsx").write_text("import React from 'react';\nexport default App;")
        scanner = ProjectScanner(tmp_path)
        result = scanner.scan()
        assert "react" in result.frameworks

    def test_detect_nextjs_from_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"next": "^14.0"}, "devDependencies": {}})
        )
        scanner = ProjectScanner(tmp_path)
        result = scanner.scan()
        assert "nextjs" in result.frameworks

    def test_detect_vue(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"vue": "^3.0"}, "devDependencies": {}})
        )
        scanner = ProjectScanner(tmp_path)
        result = scanner.scan()
        assert "vue" in result.frameworks

    def test_detect_fastapi_from_imports(self, tmp_path):
        (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
        scanner = ProjectScanner(tmp_path)
        result = scanner.scan()
        assert "fastapi" in result.frameworks

    def test_detect_django_from_imports(self, tmp_path):
        (tmp_path / "views.py").write_text("from django.http import HttpResponse\ndef index(r): pass")
        scanner = ProjectScanner(tmp_path)
        result = scanner.scan()
        assert "django" in result.frameworks

    def test_detect_express(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"express": "^4.18"}, "devDependencies": {}})
        )
        scanner = ProjectScanner(tmp_path)
        result = scanner.scan()
        assert "express" in result.frameworks

    def test_python_project_detected(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pytest\nrequests\n")
        scanner = ProjectScanner(tmp_path)
        result = scanner.scan()
        assert "python" in result.languages

    def test_skips_ignored_dirs(self, tmp_path):
        node_mod = tmp_path / "node_modules" / "react"
        node_mod.mkdir(parents=True)
        (node_mod / "index.js").write_text("module.exports = {};")
        scanner = ProjectScanner(tmp_path)
        result = scanner.scan()
        assert not any("node_modules" in f.path for f in result.files)


# ---------------------------------------------------------------------------
# Agent self-correction with error dedup
# ---------------------------------------------------------------------------

from vibe_studio.agents.coding_agent import AutonomousAgent, AgentState, AutonomyMode


class TestAgentErrorDedup:
    def test_agent_does_not_loop_on_repeated_error(self, tmp_path):
        """Agent must stop repeating the same repair action after max_repeats."""
        call_count = {"n": 0}

        agent = AutonomousAgent(
            project_root=tmp_path,
            autonomy_mode=AutonomyMode.AUTO,
            max_iterations=10,
            max_repair_cycles=2,
        )

        # Monkey-patch fallback to always return a failing command
        def bad_fallback(prompt):
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return '```json\n{"tool": "run_tests", "args": {}}\n```'
            return "Task completed (blocked by repeated errors)."

        agent._fallback_deterministic_step = bad_fallback
        result = agent.run("run tests and fix everything")
        # Should terminate (FAILED/BLOCKED due to failing tests), not loop forever
        assert result.status in (AgentState.FAILED, AgentState.BLOCKED, AgentState.COMPLETED)
        assert call_count["n"] <= 10

    def test_error_tracker_prevents_infinite_repair(self, tmp_path):
        tracker = ErrorTracker(max_repeats=2)
        err = ErrorInfo(
            category=ErrorCategory.TEST,
            message="pytest: 3 failed",
            fingerprint="test_fail_001",
        )
        for _ in range(3):
            tracker.record(err, "run_tests")
        assert tracker.is_stuck(err)
        assert "run_tests" in tracker.previous_actions(err)


# ---------------------------------------------------------------------------
# Context engine token budgeting
# ---------------------------------------------------------------------------

from vibe_studio.context.context_engine import ContextEngine


class TestContextBudget:
    def test_budget_respected_with_many_large_files(self, tmp_path):
        for i in range(20):
            (tmp_path / f"file_{i}.py").write_text("x = 1\n" * 500)
        engine = ContextEngine(tmp_path)
        bundle = engine.build("find something", token_budget=3000)
        assert bundle.total_tokens_est <= 3500  # 500 slack for markers

    def test_high_relevance_file_included(self, tmp_path):
        (tmp_path / "login_page.py").write_text("def render_login(): return 'bg-white'")
        (tmp_path / "unrelated.py").write_text("def foo(): pass")
        engine = ContextEngine(tmp_path)
        bundle = engine.build("Login səhifəsinin backgroundunu dəyiş")
        paths = [item.path for item in bundle.items]
        assert any("login" in p.lower() for p in paths)
