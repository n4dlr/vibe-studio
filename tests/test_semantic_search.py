"""Tests for Natural Language Code Search."""
from __future__ import annotations

import pytest
from vibe_studio.context.semantic_search import SemanticCodeSearch


def test_semantic_code_search(tmp_path):
    # Create sample codebase
    db_file = tmp_path / "db_manager.py"
    db_file.write_text("class DatabaseSession:\n    def connect_sqlite(self):\n        pass\n")

    auth_file = tmp_path / "auth.py"
    auth_file.write_text("def authenticate_user(username, password):\n    return True\n")

    searcher = SemanticCodeSearch(workspace_root=tmp_path)

    # Search natural language query for DB
    db_results = searcher.search("məlumat bazasına qoşulan hissə", top_k=5)
    assert len(db_results) >= 1
    assert "db_manager.py" in db_results[0].file_path
    assert "DatabaseSession" in db_results[0].symbol_name

    # Search natural language query for auth
    auth_results = searcher.search("where is user authentication?", top_k=5)
    assert len(auth_results) >= 1
    assert "auth.py" in auth_results[0].file_path
