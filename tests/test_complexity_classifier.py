"""Tests for ComplexityClassifier — Adaptive Turbo Mode tier routing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.agents.complexity_classifier import (
    ComplexityClassifier, TaskComplexity
)


class TestComplexityClassifier:
    def setup_method(self):
        self.clf = ComplexityClassifier()

    def test_classify_fast_typo_fix(self):
        tier = self.clf.classify("fix typo in README.md", active_file="README.md")
        assert tier == TaskComplexity.FAST

    def test_classify_fast_short_prompt(self):
        tier = self.clf.classify("rename function", active_file="main.py")
        assert tier == TaskComplexity.FAST

    def test_classify_normal_endpoint(self):
        tier = self.clf.classify("add new user login endpoint to api handler")
        assert tier == TaskComplexity.NORMAL

    def test_classify_normal_unit_tests(self):
        tier = self.clf.classify("implement unit tests for auth module")
        assert tier == TaskComplexity.NORMAL

    def test_classify_deep_refactor(self):
        tier = self.clf.classify("refactor the entire database access layer")
        assert tier == TaskComplexity.DEEP

    def test_classify_deep_rewrite(self):
        tier = self.clf.classify("rewrite the whole authentication architecture across the codebase")
        assert tier == TaskComplexity.DEEP

    def test_classify_deep_long_prompt(self):
        long_prompt = " " .join(["word"] * 55)
        tier = self.clf.classify(long_prompt)
        assert tier == TaskComplexity.DEEP

    def test_describe_returns_nonempty_string(self):
        for tier in TaskComplexity:
            desc = self.clf.describe(tier)
            assert isinstance(desc, str)
            assert len(desc) > 10
