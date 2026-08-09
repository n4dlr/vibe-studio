"""Tests for Predictive Coding Engine."""
from __future__ import annotations

import pytest
from vibe_studio.ai.predictive_engine import PredictiveCodingEngine
from vibe_studio.ai.suggestion_cache import SuggestionCache


def test_suggestion_cache():
    cache = SuggestionCache(capacity=2, ttl_seconds=1.0)
    cache.put("k1", [{"action": "a1"}])
    assert cache.get("k1") == [{"action": "a1"}]
    assert cache.get("nonexistent") is None


def test_predictive_engine_test_file():
    engine = PredictiveCodingEngine()
    suggestions = engine.predict_next_actions(
        current_file="tests/test_auth.py",
        file_content="def test_login(): pass",
    )
    assert len(suggestions) >= 2
    actions = [s["action"] for s in suggestions]
    assert "run_tests" in actions
    assert suggestions[0]["confidence"] >= 0.8


def test_predictive_engine_python_file():
    engine = PredictiveCodingEngine()
    suggestions = engine.predict_next_actions(
        current_file="src/vibe_studio/auth.py",
        file_content="def authenticate(user, password):\n    return True",
    )
    actions = [s["action"] for s in suggestions]
    assert "add_docstrings" in actions
