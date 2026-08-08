"""
Smart output truncation and error classification.

Rules:
  - Never dump more than MAX_CHARS chars into LLM context per tool result
  - Preserve the first N lines (imports/headers) and the last N lines (errors/summary)
  - Always preserve lines that contain error indicators
  - Classify error type so the agent knows what repair strategy to use
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# Maximum characters per tool output fed to the model
MAX_CHARS = 4000
# Lines to always keep from the top (imports, config headers)
HEAD_LINES = 30
# Lines to always keep from the bottom (error summary, failed tests)
TAIL_LINES = 60


class ErrorCategory(str, Enum):
    SYNTAX     = "SYNTAX"
    TYPE       = "TYPE"
    TEST       = "TEST"
    BUILD      = "BUILD"
    DEPENDENCY = "DEPENDENCY"
    RUNTIME    = "RUNTIME"
    CONFIG     = "CONFIG"
    LINT       = "LINT"
    PERMISSION = "PERMISSION"
    NETWORK    = "NETWORK"
    UNKNOWN    = "UNKNOWN"


@dataclass
class ErrorInfo:
    category: ErrorCategory
    message: str
    file: str | None = None
    line: int | None = None
    fingerprint: str = ""   # stable hash for dedup

    def __post_init__(self) -> None:
        if not self.fingerprint:
            import hashlib
            self.fingerprint = hashlib.md5(
                f"{self.category}:{self.file}:{self.line}:{self.message[:80]}".encode()
            ).hexdigest()[:12]


# Patterns for error detection — ordered by specificity
_ERROR_PATTERNS: list[tuple[re.Pattern, ErrorCategory]] = [
    (re.compile(r"\bSyntaxError\b|IndentationError|unexpected indent|invalid syntax", re.I), ErrorCategory.SYNTAX),
    (re.compile(r"\bTypeError\b|type error|cannot be assigned|incompatible type|mypy", re.I), ErrorCategory.TYPE),
    (re.compile(r"FAILED tests?/|FAILED src/|AssertionError|pytest|test failed|no tests ran", re.I), ErrorCategory.TEST),
    (re.compile(r"\bModuleNotFoundError\b|cannot find module|importerror|no module named", re.I), ErrorCategory.DEPENDENCY),
    (re.compile(r"npm ERR!|cargo error|make.*error|build failed|compilation error|error\[E\d", re.I), ErrorCategory.BUILD),
    (re.compile(r"\bruff\b|eslint|pylint|flake8|warning: .*unused|missing comma", re.I), ErrorCategory.LINT),
    (re.compile(r"permissionerror|permission denied|access denied", re.I), ErrorCategory.PERMISSION),
    (re.compile(r"connection refused|timeout|network error|ECONNREFUSED|unreachable", re.I), ErrorCategory.NETWORK),
    (re.compile(r"error in.*\.toml|invalid config|missing.*config|keyerror.*config", re.I), ErrorCategory.CONFIG),
    (re.compile(r"\bTraceback\b|RuntimeError|AttributeError|NameError|ValueError|KeyError|IndexError", re.I), ErrorCategory.RUNTIME),
]

_ERROR_LINE = re.compile(
    r"(?:error|warning|failed|exception|traceback|FAILED|ERROR)",
    re.I,
)

# Regex for extracting file/line from error output
_FILE_LINE = re.compile(
    r'(?:File "([^"]+)", line (\d+)|([A-Za-z0-9_./-]+\.(?:py|js|ts|tsx|rs|go|java|cpp|c|cs)):(\d+))',
)


def truncate_output(text: str, max_chars: int = MAX_CHARS) -> str:
    """
    Intelligently truncate tool output:
      - Keep first HEAD_LINES always
      - Keep last TAIL_LINES always
      - Keep any lines containing error indicators
      - Join with a truncation marker if needed
    """
    if len(text) <= max_chars:
        return text

    lines = text.splitlines(keepends=True)
    total = len(lines)

    if total <= HEAD_LINES + TAIL_LINES:
        # Just truncate characters
        half = max_chars // 2
        return text[:half] + f"\n…[{len(text) - max_chars} chars truncated]…\n" + text[-half:]

    head = lines[:HEAD_LINES]
    tail = lines[max(total - TAIL_LINES, HEAD_LINES):]

    # Extract error lines from the middle
    middle = lines[HEAD_LINES: max(total - TAIL_LINES, HEAD_LINES)]
    error_lines = [l for l in middle if _ERROR_LINE.search(l)]

    preserved = (
        "".join(head)
        + (("…[error lines from middle]…\n" + "".join(error_lines[:20])) if error_lines else "")
        + f"\n…[{total - HEAD_LINES - TAIL_LINES} lines truncated]…\n"
        + "".join(tail)
    )

    if len(preserved) > max_chars:
        half = max_chars // 2
        return preserved[:half] + f"\n…[truncated]…\n" + preserved[-half:]

    return preserved


def classify_error(output: str) -> ErrorCategory:
    """Classify the primary error type in tool output."""
    if not output:
        return ErrorCategory.UNKNOWN
    for pattern, category in _ERROR_PATTERNS:
        if pattern.search(output):
            return category
    return ErrorCategory.UNKNOWN


def extract_errors(output: str) -> list[ErrorInfo]:
    """Extract structured error information from tool output."""
    errors: list[ErrorInfo] = []
    category = classify_error(output)

    for m in _FILE_LINE.finditer(output):
        file_path = m.group(1) or m.group(3)
        line_num = int(m.group(2) or m.group(4) or 0)
        # Find nearest error message on same or adjacent line
        start = max(0, m.start() - 200)
        snippet = output[start: m.end() + 200]
        errors.append(ErrorInfo(
            category=category,
            message=snippet.strip()[:200],
            file=file_path,
            line=line_num,
        ))

    if not errors:
        # Create a single error from the whole output
        errors.append(ErrorInfo(
            category=category,
            message=output[-400:].strip(),
        ))

    return errors


@dataclass
class ErrorTracker:
    """
    Tracks errors across repair cycles to prevent infinite loops.

    If the same error fingerprint appears more than `max_repeats` times,
    the agent is blocked from repeating the same repair action.
    """
    max_repeats: int = 2
    _seen: dict[str, int] = field(default_factory=dict)
    _actions_tried: dict[str, list[str]] = field(default_factory=dict)

    def record(self, error: ErrorInfo, action: str = "") -> None:
        self._seen[error.fingerprint] = self._seen.get(error.fingerprint, 0) + 1
        if action:
            self._actions_tried.setdefault(error.fingerprint, []).append(action)

    def is_stuck(self, error: ErrorInfo) -> bool:
        return self._seen.get(error.fingerprint, 0) >= self.max_repeats

    def previous_actions(self, error: ErrorInfo) -> list[str]:
        return self._actions_tried.get(error.fingerprint, [])

    def reset(self) -> None:
        self._seen.clear()
        self._actions_tried.clear()

    def summary(self) -> str:
        repeated = {fp: cnt for fp, cnt in self._seen.items() if cnt >= self.max_repeats}
        if not repeated:
            return ""
        return f"Repeated errors ({len(repeated)}): " + ", ".join(repeated.keys())
