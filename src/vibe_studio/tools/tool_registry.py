"""
Tool registry — production-grade tool lifecycle management.

Every tool has:
  - name / description
  - input schema (for LLM prompt + validation)
  - risk level (SAFE / LOW / MEDIUM / HIGH)
  - execution handler
  - snapshot/undo support for file-mutating tools
  - structured result
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vibe_studio.tools.code_tools import CodeTools
from vibe_studio.tools.code_analysis_tools import CodeAnalysisTools
from vibe_studio.tools.filesystem_tools import FilesystemTools
from vibe_studio.tools.git_tools import GitTools
from vibe_studio.tools.patch_tools import PatchTools
from vibe_studio.tools.search_tools import SearchTools
from vibe_studio.tools.terminal_tools import TerminalTools


class RiskLevel(str, Enum):
    SAFE   = "SAFE"
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


@dataclass
class ToolParameter:
    type: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, ToolParameter]
    handler: Callable[..., Any]
    risk: RiskLevel = RiskLevel.LOW
    requires_permission: bool = False


class ToolRegistry:
    """Unified executable registry for all AI IDE agent tools."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root)
        self.fs_tools = FilesystemTools(self.workspace_root)
        self.search_tools = SearchTools(self.workspace_root)
        self.code_tools = CodeTools(self.workspace_root)
        self.patch_tools = PatchTools(self.workspace_root)
        self.terminal_tools = TerminalTools(self.workspace_root)
        self.git_tools = GitTools(self.workspace_root)
        self.code_analysis_tools = CodeAnalysisTools(self.workspace_root)
        self._tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, ToolParameter],
        handler: Callable[..., Any],
        risk: RiskLevel = RiskLevel.LOW,
        requires_permission: bool = False,
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            risk=risk,
            requires_permission=requires_permission,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """Return tools in OpenAI function-calling schema format."""
        result = []
        for name, tool in self._tools.items():
            properties: dict[str, Any] = {}
            required: list[str] = []
            for param_name, param in tool.parameters.items():
                properties[param_name] = {
                    "type": param.type,
                    "description": param.description,
                }
                if param.default is not None:
                    properties[param_name]["default"] = param.default
                if param.required:
                    required.append(param_name)
            result.append({
                "name": tool.name,
                "description": tool.description,
                "risk": tool.risk.value,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })
        return result

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    # ------------------------------------------------------------------
    # Argument coercion — fix common LLM type mistakes
    # ------------------------------------------------------------------

    def _coerce_args(self, tool: ToolDefinition, args: dict[str, Any]) -> dict[str, Any]:
        """
        Coerce arg types to match the parameter schema.
        Models sometimes pass "3" (string) for an integer parameter.
        """
        coerced: dict[str, Any] = {}
        for key, value in args.items():
            param = tool.parameters.get(key)
            if param is None:
                coerced[key] = value
                continue
            if param.type == "integer" and isinstance(value, str):
                try:
                    coerced[key] = int(value)
                    continue
                except ValueError:
                    pass
            if param.type == "number" and isinstance(value, str):
                try:
                    coerced[key] = float(value)
                    continue
                except ValueError:
                    pass
            if param.type == "boolean" and isinstance(value, str):
                coerced[key] = value.lower() in ("true", "1", "yes")
                continue
            if param.type == "array" and isinstance(value, str):
                # Accept JSON array string
                try:
                    coerced[key] = json.loads(value)
                    continue
                except Exception:
                    coerced[key] = [value]
                    continue
            coerced[key] = value
        # Fill in defaults for missing optional params
        for param_name, param in tool.parameters.items():
            if param_name not in coerced and not param.required and param.default is not None:
                coerced[param_name] = param.default
        return coerced

    def _validate_args(self, tool: ToolDefinition, args: dict[str, Any]) -> tuple[bool, str]:
        """Validate required args are present and types are correct."""
        for param_name, param in tool.parameters.items():
            if param.required and param_name not in args:
                return False, f"Missing required parameter '{param_name}' for tool '{tool.name}'"
        return True, ""

    # ------------------------------------------------------------------
    # File mutation snapshot support
    # ------------------------------------------------------------------

    _FILE_MUTATION_TOOLS = {
        "create_file", "write_file", "delete_file",
        "patch_file", "replace_text", "insert_text", "delete_text",
        "move_file", "rename_file",
    }

    def _snapshot_before(self, name: str, args: dict[str, Any]) -> None:
        if name not in self._FILE_MUTATION_TOOLS:
            return
        path_str = args.get("path") or args.get("source") or ""
        if not path_str:
            return
        try:
            from vibe_studio.tools.patch_tools import FileChangeSnapshot
            target = self.patch_tools._resolve(path_str)
            old_content = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
            rel = target.relative_to(self.workspace_root).as_posix() if target.exists() else str(path_str)
            snapshot = FileChangeSnapshot(
                path=rel,
                previous_content=old_content,
                new_content="",
                diff="",
                hash_before=self.patch_tools._hash(old_content),
                hash_after="",
            )
            self.patch_tools.history.append(snapshot)
        except Exception:
            pass

    def _snapshot_after(self, name: str, args: dict[str, Any]) -> None:
        if name not in self._FILE_MUTATION_TOOLS or not self.patch_tools.history:
            return
        path_str = args.get("path") or args.get("destination") or args.get("source") or ""
        if not path_str:
            return
        try:
            target = self.patch_tools._resolve(path_str)
            new_content = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
            snap = self.patch_tools.history[-1]
            snap.new_content = new_content
            snap.hash_after = self.patch_tools._hash(new_content)
            snap.diff = self.patch_tools._diff(snap.path, snap.previous_content, new_content)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return _error_result(name, f"Unknown tool: '{name}'. Use list_tools to see available tools.")

        # Coerce then validate
        args = self._coerce_args(tool, args)
        ok, err = self._validate_args(tool, args)
        if not ok:
            return _error_result(name, err)

        self._snapshot_before(name, args)
        start_time = time.monotonic()

        try:
            raw_res = tool.handler(**args)
            duration = time.monotonic() - start_time
            self._snapshot_after(name, args)
            return _normalise_result(name, raw_res, args, duration)
        except Exception as exc:
            # Pop the dangling snapshot — nothing was changed
            if name in self._FILE_MUTATION_TOOLS and self.patch_tools.history:
                snap = self.patch_tools.history[-1]
                if snap.new_content == "" and snap.hash_after == "":
                    self.patch_tools.history.pop()
            duration = time.monotonic() - start_time
            return _error_result(name, f"Tool execution error ({name}): {exc}", duration=duration)

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_default_tools(self) -> None:
        S = ToolParameter
        R = RiskLevel

        # ── Filesystem (read-only) ────────────────────────────────────
        self.register("list_directory", "List contents of a directory",
            {"path": S("string", "Directory path", False, ".")},
            self.fs_tools.list_directory, risk=R.SAFE)

        self.register("tree", "Get recursive folder hierarchy as text tree",
            {"path": S("string", "Root path", False, "."),
             "max_depth": S("integer", "Max depth", False, 3)},
            self.fs_tools.tree, risk=R.SAFE)

        self.register("read_file", "Read text content of a file (optional line range)",
            {"path": S("string", "File path"),
             "start_line": S("integer", "Start line (1-indexed)", False, 1),
             "end_line": S("integer", "End line inclusive", False, None)},
            self.fs_tools.read_file, risk=R.SAFE)

        self.register("read_multiple_files", "Read several files at once",
            {"paths": S("array", "List of file paths")},
            self.fs_tools.read_multiple_files, risk=R.SAFE)

        self.register("file_exists", "Check if a file exists",
            {"path": S("string", "File path")},
            self.fs_tools.file_exists, risk=R.SAFE)

        self.register("directory_exists", "Check if a directory exists",
            {"path": S("string", "Directory path")},
            self.fs_tools.directory_exists, risk=R.SAFE)

        self.register("get_file_metadata", "Get file size, extension, and modification time",
            {"path": S("string", "File path")},
            self.fs_tools.get_file_metadata, risk=R.SAFE)

        # ── Filesystem (write) ────────────────────────────────────────
        self.register("write_file", "Write/overwrite a file with text content",
            {"path": S("string", "File path"),
             "content": S("string", "Text content")},
            self.fs_tools.write_file, risk=R.MEDIUM)

        self.register("create_file", "Create a new file (fails if exists)",
            {"path": S("string", "File path"),
             "content": S("string", "Initial content", False, "")},
            self.fs_tools.create_file, risk=R.MEDIUM)

        self.register("delete_file", "Delete a file or empty directory",
            {"path": S("string", "File or directory path")},
            self.fs_tools.delete_file, risk=R.HIGH, requires_permission=False)

        self.register("move_file", "Move or rename a file/directory",
            {"source": S("string", "Source path"),
             "destination": S("string", "Destination path")},
            self.fs_tools.move_file, risk=R.MEDIUM)

        self.register("copy_file", "Copy a file or directory",
            {"source": S("string", "Source path"),
             "destination": S("string", "Destination path")},
            self.fs_tools.copy_file, risk=R.MEDIUM)

        self.register("rename_file", "Rename a file within its directory",
            {"path": S("string", "File path"),
             "new_name": S("string", "New filename (basename only)")},
            self.fs_tools.rename_file, risk=R.MEDIUM)

        # ── Search ────────────────────────────────────────────────────
        self.register("search_text", "Search text across the workspace",
            {"query": S("string", "Search query"),
             "case_sensitive": S("boolean", "Case sensitive", False, False)},
            self.search_tools.search_text, risk=R.SAFE)

        self.register("search_regex", "Regex search across workspace",
            {"pattern": S("string", "Regex pattern")},
            self.search_tools.search_regex, risk=R.SAFE)

        self.register("search_filename", "Search files by name pattern",
            {"pattern": S("string", "Filename substring or pattern")},
            self.search_tools.search_filename, risk=R.SAFE)

        self.register("search_symbol", "Find definition of a code symbol",
            {"name": S("string", "Symbol name")},
            self.search_tools.search_symbol, risk=R.SAFE)

        self.register("find_references", "Find all references to a symbol",
            {"symbol_name": S("string", "Symbol name")},
            self.search_tools.find_references, risk=R.SAFE)

        self.register("find_definition", "Find definition of a symbol across the project",
            {"symbol_name": S("string", "Symbol name")},
            self.search_tools.find_definition, risk=R.SAFE)

        # ── Code Analysis (AST) ──────────────────────────────────────
        self.register("get_function_signatures", "Extract function/class signatures from a Python file via AST",
            {"path": S("string", "Python file path")},
            self.code_analysis_tools.get_function_signatures, risk=R.SAFE)

        self.register("find_unused_imports", "Identify unused imported symbols in a Python file",
            {"path": S("string", "Python file path")},
            self.code_analysis_tools.find_unused_imports, risk=R.SAFE)

        self.register("get_complexity_score", "Calculate cyclomatic complexity per function in a Python file",
            {"path": S("string", "Python file path")},
            self.code_analysis_tools.get_complexity_score, risk=R.SAFE)

        self.register("search_import", "Find imports of a module",
            {"module_name": S("string", "Module or package name")},
            self.search_tools.search_import, risk=R.SAFE)

        self.register("find_usages", "Find all usages of a symbol (alias for find_references)",
            {"symbol_name": S("string", "Symbol name")},
            self.search_tools.find_references, risk=R.SAFE)

        # ── Patch / editing ───────────────────────────────────────────
        self.register("patch_file",
            "Replace an exact text block in a file with new content. "
            "ALWAYS read_file first to get the exact existing text.",
            {"path": S("string", "File path"),
             "target_text": S("string", "Exact text to replace (must exist verbatim)"),
             "replacement_text": S("string", "New replacement text")},
            self.patch_tools.patch_file, risk=R.MEDIUM)

        self.register("replace_text", "Replace old_str with new_str in a file",
            {"path": S("string", "File path"),
             "old_str": S("string", "String to find (verbatim)"),
             "new_str": S("string", "Replacement string")},
            self.patch_tools.replace_text, risk=R.MEDIUM)

        self.register("insert_text", "Insert text before or after an anchor string",
            {"path": S("string", "File path"),
             "position_text": S("string", "Anchor text to insert relative to"),
             "text_to_insert": S("string", "Text to insert"),
             "after": S("boolean", "True = insert after anchor, False = before", False, True)},
            self.patch_tools.insert_text, risk=R.MEDIUM)

        self.register("delete_text", "Delete a specific snippet from a file",
            {"path": S("string", "File path"),
             "text_to_delete": S("string", "Exact text snippet to delete")},
            self.patch_tools.delete_text, risk=R.MEDIUM)

        # ── Code intelligence ─────────────────────────────────────────
        self.register("detect_language", "Detect programming language of a file",
            {"file_path": S("string", "File path")},
            self.code_tools.detect_language, risk=R.SAFE)

        self.register("detect_project_type",
            "Detect project ecosystem, languages, frameworks, build system, test runner",
            {},
            self.code_tools.detect_project_type, risk=R.SAFE)

        self.register("detect_entry_points", "Detect main entry-point files",
            {},
            self.code_tools.detect_entry_points, risk=R.SAFE)

        self.register("detect_dependencies", "List Python and npm dependencies",
            {},
            self.code_tools.detect_dependencies, risk=R.SAFE)

        self.register("detect_build_system", "Identify the project build system",
            {},
            self.code_tools.detect_build_system, risk=R.SAFE)

        self.register("detect_test_framework", "Identify the project test framework",
            {},
            self.code_tools.detect_test_framework, risk=R.SAFE)

        self.register("inspect_package_configuration",
            "Read key configuration files (package.json, pyproject.toml, etc.)",
            {},
            self.code_tools.inspect_package_configuration, risk=R.SAFE)

        # ── Terminal ──────────────────────────────────────────────────
        self.register("execute_command",
            "Execute a shell command in the project directory",
            {"command": S("string", "Shell command to run"),
             "cwd": S("string", "Working directory (relative)", False, "."),
             "timeout": S("integer", "Timeout in seconds", False, 60)},
            self.terminal_tools.execute_command, risk=R.MEDIUM)

        self.register("run_tests",
            "Run the project test suite (auto-detects pytest/npm/cargo/go test)",
            {"test_path": S("string", "Optional specific test path/file", False, None),
             "timeout": S("integer", "Timeout in seconds", False, 120)},
            self.terminal_tools.run_tests, risk=R.LOW)

        self.register("run_linter",
            "Run the code linter (ruff/eslint/etc.)",
            {"path": S("string", "Path to lint", False, "."),
             "timeout": S("integer", "Timeout in seconds", False, 60)},
            self.terminal_tools.run_linter, risk=R.LOW)

        self.register("run_formatter",
            "Run the code formatter (ruff format/prettier/etc.)",
            {"path": S("string", "Path to format", False, "."),
             "timeout": S("integer", "Timeout in seconds", False, 60)},
            self.terminal_tools.run_formatter, risk=R.LOW)

        self.register("run_build",
            "Run the project build (npm run build / cargo build / make / etc.)",
            {"timeout": S("integer", "Timeout in seconds", False, 180)},
            self.terminal_tools.run_build, risk=R.LOW)

        # ── Git ───────────────────────────────────────────────────────
        self.register("git_status", "Get current Git working-tree status",
            {},
            self.git_tools.git_status, risk=R.SAFE)

        self.register("git_diff",
            "Get git diff. Use file_path to limit to one file. "
            "Use staged=True for staged changes.",
            {"file_path": S("string", "Optional file path", False, None),
             "staged": S("boolean", "Show staged diff", False, False)},
            self.git_tools.git_diff, risk=R.SAFE)

        self.register("git_log", "Get recent commit history",
            {"limit": S("integer", "Number of commits", False, 10)},
            self.git_tools.git_log, risk=R.SAFE)

        self.register("git_branch", "List local and remote branches",
            {},
            self.git_tools.git_branch, risk=R.SAFE)

        self.register("git_stage", "Stage specific file(s) for commit",
            {"path": S("string", "File or directory to stage")},
            self.git_tools.git_add, risk=R.LOW)

        self.register("git_unstage", "Unstage a file (git reset HEAD)",
            {"path": S("string", "File to unstage")},
            self.git_tools.git_unstage, risk=R.LOW)

        self.register("git_commit", "Stage all tracked changes and commit",
            {"message": S("string", "Commit message")},
            self.git_tools.git_commit, risk=R.MEDIUM)

        self.register("git_restore", "Restore a file to its last committed state",
            {"path": S("string", "File path")},
            self.git_tools.git_restore, risk=R.HIGH)

        self.register("git_checkout", "Checkout a branch",
            {"branch_name": S("string", "Branch name")},
            self.git_tools.git_checkout, risk=R.HIGH)


