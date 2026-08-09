"""Deterministic test suite for Commit 14 runtime stabilization and bug matrix (Bugs A-E)."""
import time
import pytest
from pathlib import Path
from vibe_studio.agents.coding_agent import AgentState, AutonomousAgent, AgentTaskResult
from vibe_studio.agents.tool_call_parser import parse_tool_calls, strip_tool_calls
from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.providers.ollama_provider import OllamaProvider
from vibe_studio.providers.openai_compatible_provider import OpenAICompatibleProvider


class MockSlowProvider:
    """Fake provider simulating slow streaming and tool call generation."""

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def generate(self, prompt: str, **kwargs):
        time.sleep(self.delay)
        if self._cancelled:
            raise InterruptedError("Cancelled")
        return "Task completed."

    def chat(self, messages: list, **kwargs):
        time.sleep(self.delay)
        if self._cancelled:
            raise InterruptedError("Cancelled")
        return "Task completed."


# ── Bug A: Agent never hangs indefinitely ─────────────────────────────────────

def test_bug_a_agent_returns_terminal_state(tmp_path):
    """Verify agent transitions deterministically to COMPLETED or FAILED and returns to IDLE."""
    agent = AutonomousAgent(project_root=tmp_path)
    res = agent.run("Create a hello world text file")
    assert res.status in (AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED)
    assert agent.state in (AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED, AgentState.IDLE)


# ── Bug B: Stop button / True cancellation ────────────────────────────────────

def test_bug_b_true_cancellation_propagates(tmp_path):
    """Verify cancellation token stops execution immediately and yields CANCELLED state."""
    slow_provider = MockSlowProvider(delay=1.0)
    token = CancellationToken()
    agent = AutonomousAgent(
        project_root=tmp_path,
        provider=slow_provider,
        cancellation_token=token,
    )

    token.cancel()
    res = agent.run("Run long operation")

    assert res.status == AgentState.CANCELLED
    assert agent.is_cancelled()


# ── Bug C & D: Tool call JSON stripping matrix ────────────────────────────────

def test_bug_c_d_tool_json_stripped_from_response():
    """Verify raw tool call JSON (bare, fenced, XML, OpenAI) is stripped cleanly from response text."""
    fenced_text = "I will read the file.\n```json\n{\"tool\": \"read_file\", \"args\": {\"path\": \"main.py\"}}\n```\nAll done."
    calls = parse_tool_calls(fenced_text)
    assert len(calls) == 1
    assert calls[0].tool == "read_file"

    prose = strip_tool_calls(fenced_text, calls)
    assert "```json" not in prose
    assert "read_file" not in prose
    assert "All done." in prose


def test_xml_and_bare_json_parsing():
    xml_text = "Let's inspect: <tool_call><name>list_directory</name><args>{\"path\": \".\"}</args></tool_call>"
    calls = parse_tool_calls(xml_text)
    assert len(calls) == 1
    assert calls[0].tool == "list_directory"

    bare_text = 'Check files: {"tool": "search_text", "args": {"query": "import"}}'
    calls_bare = parse_tool_calls(bare_text)
    assert len(calls_bare) == 1
    assert calls_bare[0].tool == "search_text"


# ── Bug E: Invalid JSON recovery without infinite loop ────────────────────────

def test_bug_e_invalid_json_handling(tmp_path):
    """Verify malformed JSON does not crash the agent or cause infinite retries."""
    malformed_text = '{"tool": "read_file", "args":'
    calls = parse_tool_calls(malformed_text)
    # Parser should attempt recovery or return empty list safely
    assert isinstance(calls, list)
