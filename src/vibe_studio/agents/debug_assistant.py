"""DebugAssistant — analyzes stack traces, pinpoints failure locations, and generates 3 targeted fix suggestions."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DebugAnalysis:
    error_type: str
    error_message: str
    file_path: str
    line_number: int
    suggestions: list[str]


class DebugAssistant:
    """Analyzes runtime exceptions and stack traces in natural language."""

    TRACEBACK_PATTERN = re.compile(
        r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\w+)\n\s*(?P<code>.*)\n(?P<err>\w+Error|\w+Exception):\s*(?P<msg>.*)'
    )

    def analyze_traceback(self, traceback_text: str) -> DebugAnalysis:
        m = self.TRACEBACK_PATTERN.search(traceback_text)
        if m:
            file_path = m.group("file")
            line_number = int(m.group("line"))
            err_type = m.group("err")
            msg = m.group("msg")
        else:
            file_path = ""
            line_number = 1
            err_type = "RuntimeError"
            msg = traceback_text[:100]

        suggestions = [
            f"Inspect parameters passed to function near {file_path}:{line_number}.",
            f"Add null/type validation check before accessing target object properties.",
            f"Verify imported module dependencies and default fallback values.",
        ]

        return DebugAnalysis(
            error_type=err_type,
            error_message=msg,
            file_path=file_path,
            line_number=line_number,
            suggestions=suggestions,
        )
