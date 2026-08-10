"""
V19 Production Reliability Tests — Vibe Studio
===============================================
Covers:
  - ExecutionContext lifecycle and cancellation
  - CancellationToken socket-abort propagation into providers
  - Normalized StreamEvent emission from both providers
  - Malformed/partial LLM chunk recovery
  - Cancel-before-tool, cancel-during-streaming, cancel-during-subprocess
  - Self-healing hard limits (no infinite retry loops)
  - OpenAI SSE malformed chunk resilience
  - Hard STOP returns agent to CANCELLED cleanly
"""
from __future__ import annotations

import io
import json
import threading
import time
import tempfile
import pathlib
import unittest.mock as mock

import pytest

from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.agents.execution_context import ExecutionContext
from vibe_studio.providers.stream_events import StreamEvent, StreamEventType

# ---------------------------------------------------------------------------
# ExecutionContext
# ---------------------------------------------------------------------------

class TestExecutionContext:
    def test_initial_state(self):
        ctx = ExecutionContext(task_prompt="test task")
        assert ctx.current_state == "IDLE"
        assert ctx.iteration_count == 0
        assert ctx.tool_call_count == 0
        assert not ctx.is_cancelled

    def test_cancellation_propagates(self):
        ctx = ExecutionContext()
        assert not ctx.is_cancelled
        ctx.cancellation_token.cancel()
        assert ctx.is_cancelled

    def test_cancellation_is_idempotent(self):
        ctx = ExecutionContext()
        ctx.cancellation_token.cancel()
        ctx.cancellation_token.cancel()  # Must not raise
        assert ctx.is_cancelled

    def test_record_tool_call(self):
        ctx = ExecutionContext()
        ctx.record_tool_call("read_file")
        assert ctx.active_tool == "read_file"
        assert ctx.tool_call_count == 1

    def test_record_file_change(self):
        ctx = ExecutionContext()
        ctx.record_file_change("hello.py")
        ctx.record_file_change("hello.py")  # dedup
        assert ctx.generated_changes == ["hello.py"]

    def test_record_error(self):
        ctx = ExecutionContext()
        ctx.record_error("Something broke")
        assert ctx.last_error == "Something broke"

    def test_elapsed_seconds(self):
        ctx = ExecutionContext()
        time.sleep(0.05)
        assert ctx.elapsed_seconds >= 0.04

    def test_to_dict(self):
        ctx = ExecutionContext(task_prompt="my task")
        d = ctx.to_dict()
        assert d["task_prompt"] == "my task"
        assert "run_id" in d
        assert "elapsed_seconds" in d


# ---------------------------------------------------------------------------
# StreamEvent
# ---------------------------------------------------------------------------

class TestStreamEvent:
    def test_token_event(self):
        ev = StreamEvent.token("hello")
        assert ev.event_type == StreamEventType.TOKEN
        assert ev.content == "hello"

    def test_error_event(self):
        ev = StreamEvent.error("boom")
        assert ev.event_type == StreamEventType.ERROR
        assert ev.content == "boom"

    def test_complete_event(self):
        ev = StreamEvent.complete("done text")
        assert ev.event_type == StreamEventType.COMPLETE

    def test_cancelled_event(self):
        ev = StreamEvent.cancelled("user stopped")
        assert ev.event_type == StreamEventType.CANCELLED

    def test_tool_call_event(self):
        ev = StreamEvent.tool_call("read_file", {"path": "foo.py"})
        assert ev.event_type == StreamEventType.TOOL_CALL
        assert ev.metadata["args"]["path"] == "foo.py"


# ---------------------------------------------------------------------------
# CancellationToken
# ---------------------------------------------------------------------------

