"""Root Cause Analyzer — AST-based data-flow tracing for smarter self-healing.

Sütun 3 (Root Cause Analysis):
  - DataFlowTrace   : captures where a failing variable was defined / assigned.
  - ErrorFingerprint: (error_type, file_path, line_no) hash — detects repeated failures.
  - RootCauseAnalyzer: parses traceback, extracts the failing variable name from the
                       error message, traces assignments in the source via AST, and
                       produces an actionable hint for the coding agent.

Usage::

    rca = RootCauseAnalyzer()
    hint = rca.analyze(
        traceback_text="...",
        source_code=Path("src/foo.py").read_text(),
        file_path="src/foo.py",
    )
    # hint.prompt_hint → "DATA FLOW: `result` assigned at line 42 via call to `compute()`"
"""
from __future__ import annotations

import ast
import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns for extracting variable names from error messages
# ---------------------------------------------------------------------------

_VAR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"name '(\w+)' is not defined"),
    re.compile(r"AttributeError: '[\w.]+' object has no attribute '(\w+)'"),
    re.compile(r"KeyError: '?(\w+)'?"),
    re.compile(r"(\w+) = .* expected (\w+)"),
    re.compile(r"AssertionError.*\b(\w+)\b"),
    re.compile(r"'(\w+)' is None"),
    re.compile(r"expected (\w+),? got"),
]

_TRACEBACK_LINE_RE = re.compile(
    r'File "([^"]+)", line (\d+)',
)

_ASSERT_VAR_RE = re.compile(r"\bassert\b.+\b(\w+)\b")


# ---------------------------------------------------------------------------
# DataFlowTrace
# ---------------------------------------------------------------------------

@dataclass
class DataFlowTrace:
    """Result of tracing a variable's data flow through source AST."""

    variable: str
    file_path: str
    error_line: int
    definitions: list[tuple[int, str]] = field(default_factory=list)
    """List of (line_number, short_snippet) where variable is defined/assigned."""
    call_chain: list[str] = field(default_factory=list)
    """Function names that returned/modified the variable up the call stack."""

    @property
    def prompt_hint(self) -> str:
        if not self.definitions:
            return f"DATA FLOW: `{self.variable}` has no tracked assignment before line {self.error_line}."
        defs_text = "; ".join(f"line {ln}: {snip}" for ln, snip in self.definitions[:3])
        chain_text = f" via {' → '.join(self.call_chain[:3])}" if self.call_chain else ""
        return (
            f"DATA FLOW: `{self.variable}` assigned at {defs_text}{chain_text}. "
            f"Error occurred at line {self.error_line}."
        )


# ---------------------------------------------------------------------------
# ErrorFingerprint
# ---------------------------------------------------------------------------

@dataclass
class ErrorFingerprint:
    """Compact hash identifying a unique error location to detect repeated failures."""

    error_type: str
    file_path: str
    line_no: int

    @property
    def hash(self) -> str:
        raw = f"{self.error_type}:{self.file_path}:{self.line_no}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ErrorFingerprint):
            return NotImplemented
        return self.hash == other.hash

    def __hash__(self) -> int:
        return hash(self.hash)


# ---------------------------------------------------------------------------
# AST helper — assignment collector
# ---------------------------------------------------------------------------

class _AssignmentCollector(ast.NodeVisitor):
    """Collect all assignment statements for a given variable name."""

    def __init__(self, target_name: str) -> None:
        self.target = target_name
        self.assignments: list[tuple[int, str]] = []

    def _record(self, node: ast.stmt, snippet: str) -> None:
        self.assignments.append((node.lineno, snippet[:80]))

    def visit_Assign(self, node: ast.Assign) -> None:
        for tgt in node.targets:
            try:
                if ast.unparse(tgt).strip() == self.target:
                    self._record(node, ast.unparse(node).strip())
            except Exception:
                pass
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        try:
            if ast.unparse(node.target).strip() == self.target:
                self._record(node, ast.unparse(node).strip())
        except Exception:
            pass
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        try:
            if node.value and ast.unparse(node.target).strip() == self.target:
                self._record(node, ast.unparse(node).strip())
        except Exception:
            pass
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        try:
            if ast.unparse(node.target).strip() == self.target:
                self._record(node, f"for {self.target} in {ast.unparse(node.iter).strip()}")
        except Exception:
            pass
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars:
                try:
                    if ast.unparse(item.optional_vars).strip() == self.target:
                        self._record(node, f"with ... as {self.target}")
                except Exception:
                    pass
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# RootCauseAnalyzer
# ---------------------------------------------------------------------------

