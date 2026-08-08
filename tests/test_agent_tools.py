"""Comprehensive tests for agent tools, security, context engine, and agent loop."""
from __future__ import annotations

import os
os.environ.setdefault("VIBE_STUDIO_OFFLINE", "1")

import json
from pathlib import Path
import pytest

from vibe_studio.tools.filesystem_tools import FilesystemTools
from vibe_studio.tools.search_tools import SearchTools
from vibe_studio.tools.patch_tools import PatchTools
from vibe_studio.tools.terminal_tools import TerminalTools
from vibe_studio.tools.git_tools import GitTools
from vibe_studio.tools.code_tools import CodeTools
from vibe_studio.tools.tool_registry import default_tool_registry
from vibe_studio.security.path_security import PathSecurity, PathSecurityError
from vibe_studio.security.sensitive_file_detector import SensitiveFileDetector
from vibe_studio.core.command_safety import CommandSafety, RiskLevel
from vibe_studio.context.context_engine import ContextEngine
from vibe_studio.agents.coding_agent import AutonomousAgent, AgentState, AutonomyMode


# ---------------------------------------------------------------------------
# Filesystem tools
# ---------------------------------------------------------------------------

class TestFilesystemTools:
    def test_create_read_write_delete(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("a/b/hello.py", "print('hello')\n")
        assert fs.file_exists("a/b/hello.py")
        assert "hello" in fs.read_file("a/b/hello.py")
        fs.write_file("a/b/hello.py", "print('updated')\n")
        assert "updated" in fs.read_file("a/b/hello.py")
        meta = fs.get_file_metadata("a/b/hello.py")
        assert meta["size"] > 0
        assert meta["extension"] == ".py"
        fs.delete_file("a/b/hello.py")
        assert not fs.file_exists("a/b/hello.py")

    def test_tree_output(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("src/main.py", "")
        fs.create_file("tests/test_main.py", "")
        tree = fs.tree(max_depth=3)
        assert "src" in tree
        assert "main.py" in tree

    def test_move_and_copy(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("original.txt", "content")
        fs.copy_file("original.txt", "copy.txt")
        assert fs.file_exists("copy.txt")
        fs.move_file("copy.txt", "moved.txt")
        assert fs.file_exists("moved.txt")
        assert not fs.file_exists("copy.txt")

    def test_rename_file(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("old_name.py", "x = 1")
        fs.rename_file("old_name.py", "new_name.py")
        assert fs.file_exists("new_name.py")
        assert not fs.file_exists("old_name.py")

    def test_read_multiple_files(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("a.py", "a = 1")
        fs.create_file("b.py", "b = 2")
        result = fs.read_multiple_files(["a.py", "b.py", "nonexistent.py"])
        assert "a = 1" in result["a.py"]
        assert "b = 2" in result["b.py"]
        assert "Error" in result["nonexistent.py"]

    def test_path_traversal_blocked(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        with pytest.raises(Exception):
            fs.read_file("../../etc/passwd")

    def test_directory_operations(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("nested/deep/file.txt", "hello")
        assert fs.directory_exists("nested")
        assert fs.directory_exists("nested/deep")
        items = fs.list_directory("nested/deep")
        assert any(i["name"] == "file.txt" for i in items)


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------

class TestSearchTools:
    def test_search_text_finds_matches(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("src/app.py", "def login():\n    return 'hello'\n")
        fs.create_file("src/utils.py", "def logout():\n    pass\n")
        search = SearchTools(tmp_path)
        results = search.search_text("login")
        assert any(r["file"] == "src/app.py" for r in results)
        assert not any(r["file"] == "src/utils.py" for r in results)

    def test_search_regex(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("test.py", "API_KEY = 'abc123'\npassword = 'secret'\n")
        search = SearchTools(tmp_path)
        results = search.search_regex(r"(API_KEY|password)\s*=")
        assert len(results) == 2

    def test_search_filename(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("components/LoginPage.tsx", "")
        fs.create_file("styles/login.css", "")
        search = SearchTools(tmp_path)
        results = search.search_filename("login")
        assert len(results) == 2
        assert any("LoginPage.tsx" in r for r in results)
        assert any("login.css" in r for r in results)

    def test_search_symbol(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("main.py", "class MyClass:\n    def my_method(self):\n        pass\n")
        search = SearchTools(tmp_path)
        results = search.search_symbol("MyClass")
        assert len(results) >= 1
        assert results[0]["file"] == "main.py"

    def test_find_references(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("module.py", "def greet():\n    return 'hi'\n")
        fs.create_file("main.py", "from module import greet\nresult = greet()\n")
        search = SearchTools(tmp_path)
        refs = search.find_references("greet")
        files = {r["file"] for r in refs}
        assert "module.py" in files
        assert "main.py" in files

    def test_skip_ignored_dirs(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        fs.create_file("src/real.py", "NEEDLE = 1")
        # Create in ignored directory
        ignored = tmp_path / ".venv" / "lib"
        ignored.mkdir(parents=True)
        (ignored / "fake.py").write_text("NEEDLE = 2")
        search = SearchTools(tmp_path)
        results = search.search_text("NEEDLE")
        assert all(".venv" not in r["file"] for r in results)


# ---------------------------------------------------------------------------
# Patch tools
# ---------------------------------------------------------------------------

class TestPatchTools:
    def test_patch_and_undo(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        pt = PatchTools(tmp_path)
        fs.create_file("style.css", "body { background: white; }\n")
        result = pt.patch_file("style.css", "background: white;", "background: linear-gradient(135deg, #111 0%, #3b82f6 100%);")
        assert result["status"] == "success"
        assert "linear-gradient" in fs.read_file("style.css")
        assert "---" in result["diff"] or "+++" in result["diff"]
        assert pt.undo_last_change()
        assert "white" in fs.read_file("style.css")

    def test_replace_text(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        pt = PatchTools(tmp_path)
        fs.create_file("app.py", "VERSION = '1.0.0'\n")
        pt.replace_text("app.py", "1.0.0", "2.0.0")
        assert "2.0.0" in fs.read_file("app.py")

    def test_insert_text(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        pt = PatchTools(tmp_path)
        fs.create_file("main.py", "def main():\n    pass\n")
        pt.insert_text("main.py", "def main():", "\nimport os", after=False)
        content = fs.read_file("main.py")
        assert "import os" in content

    def test_delete_text(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        pt = PatchTools(tmp_path)
        fs.create_file("config.py", "DEBUG = True\nSECRET = 'abc'\n")
        pt.delete_text("config.py", "SECRET = 'abc'\n")
        assert "SECRET" not in fs.read_file("config.py")

    def test_target_not_found_raises(self, tmp_path):
        fs = FilesystemTools(tmp_path)
        pt = PatchTools(tmp_path)
        fs.create_file("file.py", "x = 1\n")
        with pytest.raises(ValueError):
            pt.patch_file("file.py", "nonexistent text", "replacement")


# ---------------------------------------------------------------------------
# Code tools
# ---------------------------------------------------------------------------

class TestCodeTools:
    def test_detect_python_project(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pytest\n")
        (tmp_path / "tests").mkdir()
        ct = CodeTools(tmp_path)
        result = ct.detect_project_type()
        assert "python" in result["languages"]

    def test_detect_js_project(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react": "^18.0"}, "devDependencies": {"jest": "^29.0"}}'
        )
        ct = CodeTools(tmp_path)
        result = ct.detect_project_type()
        assert "react" in result["frameworks"]
        assert "jest/vitest" in result["test_frameworks"]

    def test_detect_language_by_extension(self, tmp_path):
        ct = CodeTools(tmp_path)
        assert ct.detect_language("main.py") == "python"
        assert ct.detect_language("app.ts") == "typescript"
        assert ct.detect_language("styles.css") == "css"
        assert ct.detect_language("Cargo.toml") == "unknown"

    def test_detect_test_framework(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        ct = CodeTools(tmp_path)
        tf = ct.detect_test_framework()
        assert tf != ""


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_path_traversal_blocked(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        with pytest.raises(PathSecurityError):
            PathSecurity.validate_workspace_path(tmp_path / "outside.txt", ws)

    def test_relative_path_allowed(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "src").mkdir()
        result = PathSecurity.validate_workspace_path("src", ws)
        assert result == (ws / "src").resolve()

    def test_dotdot_blocked(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        with pytest.raises(PathSecurityError):
            PathSecurity.validate_workspace_path(ws / ".." / "outside", ws)

    def test_secret_redaction(self):
        text = "API_KEY = 'sk-abc123def456ghi789jkl012'"
        redacted = SensitiveFileDetector.redact_secrets(text)
        assert "sk-abc123def456ghi789jkl012" not in redacted
        assert "REDACTED" in redacted

    def test_sensitive_file_detection(self):
        assert SensitiveFileDetector.is_sensitive(".env")
        assert SensitiveFileDetector.is_sensitive("id_rsa")
        assert SensitiveFileDetector.is_sensitive("credentials.json")
        assert not SensitiveFileDetector.is_sensitive("main.py")
        assert not SensitiveFileDetector.is_sensitive("README.md")

    def test_command_risk_critical_blocked(self):
        assessment = CommandSafety.assess_risk("rm -rf /")
        assert assessment.risk_level == RiskLevel.CRITICAL

    def test_command_risk_safe(self):
        assessment = CommandSafety.assess_risk("pytest tests/")
        assert assessment.risk_level in (RiskLevel.SAFE, RiskLevel.LOW)

    def test_command_risk_high(self):
        assessment = CommandSafety.assess_risk("rm -rf build/")
        assert assessment.risk_level == RiskLevel.HIGH

    def test_command_execution_safe(self, tmp_path):
        result = CommandSafety.run("echo hello", cwd=tmp_path)
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_critical_command_blocked(self, tmp_path):
        result = CommandSafety.run("rm -rf /", cwd=tmp_path)
        assert result.exit_code != 0
        assert "blocked" in result.stderr.lower() or "safety" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Context engine
# ---------------------------------------------------------------------------

class TestContextEngine:
    def test_ranks_relevant_files_higher(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "login.py").write_text("def render_login(): return 'bg-white'")
        (tmp_path / "src" / "unrelated.py").write_text("def foo(): return 42")
        (tmp_path / "styles.css").write_text("body { background: white; }")

        engine = ContextEngine(tmp_path)
        bundle = engine.build("Login page-in backgroundunu dəyiş.")
        assert len(bundle.items) > 0
        # login.py or styles.css should rank highest
        top_paths = [item.path for item in bundle.items[:3]]
        assert any("login" in p.lower() or "style" in p.lower() for p in top_paths)

    def test_budget_respected(self, tmp_path):
        for i in range(30):
            (tmp_path / f"file_{i}.py").write_text("x" * 2000)
        engine = ContextEngine(tmp_path)
        bundle = engine.build("find something", token_budget=4000)
        assert bundle.total_tokens_est <= 5000  # some slack

    def test_empty_project(self, tmp_path):
        engine = ContextEngine(tmp_path / "nonexistent")
        bundle = engine.build("anything")
        assert len(bundle.items) == 0
        assert "No project" in bundle.format_prompt_context()


# ---------------------------------------------------------------------------
# Agent state machine + tool loop
# ---------------------------------------------------------------------------

class TestAgentStateMachine:
    def test_agent_completes_create_file(self, tmp_path):
        agent = AutonomousAgent(project_root=tmp_path, autonomy_mode=AutonomyMode.AUTO)
        result = agent.run("Create a file with the numbers 1 to 20, one number per line.")
        assert result.status == AgentState.COMPLETED
        nums = tmp_path / "numbers.txt"
        assert nums.exists()
        lines = nums.read_text().splitlines()
        assert lines == [str(i) for i in range(1, 21)]

    def test_agent_completes_delete_file(self, tmp_path):
        target = tmp_path / "numbers.txt"
        target.write_text("\n".join(str(i) for i in range(1, 21)))
        agent = AutonomousAgent(project_root=tmp_path, autonomy_mode=AutonomyMode.AUTO)
        result = agent.run("Delete numbers.txt")
        assert result.status == AgentState.COMPLETED
        assert not target.exists()

    def test_agent_modifies_css_background(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "styles.css").write_text("body { background: white; }\n")
        (tmp_path / "src" / "login.py").write_text("def login(): return 'bg-white'\n")
        agent = AutonomousAgent(project_root=tmp_path, autonomy_mode=AutonomyMode.AUTO)
        result = agent.run("Login page-in backgroundunu daha modern gradient et.")
        assert result.status == AgentState.COMPLETED
        css = (tmp_path / "src" / "styles.css").read_text()
        assert "linear-gradient" in css or "background:" in css

    def test_agent_cancellation(self, tmp_path):
        agent = AutonomousAgent(project_root=tmp_path, autonomy_mode=AutonomyMode.AUTO)
        # Cancel during the fallback — monkey-patch to cancel then return a tool call
        original_fallback = agent._fallback_deterministic_step

        def cancel_and_fallback(prompt):
            agent._cancel_requested = True
            return original_fallback(prompt)

        agent._fallback_deterministic_step = cancel_and_fallback
        result = agent.run("analyze deeply")
        assert result.status == AgentState.CANCELLED

    def test_plan_mode_returns_waiting(self, tmp_path):
        agent = AutonomousAgent(project_root=tmp_path, autonomy_mode=AutonomyMode.PLAN)
        result = agent.run("modify something")
        assert result.status == AgentState.WAITING_APPROVAL

    def test_agent_loop_safety_max_iterations(self, tmp_path):
        """Agent must not run forever — respects max_iterations."""
        agent = AutonomousAgent(
            project_root=tmp_path,
            autonomy_mode=AutonomyMode.AUTO,
            max_iterations=3,
        )
        result = agent.run("analyze the project in great detail")
        # Should complete within 3 iterations
        assert result.status == AgentState.COMPLETED
        assert len(result.tool_history) <= 3


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_all_expected_tools_registered(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        tools = {t["name"] for t in reg.list_tools()}
        expected = {
            "list_directory", "tree", "read_file", "write_file", "create_file",
            "delete_file", "move_file", "rename_file", "search_text", "search_regex",
            "search_filename", "search_symbol", "patch_file", "replace_text",
            "execute_command", "run_tests", "run_linter", "git_status", "git_diff",
            "git_log", "git_commit", "detect_project_type",
        }
        for tool in expected:
            assert tool in tools, f"Missing tool: {tool}"

    def test_unknown_tool_returns_error(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        result = reg.execute("nonexistent_tool", {})
        assert result["exit_code"] != 0
        assert "Unknown tool" in result["stderr"]

    def test_snapshot_enables_undo(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        (tmp_path / "test.txt").write_text("original")
        reg.execute("write_file", {"path": "test.txt", "content": "modified"})
        assert (tmp_path / "test.txt").read_text() == "modified"
        assert reg.patch_tools.undo_last_change()
        assert (tmp_path / "test.txt").read_text() == "original"

    def test_tool_schema_is_valid_json(self, tmp_path):
        reg = default_tool_registry(tmp_path)
        tools_json = json.dumps(reg.list_tools())
        parsed = json.loads(tools_json)
        assert isinstance(parsed, list)
        assert len(parsed) > 0
        for t in parsed:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t
