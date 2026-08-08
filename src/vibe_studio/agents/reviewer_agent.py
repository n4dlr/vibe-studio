"""ReviewerAgent — inspects file diffs, audits code changes, and produces code quality critiques."""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass


@dataclass
class ReviewResult:
    passed: bool
    score: int
    feedback: list[str]


class ReviewerAgent:
    """Specialized agent performing code review, quality audits, and diff analysis."""

    def review_diff(self, diff_text: str) -> ReviewResult:
        feedback: list[str] = []
        score = 100

        if not diff_text.strip():
            return ReviewResult(passed=True, score=100, feedback=["No changes detected in diff."])

        added_lines = [line for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]

        for line in added_lines:
            if "print(" in line and "# noqa" not in line:
                score -= 5
                feedback.append("Avoid leaving raw print statements in production code.")

            if "TODO" in line or "FIXME" in line:
                score -= 5
                feedback.append("Added line contains unaddressed TODO/FIXME marker.")

            if "except:" in line:
                score -= 10
                feedback.append("Avoid bare 'except:' clauses; catch specific exceptions.")

        passed = score >= 70
        return ReviewResult(passed=passed, score=max(0, score), feedback=feedback)
