"""Unit and Integration tests for J.A.R.V.I.S RAG Memory DB, Live Duplex Voice, and Screen Vision."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vibe_studio.jarvis.engine import JarvisCore
from vibe_studio.jarvis.memory_db import JarvisMemoryDB, _compute_fallback_vector, _cosine_similarity
from vibe_studio.jarvis.system_tools import JarvisSystemTools
from vibe_studio.jarvis.voice_listener import JarvisVoiceListener, LiveDuplexVoiceSession


@pytest.fixture
def temp_memory_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = JarvisMemoryDB(db_path=db_path)
    yield db
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


class TestJarvisMemoryDB:
    def test_init_and_stats(self, temp_memory_db):
        stats = temp_memory_db.get_stats()
        assert stats["conversations"] == 0
        assert stats["facts"] == 0
        assert stats["rag_chunks"] == 0

    def test_save_turn_and_history(self, temp_memory_db):
        temp_memory_db.save_turn("user", "Hello JARVIS, write a python script.", model="qwen3:8b")
        temp_memory_db.save_turn("assistant", "Right away, sir. Creating script.py now.", model="qwen3:8b")

        history = temp_memory_db.get_recent_history(n=5)
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[1].role == "assistant"
        assert "script.py" in history[1].content

        formatted = temp_memory_db.format_history_for_prompt(n=2)
        assert "USER: Hello JARVIS" in formatted
        assert "ASSISTANT: Right away" in formatted

    def test_auto_fact_extraction(self, temp_memory_db):
        temp_memory_db.save_turn("user", "Mənim adım Əlidir və sevdiyim maşın Porsche 911-dir.")
        facts = temp_memory_db.recall_facts()
        keys = [f.fact_key for f in facts]
        assert "user_name" in keys

        name_fact = next(f for f in facts if f.fact_key == "user_name")
        assert name_fact.fact_value == "Əli" or "Əli" in name_fact.fact_value

    def test_semantic_rag_search(self, temp_memory_db):
        temp_memory_db.index_chunk("note", "Project Setup", "The backend server uses FastAPI on port 8000 with PostgreSQL.")
        temp_memory_db.index_chunk("note", "Cooking Recipe", "Delicious pasta requires olive oil, garlic, and fresh basil.")

        results = temp_memory_db.search_rag("What port does the backend FastAPI server run on?", top_k=2)
        assert len(results) >= 1
        assert "FastAPI" in results[0].chunk_text

        ctx = temp_memory_db.build_rag_context("FastAPI port")
        assert "FastAPI on port 8000" in ctx

    def test_vector_similarity_math(self):
        v1 = _compute_fallback_vector("FastAPI web server python", dim=64)
        v2 = _compute_fallback_vector("FastAPI python backend server", dim=64)
        v3 = _compute_fallback_vector("Strawberry banana smoothie recipe", dim=64)

        score_related = _cosine_similarity(v1, v2)
        score_unrelated = _cosine_similarity(v1, v3)
        assert score_related > score_unrelated


class TestScreenVisionAndTools:
    def test_play_youtube_video(self, tmp_path):
        tools = JarvisSystemTools(workspace_root=tmp_path)
        with patch.object(tools, "open_url", return_value={"status": "success"}):
            res = tools.play_youtube_video("inna caliente")
            assert res["status"] == "success"
            assert "youtube.com/results" in res["url"]
            assert "inna+caliente" in res["url"]

    def test_analyze_screenshot_vision_fallback(self, tmp_path):
        tools = JarvisSystemTools(workspace_root=tmp_path)
        dummy_shot = tmp_path / "dummy_screen.png"
        dummy_shot.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        with patch.object(tools, "take_screenshot", return_value={"status": "success", "path": str(dummy_shot)}):
            res = tools.analyze_screenshot_vision(query="What is on my screen?")
            assert res["status"] == "success"
            assert "path" in res
            assert "analysis" in res

    def test_get_screen_summary(self, tmp_path):
        tools = JarvisSystemTools(workspace_root=tmp_path)
        with patch.object(tools, "analyze_screenshot_vision", return_value={"status": "success", "analysis": "Desktop and IDE active"}):
            res = tools.get_screen_summary()
            assert res["status"] == "success"
            assert res["analysis"] == "Desktop and IDE active"


class TestLiveDuplexVoice:
    def test_duplex_session_lifecycle(self):
        listener = JarvisVoiceListener()
        states_recorded = []
        transcripts_recorded = []

        duplex = LiveDuplexVoiceSession(
            listener=listener,
            on_transcribed=lambda t: transcripts_recorded.append(t),
            on_state_changed=lambda s: states_recorded.append(s),
        )

        assert not duplex.is_active
        duplex.set_tts_speaking(True)
        assert duplex._tts_speaking
        duplex.set_tts_speaking(False)
        assert not duplex._tts_speaking

    def test_jarvis_core_memory_integration(self, tmp_path):
        core = JarvisCore(workspace_root=tmp_path)
        resp = core.execute_command("salam")
        assert resp.spoken_text
        stats = core.memory_db.get_stats()
        assert stats["conversations"] >= 2  # user + assistant turns stored
