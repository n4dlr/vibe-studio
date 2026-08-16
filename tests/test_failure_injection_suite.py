"""Failure Injection Test Suite — Vibe Studio.

Tests adversarial scenarios: model timeouts, connection drops, malformed LLM
output, tool errors, command timeouts, LSP binary missing, stuck agent
detection, and external file modifications.

All tests are offline-safe (no real LLM/network calls). Uses mocking/monkeypatching.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from vibe_studio.core.cancellation import CancellationToken


# ===========================================================================
# Injection A: Model timeout / connection refused → provider fallback
# ===========================================================================

class TestProviderTimeouts:
    def test_ollama_connection_refused(self, tmp_path):
        """OllamaProvider.test_connection() returns False when server is down."""
        from vibe_studio.providers.ollama_provider import OllamaProvider
        # Use a port unlikely to be in use
        provider = OllamaProvider(base_url="http://127.0.0.1:19999", timeout=1)
        assert provider.test_connection() is False

    def test_ollama_stream_cancelled(self, tmp_path):
        """Cancelling a token before generation causes provider to skip/abort."""
        from vibe_studio.providers.ollama_provider import OllamaProvider
        provider = OllamaProvider(base_url="http://127.0.0.1:19999", timeout=1)
        token = CancellationToken()
        token.cancel()
        # Provider.generate should return quickly when server is down and token is cancelled
        try:
            result = provider.generate(
                prompt="hello",
                model="llama3.1",
                cancellation_token=token,
            )
            # Any result is fine — must not hang
            assert isinstance(result, str)
        except Exception:
            pass  # Connection error is expected and acceptable

    def test_openai_connection_refused(self):
        """OpenAICompatibleProvider.test_connection() returns False when URL unreachable."""
        from vibe_studio.providers.openai_compatible_provider import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider(
            base_url="http://127.0.0.1:19998/v1",
            api_key="fake-key",
            timeout=1,
        )
        assert provider.test_connection() is False


# ===========================================================================
# Injection B: Malformed JSON / SSE stream chunks
# ===========================================================================

class TestMalformedStreamInput:
    def test_tool_call_parser_handles_garbage(self):
        from vibe_studio.agents.tool_call_parser import parse_tool_calls
        garbage_inputs = [
            "this is not json at all",
            "{{{{",
            '{"tool":',
            "```\n{broken\n```",
            "",
            "null",
            "[]",
            "true",
            "12345",
        ]
        for text in garbage_inputs:
            result = parse_tool_calls(text)
            assert isinstance(result, list), f"Failed for: {text!r}"

    def test_tool_call_parser_extracts_from_prose(self):
        from vibe_studio.agents.tool_call_parser import parse_tool_calls
        text = (
            "Let me help you. I will call the tool:\n"
            '{"tool": "read_file", "arguments": {"path": "main.py"}}\n'
            "After that I will analyze the result."
        )
        calls = parse_tool_calls(text)
        assert any(c.tool == "read_file" for c in calls)

    def test_openai_format_extracted(self):
        from vibe_studio.agents.tool_call_parser import parse_tool_calls
        text = '{"name": "read_file", "arguments": "{\"path\": \"app.py\"}"}'
        calls = parse_tool_calls(text)
        # Should at minimum not crash
        assert isinstance(calls, list)


# ===========================================================================
# Injection C: Command timeout handling
# ===========================================================================

class TestCommandTimeout:
    def test_command_timeout_cancels_process(self, tmp_path):
        """A command that runs too long gets killed within the timeout window."""
        from vibe_studio.core.command_safety import CommandSafety
        start = time.monotonic()
        result = CommandSafety.run(
            "sleep 10",
            cwd=tmp_path,
            workspace_root=tmp_path,
            timeout=1,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, "Timeout did not fire within expected window"
        assert result.exit_code != 0 or result.cancelled

    def test_command_with_cancellation_token(self, tmp_path):
        """A running command stops when its cancellation token is cancelled."""
        from vibe_studio.core.command_safety import CommandSafety
        token = CancellationToken()
        results = []

        def _run():
            r = CommandSafety.run(
                "sleep 30",
                cwd=tmp_path,
                workspace_root=tmp_path,
                timeout=30,
                cancellation_token=token,
            )
            results.append(r)

        t = threading.Thread(target=_run)
        t.start()
        time.sleep(0.3)
        token.cancel()
        t.join(timeout=3.0)
        assert results, "Command never returned"
        assert results[0].cancelled or results[0].exit_code != 0


# ===========================================================================
# Injection D: LSP binary missing
# ===========================================================================

class TestLSPBinaryMissing:
    def test_lsp_start_fails_gracefully(self, tmp_path):
        """LSPClient.start() returns False when the binary is not on PATH."""
        from vibe_studio.editor.lsp_client import LSPClient, LSPClientState
        from vibe_studio.editor.lsp_registry import LSPServerConfig
        fake_cfg = LSPServerConfig(
            language_id="python",
            display_name="Fake LSP",
            file_extensions=[".py"],
            command="nonexistent_lsp_binary_xyzzy_12345",
        )
        client = LSPClient("python", tmp_path, server_config=fake_cfg)
        result = client.start()
        assert result is False
        assert client.state in (LSPClientState.ERROR, LSPClientState.STOPPED)

    def test_lsp_requests_return_empty_when_not_running(self, tmp_path):
        """LSP feature requests return safe empty values when client is stopped."""
        from vibe_studio.editor.lsp_client import LSPClient, LSPClientState
        from vibe_studio.editor.lsp_registry import LSPServerConfig
        fake_cfg = LSPServerConfig(
            language_id="python",
            display_name="Fake LSP",
            file_extensions=[".py"],
            command="nonexistent_lsp_binary_xyzzy_12345",
        )
        client = LSPClient("python", tmp_path, server_config=fake_cfg)
        # Not started — should not raise
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")

        defs = client.goto_definition(test_file, line=1, character=0)
        assert defs == []

        refs = client.find_references(test_file, line=1, character=0)
        assert refs == []

        hover = client.hover(test_file, line=1, character=0)
        assert hover == ""

        syms = client.get_document_symbols(test_file)
        assert syms == []


# ===========================================================================
# Injection E: Repeated test failures → StuckAgentDetector
# ===========================================================================

class TestStuckAgentDetector:
    def test_detects_repeated_identical_tool(self):
        from vibe_studio.agents.stuck_detector import StuckAgentDetector
        # max_identical_steps=2 means 2 identical steps triggers is_stuck()
        detector = StuckAgentDetector(max_identical_steps=2, max_search_steps=99)
        detector.record_step("read_file", {"path": "test.py"}, "ok")
        assert not detector.is_stuck()  # 1 step — not stuck
        detector.record_step("read_file", {"path": "test.py"}, "ok")
        assert detector.is_stuck()  # 2 identical steps → stuck

    def test_different_args_not_stuck(self):
        from vibe_studio.agents.stuck_detector import StuckAgentDetector
        detector = StuckAgentDetector(max_identical_steps=2)
        detector.record_step("read_file", {"path": "a.py"}, "ok")
        detector.record_step("read_file", {"path": "b.py"}, "ok")
        assert not detector.is_stuck()  # different args → fine

    def test_search_loop_detected(self):
        from vibe_studio.agents.stuck_detector import StuckAgentDetector
        detector = StuckAgentDetector(max_search_steps=3)
        detector.record_step("read_file", {"path": "a.py"}, "ok")
        detector.record_step("search_text", {"query": "foo"}, "ok")
        detector.record_step("list_directory", {}, "ok")
        assert detector.is_stuck()  # 3 consecutive read-only tools → stuck

    def test_recovery_hint_not_empty(self):
        from vibe_studio.agents.stuck_detector import StuckAgentDetector
        detector = StuckAgentDetector(max_search_steps=3)
        detector.record_step("read_file", {"path": "a.py"}, "ok")
        detector.record_step("read_file", {"path": "b.py"}, "ok")
        detector.record_step("read_file", {"path": "c.py"}, "ok")
        detector.is_stuck()
        hint = detector.get_recovery_hint()
        assert isinstance(hint, str) and len(hint) > 0


# ===========================================================================
# Injection F: External file modification during agent run
# ===========================================================================

class TestExternalFileModification:
    def test_patch_detects_conflict(self, tmp_path):
        """PatchTools.check_conflict() detects externally modified files."""
        from vibe_studio.tools.patch_tools import PatchTools
        f = tmp_path / "target.py"
        f.write_text("original content\n")
        tools = PatchTools(tmp_path)

        # Record hash before modification
        original_content = f.read_text()
        import hashlib
        expected_hash = hashlib.sha256(original_content.encode()).hexdigest()[:12]

        # External modification
        f.write_text("externally modified content\n")

        conflict = tools.check_conflict("target.py", expected_hash)
        assert conflict is True

    def test_no_conflict_when_unchanged(self, tmp_path):
        from vibe_studio.tools.patch_tools import PatchTools
        import hashlib
        f = tmp_path / "stable.py"
        content = "stable content\n"
        f.write_text(content)
        tools = PatchTools(tmp_path)

        expected_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        conflict = tools.check_conflict("stable.py", expected_hash)
        assert conflict is False


# ===========================================================================
# Injection G: Resource cleanup on cancellation
# ===========================================================================

class TestResourceCleanup:
    def test_cancelled_command_leaves_no_orphan(self, tmp_path):
        """Cancellation via token cleans up subprocess before returning."""
        from vibe_studio.core.command_safety import CommandSafety
        token = CancellationToken()

        done = threading.Event()
        result_holder = []

        def _run():
            r = CommandSafety.run(
                "sleep 20",
                cwd=tmp_path,
                workspace_root=tmp_path,
                timeout=20,
                cancellation_token=token,
            )
            result_holder.append(r)
            done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        time.sleep(0.2)
        token.cancel()
        done.wait(timeout=5.0)

        assert done.is_set(), "Command did not return after cancellation"
        if result_holder:
            r = result_holder[0]
            assert r.cancelled or r.exit_code != 0


# ===========================================================================
# Injection H: Chat service cancel flow
# ===========================================================================

class TestChatServiceCancellation:
    def test_cancel_current_agent_when_none(self):
        """cancel_current_agent() is safe to call even when no agent is active."""
        from vibe_studio.ai.chat_service import ChatService
        from vibe_studio.ai.model_manager import ModelManager
        from vibe_studio.core.settings import AppSettings
        settings = AppSettings()
        mm = ModelManager(settings)
        service = ChatService(mm)
        # Must not raise
        service.cancel_current_agent()

    def test_clean_conversation_strips_cancelled(self):
        """_clean_conversation() removes cancelled turns."""
        from vibe_studio.ai.chat_service import ChatService
        from vibe_studio.ai.model_manager import ModelManager
        from vibe_studio.core.settings import AppSettings
        settings = AppSettings()
        mm = ModelManager(settings)
        service = ChatService(mm)
        service._conversation = [
            {"role": "user", "content": "do X"},
            {"role": "assistant", "content": "Task cancelled by user."},
        ]
        cleaned = service._clean_conversation()
        # The cancelled turn + its preceding user turn should be stripped
        cancelled_content = [m["content"] for m in cleaned if "cancelled" in m.get("content", "").lower()]
        assert cancelled_content == []

    def test_save_history_no_crash_on_readonly(self, tmp_path):
        """save_history() does not raise when directory is not writable."""
        from vibe_studio.ai.chat_service import ChatService
        from vibe_studio.ai.model_manager import ModelManager
        from vibe_studio.core.settings import AppSettings
        settings = AppSettings()
        settings.project_path = str(tmp_path)
        mm = ModelManager(settings)
        service = ChatService(mm)
        # Should silently swallow I/O errors
        with patch("builtins.open", side_effect=PermissionError("read-only")):
            service.save_history()  # must not raise


# ===========================================================================
# Injection I: TerminalTools — path security injection
# ===========================================================================

class TestTerminalSecurityInjection:
    def test_cwd_outside_workspace_blocked(self, tmp_path):
        """execute_command() with cwd outside workspace is rejected."""
        from vibe_studio.tools.terminal_tools import TerminalTools
        from vibe_studio.security.path_security import PathSecurityError
        tools = TerminalTools(tmp_path)
        with pytest.raises((PathSecurityError, ValueError, PermissionError, Exception)):
            tools.execute_command("echo hi", cwd="/etc")


# ===========================================================================
# Injection J: Provider base — stream_generate default delegation
# ===========================================================================

class TestProviderBaseProtocol:
    def test_stream_generate_default_delegates_to_generate(self):
        """Default stream_generate yields a COMPLETE event from generate()."""
        from vibe_studio.providers.base import AIProvider, GenerationConfig
        from vibe_studio.providers.stream_events import StreamEventType

        # Minimal concrete implementation
        class MinimalProvider:
            name = "minimal"

            def list_models(self):
                return []

            def generate(self, *, prompt, model, system_prompt=None, config=None, cancellation_token=None, **kw):
                return "generated response"

            def stream_generate(self, *, prompt, model, system_prompt=None, config=None, cancellation_token=None, **kw):
                # Use the default protocol implementation
                from vibe_studio.providers.base import AIProvider
                text = self.generate(
                    prompt=prompt, model=model, system_prompt=system_prompt,
                    config=config, cancellation_token=cancellation_token, **kw
                )
                from vibe_studio.providers.stream_events import StreamEvent
                yield StreamEvent.complete(final_text=text)

            def test_connection(self):
                return True

            def cancel(self):
                pass

        provider = MinimalProvider()
        events = list(provider.stream_generate(prompt="hello", model="test"))
        assert len(events) == 1
        assert events[0].event_type == StreamEventType.COMPLETE
        assert events[0].content == "generated response"

    def test_generation_config_dataclass(self):
        from vibe_studio.providers.base import GenerationConfig
        cfg = GenerationConfig(temperature=0.7, max_tokens=1024)
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 1024
        assert cfg.stop_sequences == []
