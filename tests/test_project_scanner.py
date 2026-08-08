from __future__ import annotations

from pathlib import Path

from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.project.project_scanner import ProjectScanner


def test_project_scanner_and_context_engine(tmp_path: Path):
    py_file = tmp_path / "src" / "login_page.py"
    py_file.parent.mkdir(parents=True)
    py_file.write_text("class LoginPage:\n    def render(self):\n        return 'bg-blue'\n", encoding="utf-8")

    scanner = ProjectScanner(tmp_path)
    summary = scanner.scan()

    assert "python" in summary.languages
    assert len(summary.files) == 1
    assert len(summary.files[0].symbols) == 2

    engine = ContextEngine(tmp_path)
    bundle = engine.build("Login page-in backgroundunu dəyiş.")
    assert len(bundle.items) == 1
    assert bundle.items[0].path == "src/login_page.py"
    assert "bg-blue" in bundle.format_prompt_context()
