"""ReviewerAgent — production-grade code review engine.

Inspects file diffs and produces structured quality critiques covering:
  - Hardcoded credentials / secrets        (S001)
  - Dangerous patterns (eval/exec/pickle)  (S002)
  - SQL f-string injection risks           (S003)
  - Bare exception handlers                (E001)
  - Raw print statements (debug artifacts) (W001)
  - Unaddressed TODO/FIXME/HACK markers    (W002)
  - Naming convention violations           (R001)
  - Missing return-type annotations        (R002)
  - High nesting depth / complexity        (C001)

All rules respect ``# noqa`` inline suppression.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ReviewSeverity(str, Enum):
    ERROR   = "error"      # must fix — blocks pass
    WARNING = "warning"    # should fix — reduces score
    INFO    = "info"       # note — no score impact


@dataclass
class ReviewIssue:
    rule_id: str
    severity: ReviewSeverity
    message: str
    line_content: str = ""
    line_number: int | None = None
    score_penalty: int = 0


@dataclass
class ReviewResult:
    passed: bool
    score: int
    feedback: list[str]
    issues: list[ReviewIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == ReviewSeverity.ERROR]

    @property
    def warnings(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == ReviewSeverity.WARNING]

    @property
    def summary(self) -> str:
        """One-line summary suitable for status bars or agent feedback."""
        if self.passed:
            return f"✓ Review passed ({self.score}/100, {len(self.issues)} notes)"
        return (
            f"✗ Review failed ({self.score}/100): "
            + ", ".join(f"[{i.rule_id}] {i.message[:60]}" for i in self.errors[:2])
        )

    def format_report(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        lines = [f"Code Review — Score: {self.score}/100  [{verdict}]"]
        if not self.issues:
            lines.append("  ✓ No issues found.")
        else:
            # Group by severity for readability
            for sev in (ReviewSeverity.ERROR, ReviewSeverity.WARNING, ReviewSeverity.INFO):
                group = [i for i in self.issues if i.severity == sev]
                if not group:
                    continue
                icon = {ReviewSeverity.ERROR: "✗", ReviewSeverity.WARNING: "⚠", ReviewSeverity.INFO: "ℹ"}[sev]
                for issue in group:
                    loc = f" line {issue.line_number}" if issue.line_number else ""
                    penalty = f" (-{issue.score_penalty}pt)" if issue.score_penalty else ""
                    lines.append(f"  {icon} [{issue.rule_id}]{loc}{penalty}  {issue.message}")
                    if issue.line_content:
                        lines.append(f"       | {issue.line_content[:120]}")
        lines.append("")
        lines.append(f"Feedback: {'; '.join(self.feedback[:3])}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

# Credential / secret patterns (regex against added line content)
_CREDENTIAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("password",   re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{3,}["\']')),
    ("api_key",    re.compile(r'(?i)(api_?key|apikey|api_token)\s*=\s*["\'][A-Za-z0-9_\-]{8,}["\']')),
    ("secret",     re.compile(r'(?i)(secret|private_?key)\s*=\s*["\'][^"\']{4,}["\']')),
    ("bearer",     re.compile(r'(?i)(Authorization|Bearer)\s*[=:]\s*["\'][A-Za-z0-9._\-]{10,}["\']')),
    ("aws_access", re.compile(r'AKIA[0-9A-Z]{16}')),
    ("ghp_token",  re.compile(r'ghp_[A-Za-z0-9]{36}')),
]

# Dangerous execution patterns — severity WARNING, rule S002
_DANGEROUS_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("dangerous_exec", "Avoid using eval() — potential code injection risk.", re.compile(r'\beval\s*\(')),
    ("dangerous_exec", "Avoid using exec() — potential code injection risk.", re.compile(r'\bexec\s*\(')),
    ("shell_injection", "shell=True in subprocess may allow command injection; validate inputs.", re.compile(r'shell\s*=\s*True')),
    ("pickle_load", "pickle.load/loads is unsafe with untrusted data.", re.compile(r'pickle\.(load|loads)\s*\(')),
]

# SQL injection via f-strings — separate rule S003
_SQL_INJECTION_PATTERN = re.compile(r'(execute|cursor\.execute)\s*\(\s*f["\'].*\{')

# Naming convention violations (PEP 8) — rule R001
_CLASS_NAME_RE = re.compile(r'^\s*class\s+([a-z][A-Za-z0-9_]*)\b')  # should be CamelCase
_CONST_RE = re.compile(r'^\s*([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\s*=')  # uppercase consts OK
_FUNCTION_CAMEL = re.compile(r'^\s*def\s+([A-Z][a-z])\w*\s*\(')    # camelCase function name

# Missing return-type annotations — rule R002 (Python only)
_MISSING_RETURN_ANNOT = re.compile(r'^\s*def\s+\w+\([^)]*\)\s*(?!->)\s*:')

# Complexity heuristic: count leading spaces to detect deep nesting
def _max_nesting_depth(lines: list[str]) -> int:
    max_depth = 0
    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = len(line) - len(stripped)
        depth = indent // 4
        if depth > max_depth:
            max_depth = depth
    return max_depth


class ReviewerAgent:
    """Specialized agent performing code review, quality audits, and diff analysis."""

    PASS_THRESHOLD = 70  # minimum score to pass

    def review_diff(self, diff_text: str) -> ReviewResult:
        """Analyse a unified diff and return a structured review result."""
        if not diff_text.strip():
            return ReviewResult(
                passed=True, score=100,
                feedback=["No changes detected in diff."],
                issues=[],
            )

        issues: list[ReviewIssue] = []
        score = 100

        # Extract added lines with rough line numbers
        added_lines: list[tuple[int | None, str]] = []
        current_lineno: int | None = None
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("@@"):
                m = re.search(r"\+(\d+)", raw_line)
                if m:
                    current_lineno = int(m.group(1)) - 1
            elif raw_line.startswith("+") and not raw_line.startswith("+++"):
                if current_lineno is not None:
                    current_lineno += 1
                added_lines.append((current_lineno, raw_line[1:]))
            elif raw_line.startswith(" "):
                if current_lineno is not None:
                    current_lineno += 1

        raw_added = [ln for _, ln in added_lines]

        # --- Rule E001: bare except clause ---
        for lineno, line in added_lines:
            if re.search(r"\bexcept\s*:", line) and "# noqa" not in line:
                issues.append(ReviewIssue(
                    rule_id="E001", severity=ReviewSeverity.ERROR,
                    message="Bare 'except:' catches all exceptions including KeyboardInterrupt; catch specific types.",
                    line_content=line.strip(), line_number=lineno, score_penalty=10,
                ))
                score -= 10

        # --- Rule W001: raw print statements ---
        print_seen = False
        for lineno, line in added_lines:
            if re.search(r"\bprint\s*\(", line) and "# noqa" not in line and not print_seen:
                issues.append(ReviewIssue(
                    rule_id="W001", severity=ReviewSeverity.WARNING,
                    message="Raw print() found — use logging instead for production code.",
                    line_content=line.strip(), line_number=lineno, score_penalty=5,
                ))
                score -= 5
                print_seen = True  # report once per diff

        # --- Rule W002: TODO/FIXME markers ---
        todo_seen = False
        for lineno, line in added_lines:
            if re.search(r"\b(TODO|FIXME|HACK|XXX)\b", line) and not todo_seen:
                issues.append(ReviewIssue(
                    rule_id="W002", severity=ReviewSeverity.WARNING,
                    message="Unaddressed TODO/FIXME/HACK marker added to production code.",
                    line_content=line.strip(), line_number=lineno, score_penalty=5,
                ))
                score -= 5
                todo_seen = True  # report once per diff

        # --- Rule S001: hardcoded credentials ---
        for lineno, line in added_lines:
            matched_cred = False
            for cred_name, pattern in _CREDENTIAL_PATTERNS:
                if pattern.search(line):
                    issues.append(ReviewIssue(
                        rule_id="S001", severity=ReviewSeverity.ERROR,
                        message=f"Possible hardcoded {cred_name} detected — use environment variables or a secrets manager.",
                        line_content=line.strip(), line_number=lineno, score_penalty=20,
                    ))
                    score -= 20
                    matched_cred = True
                    break
            if matched_cred:
                continue  # only one S001 per line

        # --- Rule S002: dangerous execution patterns ---
        for lineno, line in added_lines:
            if "# noqa" in line:
                continue
            for _rule_name, msg, pattern in _DANGEROUS_PATTERNS:
                if pattern.search(line):
                    issues.append(ReviewIssue(
                        rule_id="S002", severity=ReviewSeverity.WARNING,
                        message=msg,
                        line_content=line.strip(), line_number=lineno, score_penalty=8,
                    ))
                    score -= 8
                    break

        # --- Rule S003: SQL injection via f-strings ---
        for lineno, line in added_lines:
            if "# noqa" not in line and _SQL_INJECTION_PATTERN.search(line):
                issues.append(ReviewIssue(
                    rule_id="S003", severity=ReviewSeverity.ERROR,
                    message="SQL f-string interpolation detected — use parameterized queries to prevent injection.",
                    line_content=line.strip(), line_number=lineno, score_penalty=15,
                ))
                score -= 15

        # --- Rule R001: naming convention violations (PEP 8) ---
        for lineno, line in added_lines:
            if "# noqa" in line:
                continue
            if _CLASS_NAME_RE.search(line):
                m = _CLASS_NAME_RE.search(line)
                issues.append(ReviewIssue(
                    rule_id="R001", severity=ReviewSeverity.WARNING,
                    message=f"Class '{m.group(1)}' should use CamelCase naming (PEP 8).",
                    line_content=line.strip(), line_number=lineno, score_penalty=3,
                ))
                score -= 3
            elif _FUNCTION_CAMEL.search(line):
                m = _FUNCTION_CAMEL.search(line)
                issues.append(ReviewIssue(
                    rule_id="R001", severity=ReviewSeverity.WARNING,
                    message=f"Function starts with uppercase — use snake_case for function names (PEP 8).",
                    line_content=line.strip(), line_number=lineno, score_penalty=3,
                ))
                score -= 3

        # --- Rule R002: missing return-type annotations (Python) ---
        unannotated_count = 0
        for lineno, line in added_lines:
            if "# noqa" not in line and _MISSING_RETURN_ANNOT.search(line):
                unannotated_count += 1
        if unannotated_count >= 3:  # threshold: 3+ unannotated functions
            issues.append(ReviewIssue(
                rule_id="R002", severity=ReviewSeverity.INFO,
                message=f"{unannotated_count} function(s) added without return-type annotations — consider adding -> Type hints.",
                score_penalty=0,
            ))

        # --- Rule C001: excessive nesting depth ---
        max_depth = _max_nesting_depth(raw_added)
        if max_depth >= 5:
            issues.append(ReviewIssue(
                rule_id="C001", severity=ReviewSeverity.WARNING,
                message=f"High nesting depth ({max_depth} levels) detected — consider extracting sub-functions.",
                score_penalty=5,
            ))
            score -= 5

        score = max(0, score)
        passed = score >= self.PASS_THRESHOLD

        # Build backwards-compat feedback list
        feedback = [i.message for i in issues] if issues else ["No issues detected."]

        return ReviewResult(passed=passed, score=score, feedback=feedback, issues=issues)

    def review_file(self, file_path: str | Path, content: str | None = None) -> ReviewResult:
        """Review an entire file (not just a diff).

        Reads the file if content is not provided.
        """
        path = Path(file_path)
        if content is None:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                return ReviewResult(passed=False, score=0, feedback=[f"Could not read file: {exc}"])

        # Build a synthetic diff (all lines are "added")
        fake_diff = f"--- a/{path.name}\n+++ b/{path.name}\n@@ -0,0 +1,{len(content.splitlines())} @@\n"
        for line in content.splitlines():
            fake_diff += f"+{line}\n"

        return self.review_diff(fake_diff)
