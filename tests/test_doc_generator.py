"""Tests for Auto-Documentation Engine."""
from __future__ import annotations

import pytest
from vibe_studio.project.doc_generator import AutoDocGenerator


def test_auto_doc_generator(tmp_path):
    sample = tmp_path / "service.py"
    sample.write_text('"""Main Service Module."""\n\nclass UserService:\n    """Handles user operations."""\n    def get_user(self, user_id):\n        """Fetch user by ID."""\n        pass\n')

    gen = AutoDocGenerator(workspace_root=tmp_path)
    api_doc = gen.generate_api_reference()
    assert "# API Reference" in api_doc
    assert "UserService" in api_doc
    assert "get_user" in api_doc

    mermaid = gen.generate_mermaid_diagram()
    assert "classDiagram" in mermaid
    assert "UserService" in mermaid
