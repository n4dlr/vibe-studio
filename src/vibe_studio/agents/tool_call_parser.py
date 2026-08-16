"""
Robust tool-call parser and schema recovery engine.

Handles every format a model might emit:
  1. Fenced JSON blocks:  ```json\n{"tool": "...", "args": {...}}\n```
  2. Bare JSON objects:   {"tool": "...", "args": {...}}
  3. XML-style:           <tool_call><name>...</name><args>...</args></tool_call>
  4. OpenAI function-call: {"name": "...", "arguments": {...}}
  5. Python dict syntax:  {'tool': '...', 'args': {...}}
  6. Multiple tool calls in one response (sequential or interleaved with prose)
  7. Malformed/truncated JSON — progressive recovery (bracket-balancing, trailing comma fixes, unquoted keys)
  8. Schema validation against registered tool definitions with structured feedback
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
    source: str       # how it was parsed: "fenced_json" | "bare_json" | "xml" | "openai_fn" | "python_dict" | "recovered"


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
# Bare JSON with "tool" key — allows arbitrary nesting
_BARE_JSON_TOOL = re.compile(
    r'(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*"tool"\s*:\s*"[^"]+"(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})',
    re.DOTALL,
)
# OpenAI function-calling response schema
_OPENAI_FN = re.compile(
    r'(\{\s*"name"\s*:\s*"[\w_]+"\s*,\s*"arguments"\s*:\s*(?:\{[\s\S]*?\}|"[^"]*")\})',
    re.DOTALL,
)
# Single quoted Python-style dict pattern: {'tool': '...', 'args': ...}
_PYTHON_DICT_TOOL = re.compile(
    r"(\{'tool'\s*:\s*'[^']+'[\s\S]*?\})",
    re.DOTALL,
)
# Inline tool call prefix: tool_name{"args": ...} or tool_name({"path": ...})
_INLINE_TOOL_PREFIX = re.compile(
    r'(\b([a-zA-Z0-9_]+)\s*(\{\s*"(?:args|arguments|parameters|path|filename|file|content)"[\s\S]*?\}))',
    re.DOTALL,
)


def _try_parse_json(s: str) -> dict[str, Any] | None:
    """Attempt to parse JSON with progressive error recovery."""
    if not s:
        return None
    s = s.strip()

    # Direct standard parse
    try:
        res = json.loads(s)
        if isinstance(res, dict):
            return res
    except json.JSONDecodeError:
        pass

    # Clean markdown fences if embedded
    cleaned = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        res = json.loads(cleaned)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    # Try removing trailing commas before closing braces/brackets
    no_trailing_commas = re.sub(r",\s*([\]}])", r"\1", cleaned)
    try:
        res = json.loads(no_trailing_commas)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    # Try Python literal eval if using single quotes
    if "'" in cleaned and '"' not in cleaned:
        try:
            import ast
            res = ast.literal_eval(cleaned)
            if isinstance(res, dict):
                return res
        except Exception:
            pass

    # Try bracket balancing for truncated responses
    try:
        balanced = _balance_braces(no_trailing_commas)
        res = json.loads(balanced)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    # Try extracting outermost JSON object
    m = re.search(r"(\{[\s\S]*\})", s)
    if m:
        sub = m.group(1)
        sub_no_commas = re.sub(r",\s*([\]}])", r"\1", sub)
        try:
            res = json.loads(sub_no_commas)
            if isinstance(res, dict):
                return res
        except Exception:
            try:
                res = json.loads(_balance_braces(sub_no_commas))
                if isinstance(res, dict):
                    return res
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
    if in_string:
        s += '"'
    return s + "".join(reversed(stack))


def _extract_tool_and_args(
    data: dict[str, Any]
) -> tuple[str | None, dict[str, Any]]:
    """Normalise various JSON schemas to (tool_name, args)."""
    tool_name: str | None = None
    args: dict[str, Any] = {}

    # Schema 1: {"tool": "name", "args": {...}}
    if "tool" in data and isinstance(data["tool"], str):
        tool_name = data["tool"]
        raw_args = data.get("args") or data.get("arguments") or data.get("parameters") or {}
        if isinstance(raw_args, str):
            raw_args = _try_parse_json(raw_args) or {}
        args = raw_args if isinstance(raw_args, dict) else {}

    # Schema 2: {"tool_call": {"name": "...", "parameters"|"args"|"arguments": {...}}}
    elif "tool_call" in data or "tool_calls" in data:
        tc = data.get("tool_call") or data.get("tool_calls")
        if isinstance(tc, list) and tc:
            tc = tc[0]
        if isinstance(tc, dict):
            name = tc.get("name") or tc.get("tool") or tc.get("function")
            raw_args = tc.get("parameters") or tc.get("args") or tc.get("arguments") or tc.get("parameters_input") or {}
            if isinstance(name, str):
                if isinstance(raw_args, str):
                    raw_args = _try_parse_json(raw_args) or {}
                tool_name = name
                args = raw_args if isinstance(raw_args, dict) else {}

    # Schema 3: OpenAI function-calling {"name": "...", "arguments"|"parameters": {...}}
    elif "name" in data and ("arguments" in data or "parameters" in data):
        tool_name = data["name"]
        raw_args = data.get("arguments") or data.get("parameters") or {}
        if isinstance(raw_args, str):
            raw_args = _try_parse_json(raw_args) or {}
        args = raw_args if isinstance(raw_args, dict) else {}

    # Schema 4: {"function": {"name": "...", "arguments": {...}}}
    elif "function" in data and isinstance(data["function"], dict) and "name" in data["function"]:
        fn = data["function"]
        tool_name = fn["name"]
        raw_args = fn.get("arguments") or fn.get("parameters") or {}
        if isinstance(raw_args, str):
            raw_args = _try_parse_json(raw_args) or {}
        args = raw_args if isinstance(raw_args, dict) else {}

    # Schema 5: LangChain format {"action": "...", "action_input": {...}}
    elif "action" in data and isinstance(data["action"], str):
        tool_name = data["action"]
        raw_args = data.get("action_input") or data.get("args") or {}
        if isinstance(raw_args, str):
            raw_args = _try_parse_json(raw_args) or {}
        args = raw_args if isinstance(raw_args, dict) else {}

    # Flatten nested "args" if present (e.g. {"args": {"filename": "hello.html"}})
    if isinstance(args, dict) and "args" in args and isinstance(args["args"], dict):
        args = args["args"]

    # Parameter normalization for common tool arguments
    if tool_name:
        _file_tools = {
            "delete_file", "read_file", "write_file", "create_file",
            "patch_file", "file_exists", "get_file_metadata",
        }
        if tool_name in _file_tools and "path" not in args:
            for alt in ("filename", "file", "target", "filepath", "path_name"):
                if alt in args:
                    args["path"] = args.pop(alt)
                    break

    return tool_name, args


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

    # 3. Bare JSON with "tool" or "tool_call" key
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

    # 5. Python-style single quoted dict
    for m in _PYTHON_DICT_TOOL.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        data = _try_parse_json(m.group(1))
        if data:
            name, args = _extract_tool_and_args(data)
            if name:
                _add(ParsedToolCall(tool=name, args=args, raw=m.group(0), source="python_dict"),
                     m.start(), m.end())

    # 6. Inline tool call prefix: tool_name{"args": ...} or tool_name({"filename": ...})
    for m in _INLINE_TOOL_PREFIX.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        tool_name = m.group(2).strip()
        json_obj = _try_parse_json(m.group(3))
        if json_obj and isinstance(json_obj, dict):
            name, args = _extract_tool_and_args({"tool": tool_name, "args": json_obj})
            if name:
                _add(ParsedToolCall(tool=name, args=args, raw=m.group(0), source="inline_prefix"),
                     m.start(), m.end())

    # 7. Top-level bare JSON response fallback
    if not calls:
        top_json = _try_parse_json(text)
        if isinstance(top_json, dict):
            name, args = _extract_tool_and_args(top_json)
            if not name:
                # Check for single-key dict like {"read_file": {"path": "foo.py"}}
                for k, v in top_json.items():
                    if isinstance(k, str) and isinstance(v, dict):
                        name, args = k, v
                        break
            if name:
                _add(ParsedToolCall(tool=name, args=args, raw=text.strip(), source="bare_json_toplevel"), 0, len(text))

    # Sort by position in text (preserves model's intended order)
    calls.sort(key=lambda c: text.find(c.raw) if text.find(c.raw) >= 0 else 0)
    return calls


def strip_tool_calls(text: str, calls: list[ParsedToolCall]) -> str:
    """Remove all tool call blocks and raw tool-call JSON from text, leaving only prose."""
    result = text
    for call in calls:
        result = result.replace(call.raw, "")

    # Extra safety sweep: strip any remaining fenced ```json ... ``` blocks containing tool calls
    result = re.sub(
        r"```(?:json|tool_call|tool)?\s*\{\s*\"(?:tool|tool_call|name|action)\"[\s\S]*?\}\s*```",
        "",
        result,
        flags=re.IGNORECASE,
    )
    # Extra safety sweep: strip bare tool_call objects
    result = re.sub(
        r"\{\s*\"(?:tool|tool_call)\"\s*:\s*\{[\s\S]*?\}\s*\}",
        "",
        result,
        flags=re.IGNORECASE,
    )
    return result.strip()


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_tool_call(
    call: ParsedToolCall,
    tool_definitions: list[dict[str, Any]],
) -> tuple[bool, str]:
    """
    Validate a parsed tool call against registered tool definitions.

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
                f"Provided parameters: {list(call.args.keys())}. "
                f"Expected parameters schema: {list(properties.keys())}."
            )

    for arg_name, arg_value in call.args.items():
        if arg_name in properties:
            expected_type = properties[arg_name].get("type", "any")
            if not _check_type(arg_value, expected_type):
                # Try coercion if possible
                coerced_ok, coerced_val = _try_coerce(arg_value, expected_type)
                if coerced_ok:
                    call.args[arg_name] = coerced_val
                else:
                    return False, (
                        f"Tool '{call.tool}' parameter '{arg_name}' expected {expected_type}, "
                        f"got {type(arg_value).__name__} ({repr(arg_value)[:60]})"
                    )

    return True, ""


def _try_coerce(val: Any, expected: str) -> tuple[bool, Any]:
    if expected == "integer" and isinstance(val, str):
        try:
            return True, int(val)
        except ValueError:
            pass
    elif expected == "number" and isinstance(val, str):
        try:
            return True, float(val)
        except ValueError:
            pass
    elif expected == "boolean" and isinstance(val, str):
        if val.lower() in ("true", "1", "yes"):
            return True, True
        if val.lower() in ("false", "0", "no"):
            return True, False
    elif expected == "array" and isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return True, parsed
        except Exception:
            return True, [val]
    return False, val


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
