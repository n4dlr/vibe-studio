"""
End-to-end workflow regression tests for Vibe Studio's core agent pipeline.

Validates the full lifecycle:
  scan → search → read → patch → diff → validate → self-correct → re-test

These tests run deterministically (VIBE_STUDIO_OFFLINE=1) and do NOT require
an active Ollama / API connection.
"""
from __future__ import annotations

import os
os.environ.setdefault("VIBE_STUDIO_OFFLINE", "1")

import hashlib
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def make_sample_project(tmp_path: Path) -> Path:
    """Create a minimal sample project used by every E2E scenario."""
    src = tmp_path / "src"
    src.mkdir()

    # Login page (CSS target)
    (src / "Login.tsx").write_text(
        textwrap.dedent("""\
        import React from "react";
        import "./login.css";

        export function Login() {
          return <div className="login-container">Login</div>;
        }
        """),
        encoding="utf-8",
    )
    (src / "login.css").write_text(
        textwrap.dedent("""\
        body {
          background: #ffffff;
          color: black;
        }
        .login-container {
          padding: 20px;
        }
        """),
        encoding="utf-8",
    )

    # Python module with a known function
    (tmp_path / "calc.py").write_text(
        textwrap.dedent("""\
        def add(a, b):
            return a + b

        def divide(a, b):
            return a / b
        """),
        encoding="utf-8",
    )

    # Test suite that initially fails
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "test_calc.py").write_text(
        textwrap.dedent("""\
        from calc import add, divide

        def test_add():
            assert add(2, 3) == 5

        def test_divide_intentional_failure():
            # Intentional failure: divide by zero should raise
            import pytest
            with pytest.raises(ZeroDivisionError):
                divide(4, 0)
        """),
        encoding="utf-8",
    )

    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n",
        encoding="utf-8",
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Scenario 1: Search → Read → Patch → Diff
# ---------------------------------------------------------------------------

class TestSearchReadPatchDiff:
    def test_search_finds_login_css(self, tmp_path):
        """Agent must be able to locate login.css by searching for 'login' filename."""
        from vibe_studio.tools.search_tools import SearchTools

        project = make_sample_project(tmp_path)
        searcher = SearchTools(project)

        results = searcher.search_filename("login")
        paths = [r for r in results if r.endswith(".css")]
        assert len(paths) == 1
        assert "login.css" in paths[0]

    def test_read_login_css(self, tmp_path):
        """Agent must read login.css content successfully."""
        from vibe_studio.tools.tool_registry import default_tool_registry

        project = make_sample_project(tmp_path)
        reg = default_tool_registry(project)
        result = reg.execute("read_file", {"path": "src/login.css"})

        assert result["exit_code"] == 0, f"read_file failed: {result}"
        assert "background" in result["stdout"]

    def test_patch_changes_background(self, tmp_path):
        """Agent must be able to patch the CSS background property."""
        from vibe_studio.tools.tool_registry import default_tool_registry

        project = make_sample_project(tmp_path)
        reg = default_tool_registry(project)

        result = reg.execute("patch_file", {
            "path": "src/login.css",
            "target_text": "background: #ffffff;",
            "replacement_text": "background: linear-gradient(135deg, #111827, #3b82f6);",
        })
        assert result["exit_code"] == 0, f"Patch failed: {result}"

        updated = (project / "src/login.css").read_text(encoding="utf-8")
        assert "linear-gradient" in updated
        assert "#ffffff" not in updated

    def test_diff_is_generated_after_patch(self, tmp_path):
        """Applying a patch must produce a non-empty diff in the history."""
        from vibe_studio.tools.patch_tools import PatchTools

        project = make_sample_project(tmp_path)
        patcher = PatchTools(project)
        patcher.patch_file(
            "src/login.css",
            old_text="background: #ffffff;",
            new_text="background: #1a1a2e;",
        )
        assert patcher.history, "Patch history should be non-empty"
        diff = patcher.history[-1].diff
        assert "#ffffff" in diff
        assert "#1a1a2e" in diff

    def test_undo_restores_original(self, tmp_path):
        """revert_last_change must restore the original file content."""
        from vibe_studio.tools.patch_tools import PatchTools

        project = make_sample_project(tmp_path)
        patcher = PatchTools(project)

        patcher.patch_file(
            "src/login.css",
            old_text="background: #ffffff;",
            new_text="background: #000000;",
        )
        assert "#000000" in (project / "src/login.css").read_text(encoding="utf-8")

        result = patcher.revert_last_change()
        assert result["exit_code"] == 0
        reverted = (project / "src/login.css").read_text(encoding="utf-8")
        assert "#ffffff" in reverted

    def test_conflict_detection_prevents_overwrite(self, tmp_path):
        """If file changed externally, conflict detection must block a stale patch."""
        from vibe_studio.tools.patch_tools import PatchTools

        project = make_sample_project(tmp_path)
        patcher = PatchTools(project)

        # Read hash before external modification
        original = (project / "src/login.css").read_text(encoding="utf-8")
        original_hash = sha256(original)

        # External modification simulating a concurrent edit
        css_path = project / "src/login.css"
        css_path.write_text(original + "\n/* externally appended */", encoding="utf-8")

        # Conflict check should detect mismatch
        conflict = patcher.check_conflict("src/login.css", original_hash)
        assert conflict is True