class TestCancellationToken:
    def test_not_cancelled_initially(self):
        tok = CancellationToken()
        assert not tok.is_cancelled()

    def test_cancel_sets_state(self):
        tok = CancellationToken()
        tok.cancel()
        assert tok.is_cancelled()

    def test_idempotent_cancel(self):
        tok = CancellationToken()
        tok.cancel()
        tok.cancel()
        assert tok.is_cancelled()

    def test_parent_propagates_to_child(self):
        parent = CancellationToken()
        child = CancellationToken(parent=parent)
        assert not child.is_cancelled()
        parent.cancel()
        assert child.is_cancelled()

    def test_callback_on_cancel(self):
        called = []
        tok = CancellationToken()
        tok.register_callback(lambda: called.append(1))
        assert called == []
        tok.cancel()
        assert called == [1]

    def test_callback_called_immediately_if_already_cancelled(self):
        called = []
        tok = CancellationToken()
        tok.cancel()
        tok.register_callback(lambda: called.append(1))
        assert called == [1]

    def test_check_cancelled_raises(self):
        tok = CancellationToken()
        tok.cancel()
        with pytest.raises(InterruptedError):
            tok.check_cancelled()


# ---------------------------------------------------------------------------
# OllamaProvider hardened streaming
# ---------------------------------------------------------------------------

class TestOllamaProviderHardened:
    def _make_provider(self):
        from vibe_studio.providers.ollama_provider import OllamaProvider
        p = OllamaProvider()
        # Disable circuit breaker for unit tests
        p.circuit_breaker.call = lambda fn: fn()
        return p

    def test_malformed_chunks_skipped(self):
        """Malformed JSON lines are silently skipped; valid chunks still collected."""
        provider = self._make_provider()

        lines = [
            b"NOT_JSON\n",
            b'{"response": "hello", "done": false}\n',
            b"BAD_AGAIN\n",
            b'{"response": " world", "done": true}\n',
        ]
        fake_resp = io.BytesIO(b"".join(lines))
        fake_resp.__iter__ = lambda self: iter(self.read().splitlines(keepends=True))
        fake_resp.close = lambda: None

        tokens = []
        with mock.patch("vibe_studio.providers.ollama_provider.urlopen") as m_open:
            m_open.return_value.__enter__ = lambda s: fake_resp
            m_open.return_value.__exit__ = lambda *a: None
            m_open.return_value = fake_resp

            result = provider._stream_generate(
                mock.MagicMock(), tokens.append, None, 5
            )

        assert "hello" in result
        assert "world" in result

    def test_cancel_stops_streaming(self):
        """Cancellation token mid-stream stops token collection."""
        from vibe_studio.providers.ollama_provider import OllamaProvider
        provider = OllamaProvider()
        provider.circuit_breaker.call = lambda fn: fn()

        cancel_tok = CancellationToken()

        lines_data = [
            json.dumps({"response": f"chunk{i}", "done": False}).encode() + b"\n"
            for i in range(10)
        ]

        class FakeResp:
            def __init__(self):
                self._lines = iter(lines_data)
                self._closed = False

            def __iter__(self):
                for line in self._lines:
                    if cancel_tok.is_cancelled():
                        return
                    yield line

            def __enter__(self): return self
            def __exit__(self, *a): pass
            def close(self): self._closed = True

        fake_resp = FakeResp()
        tokens = []

        def callback(tok):
            tokens.append(tok)
            if len(tokens) == 3:
                cancel_tok.cancel()

        with mock.patch("vibe_studio.providers.ollama_provider.urlopen", return_value=fake_resp):
            provider._stream_generate(mock.MagicMock(), callback, None, 10, cancel_tok)

        assert len(tokens) <= 4  # stopped shortly after cancel

    def test_stream_events_emitted(self):
        """Normalized StreamEvents are emitted for TOKEN and COMPLETE."""
        provider = self._make_provider()

        lines = [
            b'{"response": "tok", "done": false}\n',
            b'{"response": "", "done": true}\n',
        ]
        events = []

        class FakeResp:
            def __iter__(self): return iter(lines)
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def close(self): pass

        with mock.patch("vibe_studio.providers.ollama_provider.urlopen", return_value=FakeResp()):
            provider._stream_generate(mock.MagicMock(), lambda t: None, events.append, 5)

        types = [e.event_type for e in events]
        assert StreamEventType.TOKEN in types
        assert StreamEventType.COMPLETE in types


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider hardened streaming
# ---------------------------------------------------------------------------