class RootCauseAnalyzer:
    """Extracts actionable root-cause hints from Python tracebacks using AST analysis."""

    def __init__(self) -> None:
        self._seen_fingerprints: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        traceback_text: str,
        source_code: str = "",
        file_path: str = "",
    ) -> DataFlowTrace | None:
        """Parse *traceback_text* and return a DataFlowTrace with a prompt-ready hint.

        Returns None if no actionable variable can be identified.
        """
        fp, error_line = self._extract_fingerprint(traceback_text, file_path)
        if fp is None:
            return None

        # Track repeated failures
        count = self._seen_fingerprints.get(fp.hash, 0) + 1
        self._seen_fingerprints[fp.hash] = count
        if count > 2:
            logger.debug(
                "RootCause: fingerprint %s seen %d times — agent should switch strategy",
                fp.hash, count,
            )

        var_name = self._extract_variable(traceback_text)
        if not var_name:
            return DataFlowTrace(
                variable="<unknown>",
                file_path=file_path,
                error_line=error_line,
            )

        definitions: list[tuple[int, str]] = []
        call_chain: list[str] = []

        if source_code:
            definitions, call_chain = self._trace_variable(source_code, var_name, error_line)

        trace = DataFlowTrace(
            variable=var_name,
            file_path=file_path,
            error_line=error_line,
            definitions=definitions,
            call_chain=call_chain,
        )
        logger.debug("RootCause: %s", trace.prompt_hint)
        return trace

    def fingerprint_count(self, traceback_text: str, file_path: str = "") -> int:
        """Return how many times this exact error location has been seen."""
        fp, _ = self._extract_fingerprint(traceback_text, file_path)
        if fp is None:
            return 0
        return self._seen_fingerprints.get(fp.hash, 0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_fingerprint(
        self, traceback_text: str, file_path: str
    ) -> tuple[ErrorFingerprint | None, int]:
        error_type = "UnknownError"
        error_line = 0

        # Extract error type from last line
        lines = traceback_text.strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith(" ") and ":" in line:
                error_type = line.split(":")[0].strip()
                break

        # Extract last file/line reference
        for match in _TRACEBACK_LINE_RE.finditer(traceback_text):
            candidate_file = match.group(1)
            candidate_line = int(match.group(2))
            if file_path and Path(candidate_file).name == Path(file_path).name:
                error_line = candidate_line
                file_path = candidate_file

        if not error_type or error_type == "UnknownError":
            return None, 0

        return ErrorFingerprint(error_type=error_type, file_path=file_path, line_no=error_line), error_line

    def _extract_variable(self, traceback_text: str) -> str:
        """Try to extract a meaningful variable/attribute name from the error message."""
        last_lines = traceback_text.strip().splitlines()[-3:]
        for line in reversed(last_lines):
            for pattern in _VAR_PATTERNS:
                m = pattern.search(line)
                if m:
                    name = m.group(1)
                    if name and name not in {"self", "cls", "None", "True", "False"}:
                        return name
        return ""

    def _trace_variable(
        self, source_code: str, var_name: str, error_line: int
    ) -> tuple[list[tuple[int, str]], list[str]]:
        """AST-walk source to find where var_name was assigned before error_line."""
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return [], []

        collector = _AssignmentCollector(var_name)
        collector.visit(tree)

        # Only assignments before the error line
        defs = [(ln, snip) for ln, snip in collector.assignments if ln <= error_line]

        # Extract function names from call chain in source lines near error
        src_lines = source_code.splitlines()
        call_chain: list[str] = []
        start = max(0, error_line - 10)
        end = min(len(src_lines), error_line)
        for src_line in src_lines[start:end]:
            for m in re.finditer(r"\b(\w+)\s*\(", src_line):
                fname = m.group(1)
                if fname not in {"if", "for", "while", "print", "len", "range", "isinstance"}:
                    call_chain.append(fname)

        return defs, list(dict.fromkeys(call_chain))[:5]
