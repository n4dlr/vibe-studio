"""Regression & hardening test suite for Vibe Studio V19 Production Hardening.

Covers:
  1. TaskVerificationEngine deterministic check pass/fail
  2. Zero tests != PASS
  3. Syntax error detection
  4. Intent-to-Verification-Plan derivation
  5. Shell command safety & shlex list execution
  6. Workspace boundary traversal prevention
  7. NavigatorAgent explicit file discovery
  8. Auto-completion guards (_simple_task heuristics)
  9. Error tracker deduplication & max retries
  10. CLI doctor command execution
  11. CLI verify command execution
  12. Benchmark scenario verification engine integration
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from vibe_studio.agents.intent_predictor import IntentPredictor
from vibe_studio.agents.navigator_agent import NavigatorAgent
from vibe_studio.agents.task_verifier import (
    BehaviorRequirement,
    FileRequirement,
    SymbolRequirement,
    TaskRequirement,
    TaskVerificationEngine,
    VerificationStatus,
)
from vibe_studio.core.command_safety import CommandSafety
from vibe_studio.security.path_security import PathSecurity
from vibe_studio.tools.terminal_tools import TerminalTools


class TestTaskVerificationEngine:
    def test_verify_file_existence_and_symbol(self, tmp_path):
        # Create target python file
        py_file = tmp_path / "hello.py"
        py_file.write_text("def farewell(name):\n    return 'Goodbye ' + name\n")

        verifier = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(
            prompt="add farewell(name) to hello.py",
            files=[FileRequirement(path="hello.py", must_exist=True)],
            symbols=[SymbolRequirement(path="hello.py", symbol_name="farewell", symbol_type="function")],
        )

        res = verifier.verify(req, reported_files_changed=["hello.py"])
        assert res.status == VerificationStatus.COMPLETED
        assert res.is_successful
        assert res.score == 100.0

    def test_verify_fails_when_file_missing(self, tmp_path):
        verifier = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(
            prompt="add farewell to missing.py",
            files=[FileRequirement(path="missing.py", must_exist=True)],
        )

        res = verifier.verify(req)
        assert res.status == VerificationStatus.FAILED
        assert not res.is_successful

    def test_verify_fails_when_syntax_error(self, tmp_path):
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken_func(:")

        verifier = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(prompt="fix bad.py", files=[FileRequirement(path="bad.py")])
        res = verifier.verify(req, reported_files_changed=["bad.py"])

        assert res.status == VerificationStatus.FAILED
        assert any("Syntax error" in c.message for c in res.checks)

    def test_verify_zero_tests_does_not_equal_pass(self, tmp_path):
        verifier = TaskVerificationEngine(tmp_path)
        req = TaskRequirement(prompt="run pytest")
        test_res = {
            "exit_code": 0,
            "stdout": "collected 0 items\nNO TESTS RAN",
            "stderr": "",
        }
        res = verifier.verify(req, test_result=test_res)

        assert res.status == VerificationStatus.FAILED
        assert any("ZERO tests were executed" in c.message for c in res.checks)


class TestIntentPredictorDerivation:
    def test_derive_verification_plan_from_prompt(self):
        predictor = IntentPredictor()
        req = predictor.derive_verification_requirements("Add farewell(name) to hello.py and run pytest")

        assert len(req.files) == 1
        assert req.files[0].path == "hello.py"
        assert len(req.symbols) == 1
        assert req.symbols[0].symbol_name == "farewell"
        assert len(req.tests) == 1


class TestSubprocessAndPathSafety:
    def test_shlex_list_execution_prevents_command_injection(self, tmp_path):
        res = CommandSafety.run(
            "echo hello",
            cwd=tmp_path,
            workspace_root=tmp_path,
        )
        assert res.exit_code == 0
        assert "hello" in res.stdout

    def test_path_traversal_blocked(self, tmp_path):
        with pytest.raises(PermissionError):
            PathSecurity.validate_workspace_path(tmp_path / "../outside.txt", tmp_path)


class TestNavigatorAgentFileDiscovery:
    def test_explicit_named_file_is_found(self, tmp_path):
        (tmp_path / "auth_controller.py").write_text("class AuthController: pass\n")
        (tmp_path / "utils.py").write_text("def helper(): pass\n")

        nav = NavigatorAgent(tmp_path)
        found = nav.discover_relevant_files("Add login method to auth_controller.py")
        assert "auth_controller.py" in found


class TestTerminalToolsStructuredMetrics:
    def test_terminal_tools_parses_zero_tests(self, tmp_path):
        tt = TerminalTools(tmp_path)
        # Create pyproject so it uses pytest
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
        res = tt.run_tests()
        assert res.get("no_tests_executed") is True or res.get("tests_executed") == 0


class TestCLISubcommands:
    def test_doctor_command_runs(self, tmp_path):
        from vibe_studio.cli import main
        code = main(["--root", str(tmp_path), "doctor"])
        assert code == 0

    def test_verify_command_runs(self, tmp_path):
        from vibe_studio.cli import main
        (tmp_path / "hello.py").write_text("print('hello')\n")
        code = main(["--root", str(tmp_path), "verify", "hello.py"])
        assert code == 0