def _error_result(name: str, msg: str, duration: float = 0.0) -> dict[str, Any]:
    return {
        "tool": name,
        "exit_code": 1,
        "stdout": "",
        "stderr": msg,
        "duration": duration,
        "files_changed": [],
    }


def _normalise_result(
    name: str,
    raw_res: Any,
    args: dict[str, Any],
    duration: float,
) -> dict[str, Any]:
    if isinstance(raw_res, dict) and "exit_code" in raw_res:
        return {
            "tool": name,
            "exit_code": int(raw_res.get("exit_code", 0)),
            "stdout": str(raw_res.get("stdout", "")),
            "stderr": str(raw_res.get("stderr", "")),
            "duration": duration,
            "files_changed": raw_res.get("files_changed", []),
            "data": raw_res,
        }

    stdout_str = (
        json.dumps(raw_res, indent=2, default=str)
        if isinstance(raw_res, (dict, list))
        else str(raw_res)
    )
    changed: list[str] = []
    if "path" in args and isinstance(args["path"], str):
        changed = [args["path"]]
    return {
        "tool": name,
        "exit_code": 0,
        "stdout": stdout_str,
        "stderr": "",
        "duration": duration,
        "files_changed": changed,
        "data": raw_res,
    }


def default_tool_registry(workspace_root: str | Path = ".") -> "ToolRegistry":
    return ToolRegistry(workspace_root)