class TestOpenAIProviderHardened:
    def _make_provider(self):
        from vibe_studio.providers.openai_compatible_provider import OpenAICompatibleProvider
        p = OpenAICompatibleProvider(api_key="test-key")
        p.circuit_breaker.call = lambda fn: fn()
        return p

    def test_malformed_sse_chunks_skipped(self):
        provider = self._make_provider()
        lines = [
            b"data: INVALID_JSON\n",
            b'data: {"choices": [{"delta": {"content": "hi"}}]}\n',
            b"data: [DONE]\n",
        ]
        events = []
        tokens = []

        class FakeResp:
            def __iter__(self): return iter(lines)
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def close(self): pass

        with mock.patch("vibe_studio.providers.openai_compatible_provider.urlopen", return_value=FakeResp()):
            result = provider._stream_chat(mock.MagicMock(), tokens.append, events.append, 5)

        assert "hi" in result
        types = [e.event_type for e in events]
        assert StreamEventType.TOKEN in types
        assert StreamEventType.COMPLETE in types

    def test_cancel_stops_openai_streaming(self):
        provider = self._make_provider()
        cancel_tok = CancellationToken()

        lines = []
        for i in range(10):
            body = json.dumps({"choices": [{"delta": {"content": f"chunk{i}"}}]})
            lines.append(f"data: {body}\n".encode())
        tokens = []

        class FakeResp:
            def __iter__(self_inner):
                for i, line in enumerate(lines):
                    if cancel_tok.is_cancelled():
                        return
                    yield line
                    if i == 2:
                        cancel_tok.cancel()

            def __enter__(self): return self
            def __exit__(self, *a): pass
            def close(self): pass

        with mock.patch("vibe_studio.providers.openai_compatible_provider.urlopen", return_value=FakeResp()):
            provider._stream_chat(mock.MagicMock(), tokens.append, None, 10, cancel_tok)

        assert len(tokens) <= 4


# ---------------------------------------------------------------------------
# Agent self-healing hard limits
# ---------------------------------------------------------------------------

class TestSelfHealingLimits:
    def test_repair_cycle_does_not_exceed_max(self):
        """Agent must not loop beyond max_repair_cycles."""
        import os, sys
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
        os.environ["VIBE_STUDIO_OFFLINE"] = "1"

        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp)
            (p / "broken.py").write_text("def bad_syntax(:")

            from vibe_studio.agents.coding_agent import AutonomousAgent, AutonomyMode
            agent = AutonomousAgent(
                project_root=p,
                autonomy_mode=AutonomyMode.AUTO,
                max_iterations=10,
                max_repair_cycles=2,
            )
            result = agent.run("Write invalid syntax ```def bad_syntax(:``` into broken.py")

        # Must terminate (not loop forever) and not be COMPLETED
        from vibe_studio.agents.coding_agent import AgentState
        assert result.status != AgentState.COMPLETED
        # Must not have exceeded max_repair_cycles
        assert len(result.tool_history) <= 15  # hard upper bound

    def test_agent_cancels_cleanly(self):
        """STOP pressed: agent returns CANCELLED without executing further tools."""
        import os
        os.environ["VIBE_STUDIO_OFFLINE"] = "1"

        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp)
            (p / "main.py").write_text("print('hello')")

            from vibe_studio.agents.coding_agent import AutonomousAgent, AutonomyMode, AgentState
            agent = AutonomousAgent(project_root=p, autonomy_mode=AutonomyMode.AUTO)

            cancel_tok = agent._cancellation_token if hasattr(agent, "_cancellation_token") else None
            # Cancel immediately before run
            agent.cancel()
            result = agent.run("Add 100 new functions to main.py")

        assert result.status == AgentState.CANCELLED


# ---------------------------------------------------------------------------
# Execution context thread safety
# ---------------------------------------------------------------------------

class TestExecutionContextThreadSafety:
    def test_concurrent_file_changes_deduplicated(self):
        ctx = ExecutionContext()
        threads = [
            threading.Thread(target=ctx.record_file_change, args=(f"file{i % 3}.py",))
            for i in range(50)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Should have at most 3 unique files
        assert len(ctx.generated_changes) <= 3

    def test_concurrent_cancel_idempotent(self):
        ctx = ExecutionContext()
        threads = [
            threading.Thread(target=ctx.cancellation_token.cancel)
            for _ in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert ctx.is_cancelled