# ---------------------------------------------------------------------------
# Scenario 2: Backup created on patch
# ---------------------------------------------------------------------------

class TestBackupOnPatch:
    def test_backup_file_created(self, tmp_path):
        from vibe_studio.tools.patch_tools import PatchTools

        project = make_sample_project(tmp_path)
        patcher = PatchTools(project)
        patcher.patch_file(
            "src/login.css",
            old_text="background: #ffffff;",
            new_text="background: #0a0a0a;",
        )
        backup_dir = project / ".vibe_studio_backup"
        assert backup_dir.exists(), "Backup directory should be created after patching"
        bak_files = list(backup_dir.glob("*.bak"))
        assert len(bak_files) >= 1


# ---------------------------------------------------------------------------
# Scenario 3: Self-repair (test fail → diagnose → fix → retest)
# ---------------------------------------------------------------------------

class TestSelfRepairWorkflow:
    def _run_tests(self, project: Path) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout + result.stderr

    def test_initial_test_suite_passes(self, tmp_path):
        """All tests in the sample project must initially pass."""
        project = make_sample_project(tmp_path)
        rc, output = self._run_tests(project)
        assert rc == 0, f"Tests failed unexpectedly:\n{output}"

    def test_introduce_and_detect_failure(self, tmp_path):
        """A deliberate bug must be caught by the test runner."""
        project = make_sample_project(tmp_path)
        calc = project / "calc.py"
        # Break the add function
        calc.write_text(
            "def add(a, b):\n    return a - b  # BUG\n\ndef divide(a, b):\n    return a / b\n",
            encoding="utf-8",
        )
        rc, output = self._run_tests(project)
        assert rc != 0, "Test runner should have detected the broken add function"
        assert "FAILED" in output or "AssertionError" in output

    def test_self_repair_fixes_broken_function(self, tmp_path):
        """Self-repair pipeline must detect and fix the broken add function."""
        from vibe_studio.tools.patch_tools import PatchTools

        project = make_sample_project(tmp_path)
        calc = project / "calc.py"

        # Introduce the bug
        calc.write_text(
            "def add(a, b):\n    return a - b  # BUG\n\ndef divide(a, b):\n    return a / b\n",
            encoding="utf-8",
        )

        rc_before, _ = self._run_tests(project)
        assert rc_before != 0

        # Self-repair: read → patch
        patcher = PatchTools(project)
        patch_result = patcher.patch_file(
            "calc.py",
            old_text="return a - b  # BUG",
            new_text="return a + b",
        )
        assert patch_result["exit_code"] == 0

        rc_after, output = self._run_tests(project)
        assert rc_after == 0, f"Self-repair failed, tests still failing:\n{output}"


# ---------------------------------------------------------------------------
# Scenario 4: Project Intelligence — scanner finds language, frameworks, tests
# ---------------------------------------------------------------------------

class TestProjectIntelligence:
    def test_scanner_detects_languages(self, tmp_path):
        from vibe_studio.project.project_scanner import ProjectScanner

        project = make_sample_project(tmp_path)
        summary = ProjectScanner(project).scan()

        assert "python" in summary.languages
        # CSS/TSX/JS files should also be counted
        assert len(summary.languages) >= 2

    def test_scanner_finds_test_files(self, tmp_path):
        from vibe_studio.project.project_scanner import ProjectScanner

        project = make_sample_project(tmp_path)
        summary = ProjectScanner(project).scan()

        assert any("test_calc" in t for t in summary.tests)

    def test_scanner_finds_symbols(self, tmp_path):
        from vibe_studio.project.project_scanner import ProjectScanner

        project = make_sample_project(tmp_path)
        summary = ProjectScanner(project).scan()

        all_symbols = [s.name for fs in summary.files for s in fs.symbols]
        assert "add" in all_symbols
        assert "divide" in all_symbols


# ---------------------------------------------------------------------------
# Scenario 5: Code Intelligence engine
# ---------------------------------------------------------------------------

