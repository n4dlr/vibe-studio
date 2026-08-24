"""Tests for tool call parsing and function-style tool call execution."""
from __future__ import annotations

from pathlib import Path
from vibe_studio.agents.tool_call_parser import parse_tool_calls, strip_tool_calls


def test_parse_standard_fenced_json():
    t = '```json\n{"tool": "write_file", "args": {"path": "main.py", "content": "print(1)"}}\n```'
    calls = parse_tool_calls(t)
    assert len(calls) == 1
    assert calls[0].tool == "write_file"
    assert calls[0].args == {"path": "main.py", "content": "print(1)"}


def test_parse_function_call_with_parentheses():
    t = 'execute_command({"command": "echo \'Hello, World!\'"});'
    calls = parse_tool_calls(t)
    assert len(calls) == 1
    assert calls[0].tool == "execute_command"
    assert calls[0].args == {"command": "echo 'Hello, World!'"}


def test_parse_function_call_with_nested_unescaped_quotes():
    t = 'execute_command({"command": "echo \'#!/usr/bin/env python\\nprint(\"Hello, World!\")\'"});'
    calls = parse_tool_calls(t)
    assert len(calls) == 1
    assert calls[0].tool == "execute_command"
    assert "print(\"Hello, World!\")" in calls[0].args["command"]


def test_parse_keyword_function_call():
    t = 'write_file(path="hello.py", content="print(\'hi\')")'
    calls = parse_tool_calls(t)
    assert len(calls) == 1
    assert calls[0].tool == "write_file"
    assert calls[0].args["path"] == "hello.py"
    assert calls[0].args["content"] == "print('hi')"


def test_strip_tool_calls_leaves_clean_text():
    t = 'I will run the command:\nexecute_command({"command": "echo hi"})\nDone.'
    calls = parse_tool_calls(t)
    stripped = strip_tool_calls(t, calls)
    assert "execute_command" not in stripped
    assert "I will run the command:" in stripped


def test_command_safety_executes_shebang_script_without_errno2():
    from vibe_studio.core.command_safety import CommandSafety
    cmd = "#!/usr/bin/env python\nprint('Hello from shebang')"
    res = CommandSafety.run(cmd)
    assert res.exit_code == 0
    assert "Hello from shebang" in res.stdout


def test_command_safety_executes_inline_python_code():
    from vibe_studio.core.command_safety import CommandSafety
    cmd = "def main():\n    print('Hello from inline')\nmain()"
    res = CommandSafety.run(cmd)
    assert res.exit_code == 0
    assert "Hello from inline" in res.stdout

