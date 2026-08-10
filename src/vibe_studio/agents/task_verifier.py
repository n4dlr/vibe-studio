"""TaskVerificationEngine — Deterministic verification of AI agent task completion.

Core Principle:
"NEVER consider an AI task completed merely because the LLM claims that it completed the task."

Verifies:
  1. Filesystem state (file creation, modification, deletion, unexpected edits)
  2. Symbol existence via AST (functions, classes, methods, variables)
  3. Textual / behavioral assertions (regex, expected sub-strings)
  4. Test suite execution (exit code 0, non-zero test execution)
  5. Syntax validation (compilation / parse check)
  6. Git / patch diff inspection

Result Tiers:
  - COMPLETED              : 100% requirements and tests passed.
  - COMPLETED_WITH_WARNINGS: Core requirements passed, minor non-critical warnings.
  - PARTIAL                : Some requirements met, others missing/failing.
  - FAILED                 : Test or critical requirement failed.
  - BLOCKED                : Unrecoverable error or max retries reached.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status Enum
# ---------------------------------------------------------------------------

class VerificationStatus(str, Enum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Task Requirements Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FileRequirement:
    path: str
    must_exist: bool = True
    must_not_exist: bool = False
    min_size_bytes: int = 1
    expected_content_pattern: str | None = None


@dataclass
class SymbolRequirement:
    path: str
    symbol_name: str
    symbol_type: str = "any"  # "function" | "class" | "variable" | "any"


@dataclass
class BehaviorRequirement:
    description: str
    check_type: str  # "regex" | "contains" | "custom"
    pattern_or_code: str
    target_file: str | None = None


@dataclass
class TestRequirement:
    verification_command: str | None = None
    expected_exit_code: int = 0
    require_tests_executed: bool = True
    target_path: str | None = None


@dataclass
class TaskRequirement:
    prompt: str
    files: list[FileRequirement] = field(default_factory=list)
    symbols: list[SymbolRequirement] = field(default_factory=list)
    behaviors: list[BehaviorRequirement] = field(default_factory=list)
    tests: list[TestRequirement] = field(default_factory=list)
    allow_unexpected_file_changes: bool = True


@dataclass
class VerificationCheckResult:
    check_type: str
    name: str
    passed: bool
    message: str
    severity: str = "error"  # "error" | "warning" | "info"


@dataclass
class VerificationResult:
    status: VerificationStatus
    score: float  # 0.0 to 100.0
    checks: list[VerificationCheckResult] = field(default_factory=list)
    summary: str = ""
    files_verified: list[str] = field(default_factory=list)
    unexpected_files_modified: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.status in (VerificationStatus.COMPLETED, VerificationStatus.COMPLETED_WITH_WARNINGS)


# ---------------------------------------------------------------------------
# TaskVerificationEngine
# ---------------------------------------------------------------------------

class TaskVerificationEngine:
    """Engine for verifying agent work against actual filesystem and execution state."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()

    def verify(
        self,
        requirement: TaskRequirement,
        reported_files_changed: list[str] | None = None,
        test_result: dict[str, Any] | None = None,
        git_diff_files: list[str] | None = None,
    ) -> VerificationResult:
        """Run full deterministic verification pass."""
        checks: list[VerificationCheckResult] = []
        files_verified: list[str] = []
        unexpected_files: list[str] = []

        # 1. File Requirements Verification
        for freq in requirement.files:
            file_pass, msg, sev = self._verify_file(freq)
            checks.append(VerificationCheckResult("file", f"File '{freq.path}'", file_pass, msg, sev))
            if file_pass:
                files_verified.append(freq.path)

        # 2. Symbol Requirements Verification
        for sreq in requirement.symbols:
            sym_pass, msg, sev = self._verify_symbol(sreq)
            checks.append(VerificationCheckResult("symbol", f"Symbol '{sreq.symbol_name}' in {sreq.path}", sym_pass, msg, sev))

        # 3. Behavior / Content Verification
        for breq in requirement.behaviors:
            beh_pass, msg, sev = self._verify_behavior(breq)
            checks.append(VerificationCheckResult("behavior", breq.description, beh_pass, msg, sev))

        # 4. Syntax Verification for all target files
        req_file_paths = {f.path for f in requirement.files}
        target_files = sorted(set(reported_files_changed or []) | req_file_paths | set(files_verified))
        for fpath in target_files:
            syn_pass, msg, sev = self._verify_syntax(fpath)
            if not syn_pass:
                checks.append(VerificationCheckResult("syntax", f"Syntax in '{fpath}'", False, msg, "error"))

        # 5. Test Suite Verification
        if test_result:
            test_pass, msg, sev = self._verify_test_result(test_result, requirement.tests)
            checks.append(VerificationCheckResult("test", "Test Suite Validation", test_pass, msg, sev))
        elif requirement.tests:
            for treq in requirement.tests:
                checks.append(VerificationCheckResult("test", f"Test check for {treq.target_path or 'project'}", False, "Tests were required but not executed", "error"))

        # 6. Unexpected changes check
        if git_diff_files and reported_files_changed is not None:
            expected_set = set(reported_files_changed) | {f.path for f in requirement.files}
            for diff_f in git_diff_files:
                if diff_f not in expected_set and not diff_f.startswith(".vibe_studio/"):
                    unexpected_files.append(diff_f)

            if unexpected_files and not requirement.allow_unexpected_file_changes:
                checks.append(VerificationCheckResult(
                    "unexpected_edits", "Workspace Integrity", False,
                    f"Unexpected modified files detected: {', '.join(unexpected_files)}", "warning"
                ))

        # Determine Final Status and Score
        return self._compute_final_status(checks, files_verified, unexpected_files)

    # ------------------------------------------------------------------
    # Individual Verification Pass Helpers
    # ------------------------------------------------------------------

    def _verify_file(self, freq: FileRequirement) -> tuple[bool, str, str]:
        target = (self.workspace_root / freq.path).resolve()

        if freq.must_not_exist:
            if target.exists():
                return False, f"File '{freq.path}' was expected to be deleted, but still exists.", "error"
            return True, f"File '{freq.path}' successfully removed.", "info"

        if not target.exists():
            return False, f"File '{freq.path}' does not exist on disk.", "error"

        if target.is_file():
            size = target.stat().st_size
            if size < freq.min_size_bytes:
                return False, f"File '{freq.path}' is empty or below required size ({size} < {freq.min_size_bytes} bytes).", "error"

            if freq.expected_content_pattern:
                try:
                    content = target.read_text(encoding="utf-8", errors="replace")
                    if not re.search(freq.expected_content_pattern, content):
                        return False, f"File '{freq.path}' content does not match expected pattern '{freq.expected_content_pattern}'.", "error"
                except Exception as exc:
                    return False, f"Could not read '{freq.path}': {exc}", "error"

        return True, f"File '{freq.path}' verified successfully.", "info"

    def _verify_symbol(self, sreq: SymbolRequirement) -> tuple[bool, str, str]:
        target = (self.workspace_root / sreq.path).resolve()
        if not target.exists():
            return False, f"File '{sreq.path}' does not exist for symbol verification.", "error"

        if target.suffix == ".py":
            try:
                tree = ast.parse(target.read_text(encoding="utf-8", errors="replace"))
                found_type = None
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == sreq.symbol_name:
                        found_type = "function"
                        break
                    elif isinstance(node, ast.AsyncFunctionDef) and node.name == sreq.symbol_name:
                        found_type = "function"
                        break
                    elif isinstance(node, ast.ClassDef) and node.name == sreq.symbol_name:
                        found_type = "class"
                        break
                    elif isinstance(node, ast.Name) and node.id == sreq.symbol_name:
                        found_type = "variable"

                if found_type:
                    if sreq.symbol_type != "any" and sreq.symbol_type != found_type:
                        return False, f"Symbol '{sreq.symbol_name}' found in '{sreq.path}', but is {found_type} instead of {sreq.symbol_type}.", "error"
                    return True, f"Symbol '{sreq.symbol_name}' ({found_type}) verified in '{sreq.path}'.", "info"
                return False, f"Symbol '{sreq.symbol_name}' not found in AST of '{sreq.path}'.", "error"
            except Exception as exc:
                return False, f"AST parsing failed for '{sreq.path}': {exc}", "error"

        # Non-python fallback: regex symbol check
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            pattern = rf"\b{re.escape(sreq.symbol_name)}\b"
            if re.search(pattern, content):
                return True, f"Symbol '{sreq.symbol_name}' pattern matched in '{sreq.path}'.", "info"
            return False, f"Symbol '{sreq.symbol_name}' pattern not found in '{sreq.path}'.", "error"
        except Exception as exc:
            return False, f"Could not read '{sreq.path}': {exc}", "error"

    def _verify_behavior(self, breq: BehaviorRequirement) -> tuple[bool, str, str]:
        if breq.target_file:
            target = (self.workspace_root / breq.target_file).resolve()
            if not target.exists():
                return False, f"Target file '{breq.target_file}' for behavior check does not exist.", "error"
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                return False, f"Could not read '{breq.target_file}': {exc}", "error"
        else:
            content = ""

        if breq.check_type == "contains":
            if breq.pattern_or_code in content:
                return True, f"Behavior '{breq.description}' verified.", "info"
            return False, f"Behavior check failed: expected '{breq.pattern_or_code}' in content.", "error"

        elif breq.check_type == "regex":
            if re.search(breq.pattern_or_code, content):
                return True, f"Behavior '{breq.description}' verified.", "info"
            return False, f"Behavior check failed: regex '{breq.pattern_or_code}' did not match.", "error"

        return True, f"Behavior '{breq.description}' passed.", "info"

    def _verify_syntax(self, fpath: str) -> tuple[bool, str, str]:
        target = (self.workspace_root / fpath).resolve()
        if not target.exists() or not target.is_file():
            return True, "File removed or non-existent, syntax check skipped.", "info"

        if target.suffix == ".py":
            try:
                py_code = target.read_text(encoding="utf-8", errors="replace")
                ast.parse(py_code, filename=str(target))
                return True, f"Syntax OK for '{fpath}'.", "info"
            except SyntaxError as syn_err:
                return False, f"Syntax error in '{fpath}' line {syn_err.lineno}: {syn_err.msg}", "error"
            except Exception as exc:
                return False, f"Could not parse '{fpath}': {exc}", "error"

        elif target.suffix in (".json",):
            import json
            try:
                json.loads(target.read_text(encoding="utf-8", errors="replace"))
                return True, f"JSON syntax OK for '{fpath}'.", "info"
            except Exception as exc:
                return False, f"Invalid JSON in '{fpath}': {exc}", "error"

        return True, f"Syntax check for '{fpath}' skipped (non-parsed extension).", "info"

    def _verify_test_result(
        self,
        test_result: dict[str, Any],
        test_reqs: list[TestRequirement],
    ) -> tuple[bool, str, str]:
        exit_code = test_result.get("exit_code", 0)
        stdout = test_result.get("stdout", "")
        stderr = test_result.get("stderr", "")

        if exit_code != 0:
            err_snip = (stderr or stdout)[:200].replace("\n", " ")
            return False, f"Test suite failed with exit code {exit_code}: {err_snip}", "error"

        # Check if 0 tests ran (e.g. "NO TESTS RAN" or 0 collected)
        combined = (stdout + stderr).lower()
        if "no tests ran" in combined or "0 items collected" in combined or "collected 0 items" in combined:
            return False, "Test suite finished with exit code 0, but ZERO tests were executed.", "error"

        return True, "Test suite passed successfully.", "info"

    def _compute_final_status(
        self,
        checks: list[VerificationCheckResult],
        files_verified: list[str],
        unexpected_files: list[str],
    ) -> VerificationResult:
        if not checks:
            return VerificationResult(
                status=VerificationStatus.COMPLETED,
                score=100.0,
                checks=[],
                summary="No explicit checks required. Execution completed clean.",
                files_verified=files_verified,
                unexpected_files_modified=unexpected_files,
            )

        errors = [c for c in checks if not c.passed and c.severity == "error"]
        warnings = [c for c in checks if not c.passed and c.severity == "warning"]
        passed_count = sum(1 for c in checks if c.passed)
        total_count = len(checks)
        score = round((passed_count / total_count) * 100.0, 1)

        critical_errors = [c for c in errors if c.check_type in ("syntax", "test") or len(errors) == total_count]
        if not errors and not warnings:
            status = VerificationStatus.COMPLETED
            summary = f"All {total_count} verification checks passed (100%)."
        elif not errors and warnings:
            status = VerificationStatus.COMPLETED_WITH_WARNINGS
            summary = f"Passed {passed_count}/{total_count} checks with {len(warnings)} warning(s)."
        elif critical_errors:
            status = VerificationStatus.FAILED
            summary = f"Verification failed ({critical_errors[0].check_type}): {critical_errors[0].message}"
        elif passed_count > 0 and errors:
            status = VerificationStatus.PARTIAL
            summary = f"Partial success: {passed_count}/{total_count} checks passed ({score}%). Errors: {errors[0].message}"
        else:
            status = VerificationStatus.FAILED
            summary = f"Verification failed: {errors[0].message}"

        return VerificationResult(
            status=status,
            score=score,
            checks=checks,
            summary=summary,
            files_verified=files_verified,
            unexpected_files_modified=unexpected_files,
        )
