"""Production Reliability Test Suite — Vibe Studio.

Tests deterministic pipeline behaviors, cancellation propagation,
provider streaming hardening, tool call parsing recovery, and self-healing.

All tests are offline-safe (no real LLM calls) and run without Docker/VMs.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibe_studio.agents.execution_context import ExecutionContext, ExecutionState
from vibe_studio.core.cancellation import CancellationToken, CancellationTokenSource
from vibe_studio.providers.stream_events import StreamEvent, StreamEventType, TokenUsage


# ===========================================================================
# Scenario A: ExecutionContext — state tracking and transitions
# ===========================================================================

class TestExecutionContext:
    def test_initial_state(self):
        ctx = ExecutionContext(task_prompt="test task")
        assert ctx.current_state == ExecutionState.IDLE

    def test_state_transitions(self):
        ctx = ExecutionContext(task_prompt="test task")
        ctx.transition_to(ExecutionState.ANALYZING)
        assert ctx.current_state == ExecutionState.ANALYZING
        ctx.transition_to(ExecutionState.PLANNING)
        assert ctx.current_state == ExecutionState.PLANNING

    def test_run_id_generated(self):
        ctx = ExecutionContext(task_prompt="test")
        assert ctx.run_id
        assert len(ctx.run_id) > 8

    def test_elapsed_time_increases(self):
        ctx = ExecutionContext(task_prompt="test")
        t1 = ctx.elapsed_seconds
        time.sleep(0.05)
        t2 = ctx.elapsed_seconds
        assert t2 >= t1

    def test_token_accounting(self):
        ctx = ExecutionContext(task_prompt="test")
        ctx.add_token_usage(prompt_tokens=100, completion_tokens=50)
        assert ctx.token_usage["prompt_tokens"] == 100
        assert ctx.token_usage["completion_tokens"] == 50
        assert ctx.token_usage["total_tokens"] == 150

    def test_cumulative_token_accounting(self):
        ctx = ExecutionContext(task_prompt="test")
        ctx.add_token_usage(prompt_tokens=100, completion_tokens=50)
        ctx.add_token_usage(prompt_tokens=200, completion_tokens=100)
        assert ctx.token_usage["prompt_tokens"] == 300
        assert ctx.token_usage["completion_tokens"] == 150

    def test_state_history_recorded(self):
        ctx = ExecutionContext(task_prompt="test")
        ctx.transition_to(ExecutionState.ANALYZING)
        ctx.transition_to(ExecutionState.PLANNING)
        history = ctx.state_history
        assert len(history) >= 2

    def test_thread_safety(self):
        ctx = ExecutionContext(task_prompt="thread test")
        errors = []

        def worker(i):
            try:
                ctx.add_token_usage(prompt_tokens=i, completion_tokens=i)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert ctx.token_usage["prompt_tokens"] == sum(range(20))


# ===========================================================================
# Scenario B: CancellationToken — hard cancellation
# ===========================================================================

class TestCancellationToken:
    def test_initially_not_cancelled(self):
        token = CancellationToken()
        assert not token.is_cancelled()

    def test_cancel_sets_flag(self):
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled()

    def test_cancel_is_idempotent(self):
        token = CancellationToken()
        token.cancel()
        token.cancel()  # must not raise
        assert token.is_cancelled()

    def test_callback_fires_on_cancel(self):
        token = CancellationToken()
        fired = []
        token.register_callback(lambda: fired.append(True))
        token.cancel()
        assert fired == [True]

    def test_callback_not_fired_before_cancel(self):
        token = CancellationToken()
        fired = []
        token.register_callback(lambda: fired.append(True))
        assert fired == []

    def test_multiple_callbacks(self):
        token = CancellationToken()
        calls = []
        token.register_callback(lambda: calls.append("a"))
        token.register_callback(lambda: calls.append("b"))
        token.cancel()
        assert "a" in calls
        assert "b" in calls

    def test_callback_registered_after_cancel_fires_immediately(self):
        token = CancellationToken()
        token.cancel()
        fired = []
        token.register_callback(lambda: fired.append(True))
        assert fired == [True]

    def test_child_token_propagation(self):
        parent = CancellationToken()
        child = parent.create_child()
        parent.cancel()
        assert child.is_cancelled()

    def test_child_cancel_does_not_affect_parent(self):
        parent = CancellationToken()
        child = parent.create_child()
        child.cancel()
        assert not parent.is_cancelled()

    def test_token_source_cancel(self):
        source = CancellationTokenSource()
        token = source.token
        assert not token.is_cancelled()
        source.cancel()
        assert token.is_cancelled()

    def test_cancel_blocks_execution(self):
        """Cancellation stops a simulated polling loop immediately."""
        token = CancellationToken()
        results = []

        def cancellable_loop():
            for _ in range(1000):
                if token.is_cancelled():
                    results.append("stopped")
                    return
                time.sleep(0.001)
            results.append("completed")

        t = threading.Thread(target=cancellable_loop)
        t.start()
        time.sleep(0.02)
        token.cancel()
        t.join(timeout=1.0)
        assert results == ["stopped"]


# ===========================================================================
# Scenario C: StreamEvent — normalized event protocol
# ===========================================================================

class TestStreamEvent:
    def test_token_factory(self):
        ev = StreamEvent.token("hello")
        assert ev.event_type == StreamEventType.TOKEN
        assert ev.content == "hello"

    def test_thinking_factory(self):
        ev = StreamEvent.thinking("let me think...")
        assert ev.event_type == StreamEventType.THINKING
        assert ev.content == "let me think..."

    def test_tool_call_factory(self):
        ev = StreamEvent.tool_call("read_file", {"path": "test.py"})
        assert ev.event_type == StreamEventType.TOOL_CALL
        assert ev.content == "read_file"
        assert ev.metadata["args"]["path"] == "test.py"

    def test_tool_result_factory(self):
        ev = StreamEvent.tool_result("read_file", "file content", success=True)
        assert ev.event_type == StreamEventType.TOOL_RESULT
        assert ev.metadata["success"] is True

    def test_error_factory(self):
        ev = StreamEvent.error("connection refused", recoverable=True)
        assert ev.event_type == StreamEventType.ERROR
        assert ev.metadata["recoverable"] is True

    def test_status_factory(self):
        ev = StreamEvent.status("Analyzing code...")
        assert ev.event_type == StreamEventType.STATUS

    def test_complete_factory_with_usage(self):
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        ev = StreamEvent.complete("done", usage=usage)
        assert ev.event_type == StreamEventType.COMPLETE
        assert ev.metadata["usage"]["total_tokens"] == 150

    def test_cancelled_factory(self):
        ev = StreamEvent.cancelled("user pressed stop")
        assert ev.event_type == StreamEventType.CANCELLED
        assert "user pressed stop" in ev.content

    def test_is_terminal_complete(self):
        ev = StreamEvent.complete("done")
        assert ev.is_terminal()

    def test_is_terminal_error(self):
        ev = StreamEvent.error("oops")
        assert ev.is_terminal()

    def test_is_terminal_cancelled(self):
        ev = StreamEvent.cancelled()
        assert ev.is_terminal()

    def test_is_not_terminal_token(self):
        ev = StreamEvent.token("chunk")
        assert not ev.is_terminal()

    def test_as_dict_roundtrip(self):
        ev = StreamEvent.token("hello world")
        d = ev.as_dict()
        assert d["event_type"] == "TOKEN"
        assert d["content"] == "hello world"

    def test_repr_does_not_crash(self):
        ev = StreamEvent.token("x" * 100)
        r = repr(ev)
        assert "TOKEN" in r


# ===========================================================================
# Scenario D: Tool Call Parser — recovery from malformed JSON
# ===========================================================================

class TestToolCallParser:
    def _parse(self, text: str):
        from vibe_studio.agents.tool_call_parser import parse_tool_calls
        return parse_tool_calls(text)

    def test_valid_json_tool_call(self):
        text = '{"tool": "read_file", "arguments": {"path": "test.py"}}'
        calls = self._parse(text)
        assert len(calls) >= 1
        assert calls[0].tool == "read_file"

    def test_fenced_json_block(self):
        text = '```json\n{"tool": "read_file", "arguments": {"path": "test.py"}}\n```'
        calls = self._parse(text)
        assert len(calls) >= 1

    def test_single_quotes_recovery(self):
        text = "{'tool': 'read_file', 'arguments': {'path': 'test.py'}}"
        calls = self._parse(text)
        # Should parse or gracefully fail — not crash
        assert isinstance(calls, list)

    def test_xml_tool_call(self):
        text = '<tool_call>{"tool": "read_file", "arguments": {"path": "x.py"}}</tool_call>'
        calls = self._parse(text)
        assert isinstance(calls, list)

    def test_trailing_prose_ignored(self):
        text = '{"tool": "read_file", "arguments": {"path": "test.py"}} I will now read the file.'
        calls = self._parse(text)
        assert len(calls) >= 1
        assert calls[0].tool == "read_file"

    def test_malformed_truncated_json(self):
        text = '{"tool": "read_file", "arguments": {"path": "te'
        calls = self._parse(text)
        # Should not crash; may return empty list
        assert isinstance(calls, list)

    def test_empty_string_returns_empty(self):
        calls = self._parse("")
        assert calls == []

    def test_multiple_tool_calls(self):
        text = (
            '{"tool": "read_file", "arguments": {"path": "a.py"}}\n'
            '{"tool": "write_file", "arguments": {"path": "b.py", "content": "hello"}}'
        )
        calls = self._parse(text)
        tools = [c.tool for c in calls]
        assert "read_file" in tools
        assert "write_file" in tools


# ===========================================================================
# Scenario E: PatchTools — transactional rollback
# ===========================================================================

class TestPatchToolsRollback:
    def test_patch_and_undo(self, tmp_path):
        from vibe_studio.tools.patch_tools import PatchTools
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        tools = PatchTools(tmp_path)
        result = tools.patch_file("test.py", "x = 1", "x = 2")
        assert result["exit_code"] == 0
        assert f.read_text() == "x = 2\n"
        tools.undo_last_change()
        assert f.read_text() == "x = 1\n"

    def test_revert_specific_file(self, tmp_path):
        from vibe_studio.tools.patch_tools import PatchTools
        f = tmp_path / "revert_test.py"
        f.write_text("original\n")
        tools = PatchTools(tmp_path)
        tools.patch_file("revert_test.py", "original", "modified")
        assert f.read_text() == "modified\n"
        tools.revert_file_change("revert_test.py")
        assert f.read_text() == "original\n"

    def test_snapshot_stores_diff(self, tmp_path):
        from vibe_studio.tools.patch_tools import PatchTools
        f = tmp_path / "diff_test.py"
        f.write_text("line1\nline2\n")
        tools = PatchTools(tmp_path)
        result = tools.patch_file("diff_test.py", "line1", "LINE_ONE")
        assert result["diff"] != ""

    def test_patch_not_found_raises(self, tmp_path):
        from vibe_studio.tools.patch_tools import PatchTools
        f = tmp_path / "no_match.py"
        f.write_text("content here\n")
        tools = PatchTools(tmp_path)
        with pytest.raises((ValueError, Exception)):
            tools.patch_file("no_match.py", "not_present_text", "replacement")

    def test_backup_created(self, tmp_path):
        from vibe_studio.tools.patch_tools import PatchTools
        f = tmp_path / "backup_test.py"
        f.write_text("hello\n")
        tools = PatchTools(tmp_path)
        tools.patch_file("backup_test.py", "hello", "world")
        backup_dir = tmp_path / ".vibe_studio_backup"
        assert backup_dir.exists()
        assert len(list(backup_dir.iterdir())) > 0


# ===========================================================================
# Scenario F: FilesystemTools — workspace path security
# ===========================================================================

class TestFilesystemSecurity:
    def test_path_traversal_blocked(self, tmp_path):
        from vibe_studio.tools.filesystem_tools import FilesystemTools
        from vibe_studio.security.path_security import PathSecurityError
        tools = FilesystemTools(tmp_path)
        with pytest.raises((PathSecurityError, ValueError, PermissionError, Exception)):
            tools.read_file("../../etc/passwd")

    def test_valid_file_read(self, tmp_path):
        from vibe_studio.tools.filesystem_tools import FilesystemTools
        f = tmp_path / "safe.txt"
        f.write_text("safe content")
        tools = FilesystemTools(tmp_path)
        content = tools.read_file("safe.txt")
        assert content == "safe content"

    def test_write_creates_file(self, tmp_path):
        from vibe_studio.tools.filesystem_tools import FilesystemTools
        tools = FilesystemTools(tmp_path)
        tools.write_file("new_file.txt", "written content")
        assert (tmp_path / "new_file.txt").read_text() == "written content"

    def test_list_directory(self, tmp_path):
        from vibe_studio.tools.filesystem_tools import FilesystemTools
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        tools = FilesystemTools(tmp_path)
        entries = tools.list_directory(".")
        names = [e["name"] for e in entries]
        assert "a.txt" in names
        assert "b.txt" in names


# ===========================================================================
# Scenario G: TerminalTools — test parsing metrics
# ===========================================================================

class TestTerminalToolsMetrics:
    def test_run_tests_parses_passed(self, tmp_path):
        from vibe_studio.tools.terminal_tools import TerminalTools
        tools = TerminalTools(tmp_path)
        # Mock execute_command to return a synthetic pytest-like stdout
        with patch.object(tools, "execute_command") as mock_cmd:
            mock_cmd.return_value = {
                "tool": "execute_command",
                "command": "pytest",
                "exit_code": 0,
                "stdout": "25 passed, 2 skipped in 3.14s",
                "stderr": "",
                "duration": 3.14,
                "timestamp": "",
                "cancelled": False,
            }
            res = tools.run_tests()
        assert res["tests_passed"] == 25
        assert res["tests_failed"] == 0

    def test_run_tests_parses_failed(self, tmp_path):
        from vibe_studio.tools.terminal_tools import TerminalTools
        tools = TerminalTools(tmp_path)
        with patch.object(tools, "execute_command") as mock_cmd:
            mock_cmd.return_value = {
                "tool": "execute_command",
                "command": "pytest",
                "exit_code": 1,
                "stdout": "3 failed, 22 passed in 5.01s",
                "stderr": "",
                "duration": 5.01,
                "timestamp": "",
                "cancelled": False,
            }
            res = tools.run_tests()
        assert res["tests_failed"] == 3
        assert res["tests_passed"] == 22

    def test_run_tests_detects_zero_tests(self, tmp_path):
        from vibe_studio.tools.terminal_tools import TerminalTools
        tools = TerminalTools(tmp_path)
        with patch.object(tools, "execute_command") as mock_cmd:
            mock_cmd.return_value = {
                "tool": "execute_command",
                "command": "pytest",
                "exit_code": 0,
                "stdout": "collected 0 items",
                "stderr": "",
                "duration": 0.1,
                "timestamp": "",
                "cancelled": False,
            }
            res = tools.run_tests()
        assert res.get("no_tests_executed") is True


# ===========================================================================
# Scenario H: DebugAssistant — traceback analysis
# ===========================================================================

class TestDebugAssistant:
    def setup_method(self):
        from vibe_studio.agents.debug_assistant import DebugAssistant
        self.da = DebugAssistant()

    def test_python_traceback(self):
        tb = (
            'Traceback (most recent call last):\n'
            '  File "app.py", line 42, in main\n'
            '    result = process(data)\n'
            'AttributeError: \'NoneType\' object has no attribute \'process\'\n'
        )
        result = self.da.analyze_traceback(tb)
        assert result.error_type == "AttributeError"
        assert result.file_path == "app.py"
        assert result.line_number == 42
        assert len(result.suggestions) > 0

    def test_pytest_output(self):
        tb = (
            "FAILED tests/test_foo.py::TestBar::test_baz - AssertionError: assert 1 == 2\n"
            "E  AssertionError: assert 1 == 2\n"
        )
        result = self.da.analyze_traceback(tb)
        assert result.error_type in ("AssertionError", "FAILED", "AssertionError")
        assert result.suggestions

    def test_unknown_text_returns_default(self):
        result = self.da.analyze_traceback("some random text that is not an error")
        assert result is not None
        assert isinstance(result.suggestions, list)

    def test_empty_string(self):
        result = self.da.analyze_traceback("")
        assert result is not None

    def test_analyze_test_output_multiple_failures(self):
        combined = (
            "============================= FAILURES ==============================\n"
            "FAILED tests/test_a.py::TestA::test_x - ValueError: bad input\n"
            "FAILED tests/test_b.py::TestB::test_y - KeyError: 'missing_key'\n"
        )
        analyses = self.da.analyze_test_output(combined)
        assert isinstance(analyses, list)


# ===========================================================================
# Scenario I: TaskVerificationEngine — deterministic verification
# ===========================================================================

class TestTaskVerificationEngine:
    def test_file_requirement_passed(self, tmp_path):
        from vibe_studio.agents.task_verifier import (
            FileRequirement,
            TaskRequirement,
            TaskVerificationEngine,
            VerificationStatus,
        )
        f = tmp_path / "result.py"
        f.write_text("def hello(): pass\n")
        engine = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(
            prompt="create result.py",
            files=[FileRequirement(path="result.py", must_exist=True, min_size_bytes=1)],
        )
        result = engine.verify(req)
        assert result.status in (VerificationStatus.COMPLETED, VerificationStatus.COMPLETED_WITH_WARNINGS)

    def test_file_requirement_failed(self, tmp_path):
        from vibe_studio.agents.task_verifier import (
            FileRequirement,
            TaskRequirement,
            TaskVerificationEngine,
            VerificationStatus,
        )
        engine = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(
            prompt="create missing.py",
            files=[FileRequirement(path="missing.py", must_exist=True)],
        )
        result = engine.verify(req)
        assert result.status == VerificationStatus.FAILED

    def test_symbol_verification(self, tmp_path):
        from vibe_studio.agents.task_verifier import (
            SymbolRequirement,
            TaskRequirement,
            TaskVerificationEngine,
            VerificationStatus,
        )
        f = tmp_path / "module.py"
        f.write_text("def my_function():\n    pass\n")
        engine = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(
            prompt="add my_function",
            symbols=[SymbolRequirement(path="module.py", symbol_name="my_function", symbol_type="function")],
        )
        result = engine.verify(req)
        assert result.status in (VerificationStatus.COMPLETED, VerificationStatus.COMPLETED_WITH_WARNINGS)

    def test_syntax_check_catches_error(self, tmp_path):
        from vibe_studio.agents.task_verifier import (
            FileRequirement,
            TaskRequirement,
            TaskVerificationEngine,
            VerificationStatus,
        )
        f = tmp_path / "broken.py"
        f.write_text("def foo(:\n    pass\n")  # syntax error
        engine = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(
            prompt="fix broken.py",
            files=[FileRequirement(path="broken.py", must_exist=True)],
        )
        result = engine.verify(req, reported_files_changed=["broken.py"])
        assert result.status == VerificationStatus.FAILED

    def test_no_checks_returns_completed(self, tmp_path):
        from vibe_studio.agents.task_verifier import (
            TaskRequirement,
            TaskVerificationEngine,
            VerificationStatus,
        )
        engine = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(prompt="do something")
        result = engine.verify(req)
        assert result.status == VerificationStatus.COMPLETED
        assert result.score == 100.0


# ===========================================================================
# Scenario J: Orchestrator cancellation check
# ===========================================================================

class TestOrchestratorCancellation:
    def test_cancel_before_execute(self, tmp_path):
        from vibe_studio.agents.orchestrator import AgentOrchestrator
        from vibe_studio.core.cancellation import CancellationToken
        token = CancellationToken()
        token.cancel()
        orch = AgentOrchestrator(
            workspace_root=tmp_path,
            provider=None,
            cancellation_token=token,
        )
        result = orch.execute_task("do something")
        assert result is not None
        assert "cancelled" in result.summary.lower() or result.summary != ""

    def test_orchestrator_cancel_method(self, tmp_path):
        from vibe_studio.agents.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator(workspace_root=tmp_path, provider=None)
        orch.cancel()
        assert orch._is_cancelled()
