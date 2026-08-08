"""DebugAssistant — multi-language traceback analyzer.

Supports:
  - Python (standard tracebacks + pytest output)
  - JavaScript/Node.js
  - Rust (panic + test failures)
  - Go (goroutine panics)
  - Java (exception chains)

Produces ranked suggestions based on error type and workspace proximity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ErrorRuntime(str, Enum):
    PYTHON     = "python"
    PYTEST     = "pytest"
    JAVASCRIPT = "javascript"
    RUST       = "rust"
    GO         = "go"
    JAVA       = "java"
    UNKNOWN    = "unknown"


@dataclass
class DebugAnalysis:
    error_type: str
    error_message: str
    file_path: str
    line_number: int
    suggestions: list[str]
    runtime: ErrorRuntime = ErrorRuntime.UNKNOWN
    confidence: float = 0.0      # 0.0–1.0
    additional_frames: list[dict[str, str]] = field(default_factory=list)

    def format_report(self) -> str:
        lines = [
            f"=== Debug Analysis ({self.runtime.value}) ===",
            f"Error: {self.error_type}: {self.error_message}",
        ]
        if self.file_path:
            lines.append(f"Location: {self.file_path}:{self.line_number}")
        if self.additional_frames:
            lines.append("Call stack (innermost last):")
            for frame in self.additional_frames[-5:]:
                lines.append(f"  {frame.get('file', '')}:{frame.get('line', '')} in {frame.get('func', '')}")
        lines.append(f"Confidence: {self.confidence:.0%}")
        lines.append("Suggestions:")
        for i, s in enumerate(self.suggestions, 1):
            lines.append(f"  {i}. {s}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Language-specific traceback patterns
# ---------------------------------------------------------------------------

# Python: File "path", line N, in function
_PYTHON_FRAME = re.compile(
    r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\w+)'
)
# Python: ExceptionType: message (on its own line after frames)
_PYTHON_EXCEPTION = re.compile(
    r'^(?P<err>[A-Za-z][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt|Exit|Fault|Stop|Break))\s*:\s*(?P<msg>.+)',
    re.MULTILINE,
)

# Pytest: FAILED test_file.py::TestClass::test_name - ExcType: msg
_PYTEST_FAILED = re.compile(
    r'FAILED (?P<file>[^\s:]+)::(?P<test>[^\s]+)\s*-\s*(?P<err>[A-Za-z0-9_.]+):\s*(?P<msg>.+)'
)
# Pytest: E  AssertionError: assert ...
_PYTEST_ERROR_LINE = re.compile(r'^\s*E\s+(?P<err>[A-Za-z0-9_.]+Error|AssertionError):\s*(?P<msg>.+)', re.MULTILINE)

# JavaScript/Node: at functionName (file.js:line:col)
_JS_FRAME = re.compile(r'at (?P<func>[^\s(]+)\s+\((?P<file>[^)]+):(?P<line>\d+):\d+\)')
_JS_EXCEPTION = re.compile(r'^(?P<err>[A-Za-z]+Error|TypeError|SyntaxError|RangeError):\s*(?P<msg>.+)', re.MULTILINE)

# Rust: panicked at 'message', src/file.rs:line:col
_RUST_PANIC = re.compile(r"panicked at '(?P<msg>[^']+)',\s*(?P<file>[^:]+):(?P<line>\d+)")
# Rust test failure: test tests::something ... FAILED
_RUST_TEST = re.compile(r'test (?P<test>[^\s]+)\s+\.\.\.\s+FAILED')

# Go: goroutine N [running]: / package.Function(...)
_GO_FRAME = re.compile(r'\t(?P<file>[^:]+):(?P<line>\d+)\s+\+')
_GO_PANIC = re.compile(r'panic:\s*(?P<msg>.+)')

# Java: java.lang.ExceptionType: message
_JAVA_EXCEPTION = re.compile(r'(?P<err>(?:[a-z]+\.)+[A-Z][A-Za-z]+(?:Exception|Error)):\s*(?P<msg>.+)')
_JAVA_FRAME = re.compile(r'\s+at (?P<class>[^(]+)\((?P<file>[^:)]+):(?P<line>\d+)\)')


# ---------------------------------------------------------------------------
# Suggestion templates keyed by error type patterns
# ---------------------------------------------------------------------------

_SUGGESTION_MAP: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r'(?i)AttributeError'), [
        "Check if the object is None before accessing the attribute.",
        "Verify the attribute name — check spelling and case.",
        "Ensure the object is the expected type at this point in the code.",
    ]),
    (re.compile(r'(?i)KeyError'), [
        "Use dict.get(key, default) instead of dict[key] for safe access.",
        "Check if the key exists with `if key in dict:` before accessing.",
        "Print/log the dictionary contents to verify the expected keys are present.",
    ]),
    (re.compile(r'(?i)TypeError'), [
        "Check the types of arguments being passed to the function.",
        "Ensure you're not calling a non-callable or passing the wrong number of arguments.",
        "Add explicit type conversions (int(), str(), list()) where needed.",
    ]),
    (re.compile(r'(?i)ImportError|ModuleNotFoundError'), [
        "Run `pip install <package>` (or equivalent) to install the missing module.",
        "Check the import path — the module may have been renamed or moved.",
        "Ensure you're running in the correct virtual environment.",
    ]),
    (re.compile(r'(?i)FileNotFoundError'), [
        "Verify the file path is correct and the file exists at runtime.",
        "Use pathlib.Path.exists() to check before opening.",
        "Check if the working directory matches expectations.",
    ]),
    (re.compile(r'(?i)IndexError'), [
        "Check the list/array bounds before accessing by index.",
        "Use `if idx < len(lst):` guard or try/except IndexError.",
        "Print the length of the collection to verify your assumptions.",
    ]),
    (re.compile(r'(?i)ValueError'), [
        "Validate input data before passing it to the function.",
        "Check for empty strings, None, or out-of-range values.",
        "Add an explicit guard or conversion (e.g. int(x) if x.isdigit()).",
    ]),
    (re.compile(r'(?i)AssertionError'), [
        "Read the assertion expression — the left-hand value is likely not what you expect.",
        "Add debug output (print/log) before the assertion to inspect values.",
        "Check if any fixture or setup function is producing unexpected state.",
    ]),
    (re.compile(r'(?i)RuntimeError|panic'), [
        "Read the full stack trace to find the root cause.",
        "Check for infinite recursion or re-entrant locks.",
        "Add guard conditions or error handling around the failing code path.",
    ]),
    (re.compile(r'(?i)NullPointerException|NilPointerDereference'), [
        "Add a nil/null check before dereferencing the pointer.",
        "Trace back to where the variable could have been set to nil/null.",
        "Consider using Optional or null-safe operators if the language supports them.",
    ]),
]

_DEFAULT_SUGGESTIONS = [
    "Read the full stack trace and identify the innermost frame in your code (not library code).",
    "Add logging/print around the failure site to inspect variable state.",
    "Reproduce the failure with a minimal test case to isolate the root cause.",
]


def _rank_suggestions(error_type: str, error_msg: str) -> list[str]:
    combined = f"{error_type}: {error_msg}"
    for pattern, suggestions in _SUGGESTION_MAP:
        if pattern.search(combined):
            return suggestions
    return _DEFAULT_SUGGESTIONS


def _extract_python_frames(text: str) -> list[dict[str, str]]:
    return [
        {"file": m.group("file"), "line": m.group("line"), "func": m.group("func")}
        for m in _PYTHON_FRAME.finditer(text)
    ]


class DebugAssistant:
    """Analyzes runtime exceptions and stack traces across multiple languages."""

    def analyze_traceback(self, traceback_text: str) -> DebugAnalysis:
        """Parse a traceback/error output and return a structured DebugAnalysis."""
        text = traceback_text.strip()

        # Try language-specific parsers in priority order
        for parser in [
            self._parse_pytest,
            self._parse_javascript,
            self._parse_rust,
            self._parse_go,
            self._parse_java,
            self._parse_python,
        ]:
            result = parser(text)
            if result is not None:
                return result

        # Unknown — best-effort
        return DebugAnalysis(
            error_type="UnknownError",
            error_message=text[:200],
            file_path="",
            line_number=0,
            suggestions=_DEFAULT_SUGGESTIONS,
            runtime=ErrorRuntime.UNKNOWN,
            confidence=0.1,
        )

    def analyze_test_output(self, output: str) -> list[DebugAnalysis]:
        """Analyze combined test runner output containing multiple failures.

        Splits on common failure delimiters (pytest section headers, FAILED lines)
        and returns one DebugAnalysis per failure block, ordered by confidence descending.
        Returns an empty list when no failures are detected.
        """
        if not output.strip():
            return []

        analyses: list[DebugAnalysis] = []

        # Heuristic: split on separator lines (===, ---) that delimit pytest failure sections
        import re as _re
        sections = _re.split(r"(?:={5,}|_{5,}|-{5,})\s+\S+", output)
        if len(sections) <= 1:
            # Single block — just analyze directly
            result = self.analyze_traceback(output)
            if result.error_type != "UnknownError" or result.confidence > 0.1:
                analyses.append(result)
            return analyses

        for section in sections[1:]:  # skip preamble
            section = section.strip()
            if not section:
                continue
            result = self.analyze_traceback(section)
            if result.error_type != "UnknownError" or result.confidence > 0.1:
                analyses.append(result)

        # Deduplicate by (error_type, file_path, line_number)
        seen: set[tuple[str, str, int]] = set()
        unique: list[DebugAnalysis] = []
        for a in analyses:
            key = (a.error_type, a.file_path, a.line_number)
            if key not in seen:
                seen.add(key)
                unique.append(a)

        return sorted(unique, key=lambda a: a.confidence, reverse=True)

    def find_fix_location(
        self,
        analysis: DebugAnalysis,
        workspace_root: str | None = None,
    ) -> dict[str, int | str]:
        """Return the most actionable fix location from a DebugAnalysis.

        Returns a dict with keys: ``file``, ``line``, ``error_type``, ``message``.
        When *workspace_root* is provided and the file path is absolute, the returned
        path is made relative to the workspace root.
        """
        file_path = analysis.file_path
        if workspace_root and file_path:
            from pathlib import Path as _Path
            try:
                file_path = str(_Path(file_path).relative_to(_Path(workspace_root)))
            except ValueError:
                pass  # keep original if not under workspace

        return {
            "file": file_path,
            "line": analysis.line_number,
            "error_type": analysis.error_type,
            "message": analysis.error_message,
            "runtime": analysis.runtime.value,
            "confidence": analysis.confidence,
        }

    # ------------------------------------------------------------------
    # Language parsers
    # ------------------------------------------------------------------

    def _parse_python(self, text: str) -> DebugAnalysis | None:
        frames = _extract_python_frames(text)
        exc_match = _PYTHON_EXCEPTION.search(text)
        if not frames and not exc_match:
            return None

        err_type = exc_match.group("err") if exc_match else "RuntimeError"
        err_msg  = exc_match.group("msg") if exc_match else text[:100]

        # Innermost frame = last frame in traceback
        if frames:
            last = frames[-1]
            file_path = last["file"]
            line_num  = int(last["line"])
        else:
            file_path = ""
            line_num  = 0

        confidence = 0.9 if (frames and exc_match) else 0.5

        return DebugAnalysis(
            error_type=err_type,
            error_message=err_msg,
            file_path=file_path,
            line_number=line_num,
            suggestions=_rank_suggestions(err_type, err_msg),
            runtime=ErrorRuntime.PYTHON,
            confidence=confidence,
            additional_frames=frames[:-1],
        )

    def _parse_pytest(self, text: str) -> DebugAnalysis | None:
        # Check for pytest markers first
        if "FAILED" not in text and "pytest" not in text.lower() and "E  " not in text:
            return None

        failed_match = _PYTEST_FAILED.search(text)
        err_line_match = _PYTEST_ERROR_LINE.search(text)

        if not failed_match and not err_line_match:
            return None

        if failed_match:
            err_type = failed_match.group("err")
            err_msg  = failed_match.group("msg")
            file_path = failed_match.group("file")
        else:
            err_type = err_line_match.group("err")  # type: ignore[union-attr]
            err_msg  = err_line_match.group("msg")   # type: ignore[union-attr]
            file_path = ""

        # Try to get line from Python frames embedded in pytest output
        frames = _extract_python_frames(text)
        line_num = int(frames[-1]["line"]) if frames else 0
        if not file_path and frames:
            file_path = frames[-1]["file"]

        return DebugAnalysis(
            error_type=err_type,
            error_message=err_msg,
            file_path=file_path,
            line_number=line_num,
            suggestions=_rank_suggestions(err_type, err_msg),
            runtime=ErrorRuntime.PYTEST,
            confidence=0.85,
            additional_frames=frames,
        )

    def _parse_javascript(self, text: str) -> DebugAnalysis | None:
        frames = [
            {"file": m.group("file"), "line": m.group("line"), "func": m.group("func")}
            for m in _JS_FRAME.finditer(text)
        ]
        if not frames:
            return None
        exc_match = _JS_EXCEPTION.search(text)
        err_type = exc_match.group("err") if exc_match else "Error"
        err_msg  = exc_match.group("msg") if exc_match else text[:100]
        file_path = frames[0]["file"] if frames else ""
        line_num  = int(frames[0]["line"]) if frames else 0

        return DebugAnalysis(
            error_type=err_type,
            error_message=err_msg,
            file_path=file_path,
            line_number=line_num,
            suggestions=_rank_suggestions(err_type, err_msg),
            runtime=ErrorRuntime.JAVASCRIPT,
            confidence=0.75,
            additional_frames=frames[1:],
        )

    def _parse_rust(self, text: str) -> DebugAnalysis | None:
        panic_match = _RUST_PANIC.search(text)
        if not panic_match:
            return None

        err_msg   = panic_match.group("msg")
        file_path = panic_match.group("file")
        line_num  = int(panic_match.group("line"))

        return DebugAnalysis(
            error_type="panic",
            error_message=err_msg,
            file_path=file_path,
            line_number=line_num,
            suggestions=_rank_suggestions("panic", err_msg),
            runtime=ErrorRuntime.RUST,
            confidence=0.9,
        )

    def _parse_go(self, text: str) -> DebugAnalysis | None:
        panic_match = _GO_PANIC.search(text)
        if not panic_match:
            return None

        err_msg = panic_match.group("msg")
        frames = [
            {"file": m.group("file"), "line": m.group("line"), "func": ""}
            for m in _GO_FRAME.finditer(text)
        ]
        file_path = frames[0]["file"] if frames else ""
        line_num  = int(frames[0]["line"]) if frames else 0

        return DebugAnalysis(
            error_type="panic",
            error_message=err_msg,
            file_path=file_path,
            line_number=line_num,
            suggestions=_rank_suggestions("RuntimeError", err_msg),
            runtime=ErrorRuntime.GO,
            confidence=0.8,
            additional_frames=frames,
        )

    def _parse_java(self, text: str) -> DebugAnalysis | None:
        exc_match = _JAVA_EXCEPTION.search(text)
        if not exc_match:
            return None

        err_type = exc_match.group("err").split(".")[-1]
        err_msg  = exc_match.group("msg")
        frames = [
            {"file": m.group("file"), "line": m.group("line"), "func": m.group("class")}
            for m in _JAVA_FRAME.finditer(text)
        ]
        file_path = frames[0]["file"] if frames else ""
        line_num  = int(frames[0]["line"]) if frames else 0

        return DebugAnalysis(
            error_type=err_type,
            error_message=err_msg,
            file_path=file_path,
            line_number=line_num,
            suggestions=_rank_suggestions(err_type, err_msg),
            runtime=ErrorRuntime.JAVA,
            confidence=0.8,
            additional_frames=frames,
        )