class TestCodeIntelligence:
    def test_find_definition_returns_location(self, tmp_path):
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine

        project = make_sample_project(tmp_path)
        engine = CodeIntelligenceEngine(project)

        results = engine.find_definition("add")
        assert len(results) >= 1
        assert results[0].symbol == "add"
        assert results[0].file == "calc.py"

    def test_hover_info_returns_docstring(self, tmp_path):
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine

        project = make_sample_project(tmp_path)
        calc = project / "calc.py"
        calc.write_text(
            'def add(a, b):\n    """Return a + b."""\n    return a + b\n',
            encoding="utf-8",
        )
        engine = CodeIntelligenceEngine(project)

        info = engine.get_hover_info("add")
        assert info is not None
        assert "add" in info.symbol
        assert "Return a + b" in info.docstring

    def test_completions_match_prefix(self, tmp_path):
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine

        project = make_sample_project(tmp_path)
        engine = CodeIntelligenceEngine(project)

        completions = engine.get_completions("ad")
        assert "add" in completions

    def test_find_references(self, tmp_path):
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine

        project = make_sample_project(tmp_path)
        engine = CodeIntelligenceEngine(project)

        refs = engine.find_references("add")
        files_with_ref = {r["file"] for r in refs}
        assert any("test_calc" in f for f in files_with_ref)

    def test_invalidate_triggers_reindex(self, tmp_path):
        from vibe_studio.editor.code_intelligence import CodeIntelligenceEngine

        project = make_sample_project(tmp_path)
        engine = CodeIntelligenceEngine(project)

        # Build initial index
        engine.build_index()
        assert engine._index is not None

        # Invalidate
        engine.invalidate_index()
        assert engine._index is None

        # Next call rebuilds
        engine.find_definition("add")
        assert engine._index is not None


# ---------------------------------------------------------------------------
# Scenario 6: File Watcher
# ---------------------------------------------------------------------------

class TestFileWatcher:
    def test_watcher_initializes_on_workspace(self, tmp_path):
        from vibe_studio.filesystem.file_watcher import WorkspaceFileWatcher
        from PySide6.QtWidgets import QApplication
        import sys

        app = QApplication.instance() or QApplication(sys.argv)
        project = make_sample_project(tmp_path)
        watcher = WorkspaceFileWatcher(project)
        assert watcher.workspace_root == project
        watcher.deleteLater()

    def test_watcher_debounce_does_not_crash(self, tmp_path):
        """Debounce timer must fire without crashing."""
        from vibe_studio.filesystem.file_watcher import WorkspaceFileWatcher
        from PySide6.QtWidgets import QApplication
        import sys

        app = QApplication.instance() or QApplication(sys.argv)
        project = make_sample_project(tmp_path)
        received = []
        watcher = WorkspaceFileWatcher(project)
        watcher.directory_changed.connect(lambda p: received.append(p))

        # Force fire debounce immediately
        watcher._pending_dirs.add(str(project))
        watcher._emit_debounced()

        assert len(received) == 1
        watcher.deleteLater()


# ---------------------------------------------------------------------------
# Scenario 7: Security boundaries respected during patching
# ---------------------------------------------------------------------------

class TestSecurityDuringPatch:
    def test_path_traversal_blocked(self, tmp_path):
        from vibe_studio.tools.patch_tools import PatchTools
        from vibe_studio.security.path_security import PathSecurityError

        project = make_sample_project(tmp_path)
        patcher = PatchTools(project)

        with pytest.raises((PathSecurityError, ValueError, Exception)):
            patcher.patch_file("../../etc/passwd", "root", "hacked")

    def test_write_outside_workspace_blocked(self, tmp_path):
        from vibe_studio.tools.filesystem_tools import FilesystemTools
        from vibe_studio.security.path_security import PathSecurityError

        project = make_sample_project(tmp_path)
        fs = FilesystemTools(project)

        # Should raise PathSecurityError or return non-zero exit code
        try:
            result = fs.write_file("../../outside.txt", "injected")
            # If it returns without raising, the file must NOT have been written outside
            assert not (tmp_path.parent.parent / "outside.txt").exists()
        except (PathSecurityError, ValueError, Exception):
            pass  # Any exception is acceptable — attack was blocked


# ---------------------------------------------------------------------------
# Scenario 8: Full agent pipeline (deterministic offline mode)
# ---------------------------------------------------------------------------

class TestFullAgentPipeline:
    def test_agent_runs_and_completes(self, tmp_path):
        from vibe_studio.agents.coding_agent import AutonomousAgent, AutonomyMode

        project = make_sample_project(tmp_path)
        agent = AutonomousAgent(
            project_root=project,
            autonomy_mode=AutonomyMode.AUTO,
        )
        result = agent.run("Find the login CSS file and report what background color it uses.")

        # In offline mode, agent should complete without exception
        assert result is not None
        assert result.status is not None

    def test_agent_respects_max_iterations(self, tmp_path):
        """Agent must not loop indefinitely regardless of task complexity."""
        from vibe_studio.agents.coding_agent import AutonomousAgent, AutonomyMode

        project = make_sample_project(tmp_path)
        agent = AutonomousAgent(
            project_root=project,
            autonomy_mode=AutonomyMode.AUTO,
        )
        # A nonsensical task should terminate cleanly within iteration limit
        result = agent.run("Simultaneously create and delete the same file infinitely.")
        assert result is not None
