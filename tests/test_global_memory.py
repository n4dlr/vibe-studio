"""Tests for GlobalMemory — cross-project pattern store."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.core.global_memory import GlobalMemory, PatternRecord


class TestGlobalMemory:
    def test_record_and_recall_pattern(self, tmp_path):
        db = tmp_path / "global_test.db"
        gm = GlobalMemory(db_path=db)

        gm.record_pattern(
            framework="django",
            pattern_type="auth",
            keyword="custom login view",
            solution="Use CustomLoginView extending LoginView with custom template",
        )

        patterns = gm.recall_patterns("how to create custom login view", frameworks=["django"])
        assert len(patterns) >= 1
        p = patterns[0]
        assert isinstance(p, PatternRecord)
        assert "CustomLoginView" in p.solution_summary
        assert p.use_count == 1

    def test_record_pattern_increments_use_count(self, tmp_path):
        db = tmp_path / "global_test.db"
        gm = GlobalMemory(db_path=db)

        gm.record_pattern("fastapi", "route", "post endpoint", "Use @app.post decorator")
        gm.record_pattern("fastapi", "route", "post endpoint", "Use @app.post decorator updated")

        patterns = gm.recall_patterns("post endpoint")
        assert len(patterns) == 1
        assert patterns[0].use_count == 2
        assert "updated" in patterns[0].solution_summary

    def test_build_global_hint_formatting(self, tmp_path):
        db = tmp_path / "global_test.db"
        gm = GlobalMemory(db_path=db)

        gm.record_pattern("react", "state", "usecontext hook", "Wrap app in Provider and use useContext")

        hint = gm.build_global_hint("usecontext hook in react")
        assert "GLOBAL PATTERNS" in hint
        assert "Provider" in hint

    def test_build_global_hint_empty_when_no_match(self, tmp_path):
        db = tmp_path / "global_test.db"
        gm = GlobalMemory(db_path=db)
        hint = gm.build_global_hint("completely unrelated prompt xyz123")
        assert hint == ""

    def test_global_kv_set_get(self, tmp_path):
        db = tmp_path / "global_test.db"
        gm = GlobalMemory(db_path=db)

        gm.set("preferred_theme", "dark")
        assert gm.get("preferred_theme") == "dark"
        assert gm.get("nonexistent", default="light") == "light"

    def test_stats(self, tmp_path):
        db = tmp_path / "global_test.db"
        gm = GlobalMemory(db_path=db)
        gm.record_pattern("flask", "route", "get endpoint", "Use @app.route")
        st = gm.stats()
        assert st["total_patterns"] == 1
        assert "flask" in st["frameworks"]
