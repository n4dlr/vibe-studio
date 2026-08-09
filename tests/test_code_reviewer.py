"""Tests for Code Reviewer Agent."""
from __future__ import annotations

import pytest
from vibe_studio.agents.code_reviewer import CodeReviewerAgent


def test_code_reviewer_clean_diff():
    reviewer = CodeReviewerAgent()
    diff = "@@ -1,2 +1,3 @@\n def calculate(a: int) -> int:\n+    return a + 1\n"
    res = reviewer.review_diff(diff)
    assert res.score >= 90.0
    assert res.approved is True


def test_code_reviewer_security_violation():
    reviewer = CodeReviewerAgent()
    diff = "@@ -1,2 +1,3 @@\n+SECRET_KEY = 'super_secret_123'\n+eval(user_input)\n"
    res = reviewer.review_diff(diff)
    assert res.approved is False
    assert res.score < 50.0
    assert any(c.category == "security" for c in res.comments)
    assert "PR Code Review Report" in res.to_markdown()
