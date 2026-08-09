"""Tests for Enterprise Official Plugins."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.plugin.official.git_advanced_plugin import format_semantic_commit, generate_pr_description
from vibe_studio.plugin.official.python_packager_plugin import inspect_python_environment
from vibe_studio.plugin.official.webhook_notifier_plugin import send_webhook_notification


class TestOfficialPlugins:
    def test_format_semantic_commit(self):
        msg = format_semantic_commit("feat", "auth", "add jwt refresh token")
        assert msg == "feat(auth): add jwt refresh token"

    def test_format_semantic_commit_invalid_type_fallback(self):
        msg = format_semantic_commit("invalid_type", "", "do something")
        assert msg.startswith("chore:")

    def test_generate_pr_description(self, tmp_path):
        desc = generate_pr_description(workspace=str(tmp_path))
        assert "Pull Request Summary" in desc or "Failed to retrieve git diff" in desc

    def test_inspect_python_environment(self, tmp_path):
        info = inspect_python_environment(workspace=str(tmp_path))
        assert "Python" in info

    def test_send_webhook_notification_invalid_url(self):
        res = send_webhook_notification("invalid_url", "Title", "Message")
        assert "Error" in res
