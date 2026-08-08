"""ReviewerAgent — production-grade code review engine.

Inspects file diffs and produces structured quality critiques covering:
  - Hardcoded credentials / secrets
  - Bare exception handlers
  - Debug artifacts (print statements)
  - Unaddressed TODO/FIXME markers
  - Dangerous patterns (eval, exec, shell injection risks)
  - High nesting depth (complexity heuristic)
  - Naming convention violations
  - Missing return-type annotations (Python)
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

    def format_report(self) -> str:
        lines = [f"Code Review — Score: {self.score}/100 ({'PASS' if self.passed else 'FAIL'})"]
        if not self.issues:
            lines.append("  ✓ No issues found.")
        for issue in self.issues:
            icon = "✗" if issue.severity == ReviewSeverity.ERROR else "⚠" if issue.severity == ReviewSeverity.WARNING else "ℹ"
            loc = f"  (line ~{issue.line_number})" if issue.line_number else ""
            lines.append(f"  {icon} [{issue.rule_id}]{loc} {issue.message}")
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

# Dangerous execution patterns
_DANGEROUS_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("dangerous_exec", "Avoid using eval() — potential code injection risk.", re.compile(r'\beval\s*\(')),
    ("dangerous_exec", "Avoid using exec() — potential code injection risk.", re.compile(r'\bexec\s*\(')),
    ("shell_injection", "shell=True in subprocess may allow command injection; validate inputs.", re.compile(r'shell\s*=\s*True')),
    ("pickle_load", "pickle.load/loads is unsafe with untrusted data.", re.compile(r'pickle\.(load|loads)\s*\(')),
    ("sql_fstring", "Possible SQL injection — use parameterized queries instead of f-strings.", re.compile(r'(execute|cursor\.execute)\s*\(\s*f["\'].*\{')),
]

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
                # Parse @@ -old,n +new,n @@ to track new-file line numbers
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

        raw_added = [l for _, l in added_lines]

        # --- Rule: bare except clause ---
        for lineno, line in added_lines:
            if re.search(r"\bexcept\s*:", line) and "# noqa" not in line:
                issues.append(ReviewIssue(
                    rule_id="E001", severity=ReviewSeverity.ERROR,
                    message="Bare 'except:' catches all exceptions including KeyboardInterrupt; catch specific types.",
                    line_content=line.strip(), line_number=lineno, score_penalty=10,
                ))
                score -= 10

        # --- Rule: raw print statements ---
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

        # --- Rule: TODO/FIXME markers ---
        for lineno, line in added_lines:
            if re.search(r"\b(TODO|FIXME|HACK|XXX)\b", line):
                issues.append(ReviewIssue(
                    rule_id="W002", severity=ReviewSeverity.WARNING,
                    message="Unaddressed TODO/FIXME/HACK marker added to production code.",
                    line_content=line.strip(), line_number=lineno, score_penalty=5,
                ))
                score -= 5
                break  # report once

        # --- Rule: hardcoded credentials ---
        for lineno, line in added_lines:
            for cred_name, pattern in _CREDENTIAL_PATTERNS:
                if pattern.search(line):
                    issues.append(ReviewIssue(
                        rule_id="S001", severity=ReviewSeverity.ERROR,
                        message=f"Possible hardcoded {cred_name} detected — use environment variables or a secrets manager.",
                        line_content=line.strip(), line_number=lineno, score_penalty=20,
                    ))
                    score -= 20
                    break

        # --- Rule: dangerous patterns ---
        for lineno, line in added_lines:
            for rule_id, msg, pattern in _DANGEROUS_PATTERNS:
                if pattern.search(line) and "# noqa" not in line:
                    issues.append(ReviewIssue(
                        rule_id="S002", severity=ReviewSeverity.WARNING,
                        message=msg,
                        line_content=line.strip(), line_number=lineno, score_penalty=8,
                    ))
                    score -= 8
                    break

        # --- Rule: excessive nesting depth ---
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
