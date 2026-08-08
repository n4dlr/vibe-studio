"""
Robust tool-call parser.

Handles every format a model might emit:
  1. Fenced JSON block:   ```json\n{"tool": "...", "args": {...}}\n```
  2. Bare JSON object:    {"tool": "...", "args": {...}}
  3. XML-style:           <tool_call><name>...</name><args>...</args></tool_call>
  4. OpenAI function-call: {"name": "...", "arguments": {...}}
  5. Multiple tool calls in one response (sequential or interleaved with prose)
  6. Malformed/truncated JSON — attempts bracket-balancing recovery
  7. Schema validation against registered tool definitions
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedToolCall:
    tool: str
    args: dict[str, Any]
    raw: str          # the matched substring that was parsed
    source: str       # how it was parsed: "fenced_json" | "bare_json" | "xml" | "openai_fn" | "recovered"


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_FENCED_JSON = re.compile(
    r"```(?:json|tool_call|tool)?\s*(\{[\s\S]*?\})\s*```",
    re.IGNORECASE,
)
_XML_CALL = re.compile(
    r"<tool_call>\s*<name>([\w_]+)</name>\s*<arguments?>([\s\S]*?)</arguments?>\s*</tool_call>",
    re.IGNORECASE | re.DOTALL,
)
_XML_CALL_ALT = re.compile(
    r"<tool_call>\s*<name>([\w_]+)</name>\s*<args>([\s\S]*?)</args>\s*</tool_call>",
    re.IGNORECASE | re.DOTALL,
)
# Bare JSON with "tool" key — allows one level of nesting (args object)
_BARE_JSON_TOOL = re.compile(
    r'(\{(?:[^{}]|\{[^{}]*\})*"tool"\s*:\s*"[^"]+"(?:[^{}]|\{[^{}]*\})*\})',
    re.DOTALL,
)
# OpenAI function-calling response schema
_OPENAI_FN = re.compile(r'(\{\s*"name"\s*:\s*"[\w_]+"\s*,\s*"arguments"\s*:\s*\{[\s\S]*?\})', re.DOTALL)


def _try_parse_json(s: str) -> dict[str, Any] | None:
    """Attempt to parse JSON with progressive error recovery."""
    s = s.strip()
    # Direct parse
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Try to recover truncated JSON by counting brackets
    try:
        s2 = _balance_braces(s)
        return json.loads(s2)
    except Exception:
        pass
    # Last resort: strip trailing garbage after the last closing brace
    m = re.search(r'(\{[\s\S]*\})', s)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None


def _balance_braces(s: str) -> str:
    """Add missing closing braces/brackets to truncated JSON."""
    opens = {"{": "}", "[": "]"}
    closes = {v: k for k, v in opens.items()}
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in opens:
            stack.append(opens[ch])
        elif ch in closes:
            if stack and stack[-1] == ch:
                stack.pop()
    return s + "".join(reversed(stack))


def _extract_tool_and_args(
    data: dict[str, Any]
) -> tuple[str | None, dict[str, Any]]:
    """Normalise various JSON schemas to (tool_name, args)."""
    # Schema 1: {"tool": "name", "args": {...}}
    if "tool" in data and isinstance(data["tool"], str):
        args = data.get("args") or data.get("arguments") or data.get("parameters") or {}
        if isinstance(args, str):
            args = _try_parse_json(args) or {}
        return data["tool"], args

    # Schema 2: OpenAI function-calling {"name": "...", "arguments": {...}}
    if "name" in data and "arguments" in data:
        args = data["arguments"]
        if isinstance(args, str):
            args = _try_parse_json(args) or {}
        return data["name"], args if isinstance(args, dict) else {}

    # Schema 3: {"function": {"name": "...", "arguments": {...}}}
    fn = data.get("function")
    if isinstance(fn, dict) and "name" in fn:
        args = fn.get("arguments", {})
        if isinstance(args, str):
            args = _try_parse_json(args) or {}
        return fn["name"], args if isinstance(args, dict) else {}

    return None, {}


def parse_tool_calls(text: str) -> list[ParsedToolCall]:
    """
    Parse all tool calls from a model response.

    Returns an ordered list of ParsedToolCall.
    De-duplicates overlapping matches (longest match wins).
    """
    calls: list[ParsedToolCall] = []
    consumed_spans: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        for s, e in consumed_spans:
            if not (end <= s or start >= e):
                return True
        return False

    def _add(call: ParsedToolCall, start: int, end: int) -> None:
        if not _overlaps(start, end):
            calls.append(call)
            consumed_spans.append((start, end))

    # 1. Fenced JSON blocks
    for m in _FENCED_JSON.finditer(text):
        data = _try_parse_json(m.group(1))
        if data:
            name, args = _extract_tool_and_args(data)
            if name:
                _add(ParsedToolCall(tool=name, args=args, raw=m.group(0), source="fenced_json"),
                     m.start(), m.end())

    # 2. XML-style (both <arguments> and <args> variants)
    for pat in (_XML_CALL, _XML_CALL_ALT):
        for m in pat.finditer(text):
            if _overlaps(m.start(), m.end()):
                continue
            tool_name = m.group(1).strip()
            args_str = m.group(2).strip()
            args = _try_parse_json(args_str) or {}
            if not isinstance(args, dict):
                args = {}
            _add(ParsedToolCall(tool=tool_name, args=args, raw=m.group(0), source="xml"),
                 m.start(), m.end())

    # 3. Bare JSON with "tool" key
    for m in _BARE_JSON_TOOL.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        data = _try_parse_json(m.group(1))
        if data:
            name, args = _extract_tool_and_args(data)
            if name:
                _add(ParsedToolCall(tool=name, args=args, raw=m.group(0), source="bare_json"),
                     m.start(), m.end())

    # 4. OpenAI function-call schema
    for m in _OPENAI_FN.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        data = _try_parse_json(m.group(1))
        if data:
            name, args = _extract_tool_and_args(data)
            if name:
                _add(ParsedToolCall(tool=name, args=args, raw=m.group(0), source="openai_fn"),
                     m.start(), m.end())

    # Sort by position in text (preserves model's intended order)
    calls.sort(key=lambda c: text.find(c.raw))
    return calls


def strip_tool_calls(text: str, calls: list[ParsedToolCall]) -> str:
    """Remove all tool call blocks from text, leaving only prose."""
    result = text
    for call in calls:
        result = result.replace(call.raw, "")
    return result.strip()


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_tool_call(
    call: ParsedToolCall,
    tool_definitions: list[dict[str, Any]],
) -> tuple[bool, str]:
    """
    Validate a parsed tool call against the registered tool definitions.

    Returns (ok, error_message).
    """
    definition = next((t for t in tool_definitions if t["name"] == call.tool), None)
    if definition is None:
        known = ", ".join(t["name"] for t in tool_definitions)
        return False, f"Unknown tool '{call.tool}'. Known tools: {known[:200]}"

    params_schema = definition.get("parameters", {})
    required = params_schema.get("required", [])
    properties = params_schema.get("properties", {})

    for req in required:
        if req not in call.args:
            return False, (
                f"Tool '{call.tool}' missing required parameter '{req}'. "
                f"Provided: {list(call.args.keys())}"
            )

    for arg_name, arg_value in call.args.items():
        if arg_name in properties:
            expected_type = properties[arg_name].get("type", "any")
            if not _check_type(arg_value, expected_type):
                return False, (
                    f"Tool '{call.tool}' parameter '{arg_name}' expected {expected_type}, "
                    f"got {type(arg_value).__name__}"
                )

    return True, ""


def _check_type(value: Any, expected: str) -> bool:
    if expected == "any":
        return True
    type_map = {
        "string": str,
        "integer": (int,),
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    expected_types = type_map.get(expected)
    if expected_types is None:
        return True
    if isinstance(expected_types, tuple):
        return isinstance(value, expected_types) and not isinstance(value, bool)
    return isinstance(value, expected_types)
