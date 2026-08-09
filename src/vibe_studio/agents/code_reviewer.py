"""Code Reviewer Agent — Automated Pull Request code review and quality analysis."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ReviewComment:
    category: str  # "security", "performance", "style", "testing"
    severity: str  # "CRITICAL", "WARNING", "INFO"
    line_hint: Optional[int]
    message: str
    suggestion: Optional[str] = None


@dataclass
class PullRequestReviewResult:
    score: float  # 0 to 100
    approved: bool
    summary: str
    comments: List[ReviewComment] = field(default_factory=list)

    def to_markdown(self) -> str:
        md = [f"# PR Code Review Report (Score: {self.score}/100)\n"]
        md.append(f"**Status:** {'✅ APPROVED' if self.approved else '⚠️ CHANGES REQUESTED'}\n")
        md.append(f"**Summary:** {self.summary}\n")
        if self.comments:
            md.append("## Detailed Comments\n")
            for c in self.comments:
                sev_badge = "🔴" if c.severity == "CRITICAL" else ("🟡" if c.severity == "WARNING" else "🔵")
                line_str = f"Line {c.line_hint}: " if c.line_hint else ""
                md.append(f"- {sev_badge} **[{c.category.upper()}]** {line_str}{c.message}")
                if c.suggestion:
                    md.append(f"  > *Suggestion:* `{c.suggestion}`")
        return "\n".join(md)


class CodeReviewerAgent:
    """Automated PR review agent analyzing git diffs for bugs, vulnerabilities, and performance."""

    def review_diff(self, diff_text: str, pr_title: str = "Pull Request Review") -> PullRequestReviewResult:
        comments: List[ReviewComment] = []
        score = 100.0

        lines = diff_text.splitlines()
        current_line = 0

        for line in lines:
            if line.startswith("@@"):
                # Parse line numbers from unified diff header @@ -a,b +c,d @@
                m = re.search(r"\+(\d+)", line)
                if m:
                    current_line = int(m.group(1))
                continue

            if line.startswith("+") and not line.startswith("+++"):
                added_code = line[1:]
                current_line += 1

                # 1. Security Check
                if re.search(r"(password|api_key|secret|token|key)\s*=\s*['\"][^'\"]+['\"]", added_code, re.I):
                    comments.append(
                        ReviewComment(
                            category="security",
                            severity="CRITICAL",
                            line_hint=current_line,
                            message="Hardcoded secret or credential detected in diff.",
                            suggestion="Use environment variables or secret manager.",
                        )
                    )
                    score -= 25.0

                if "eval(" in added_code or "exec(" in added_code:
                    comments.append(
                        ReviewComment(
                            category="security",
                            severity="CRITICAL",
                            line_hint=current_line,
                            message="Unsafe dynamic code execution (eval/exec) detected.",
                            suggestion="Avoid dynamic execution or use ast.literal_eval.",
                        )
                    )
                    score -= 30.0

                # 2. Performance Check
                if "for " in added_code and "rglob(" in added_code:
                    comments.append(
                        ReviewComment(
                            category="performance",
                            severity="WARNING",
                            line_hint=current_line,
                            message="Potentially slow recursive filesystem scan inside loop.",
                            suggestion="Cache rglob results outside the loop.",
                        )
                    )
                    score -= 10.0

                # 3. Style & Type Hints Check
                if "def " in added_code and "->" not in added_code:
                    comments.append(
                        ReviewComment(
                            category="style",
                            severity="INFO",
                            line_hint=current_line,
                            message="Function missing return type annotation.",
                            suggestion="Add explicit return type hint (e.g. -> None).",
                        )
                    )
                    score -= 5.0

        final_score = max(0.0, min(100.0, round(score, 1)))
        approved = final_score >= 75.0 and not any(c.severity == "CRITICAL" for c in comments)
        summary = (
            f"Analyzed {len(lines)} lines in diff. Found {len(comments)} issues."
            if comments
            else "Clean diff! No security or performance issues detected."
        )

        return PullRequestReviewResult(
            score=final_score,
            approved=approved,
            summary=summary,
            comments=comments,
        )
