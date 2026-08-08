from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vibe_studio.tools.code_tools import CodeTools
from vibe_studio.tools.filesystem_tools import FilesystemTools
from vibe_studio.tools.git_tools import GitTools
from vibe_studio.tools.patch_tools import PatchTools
from vibe_studio.tools.search_tools import SearchTools
from vibe_studio.tools.terminal_tools import TerminalTools


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
        self._tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, name: str, description: str, parameters: dict[str, ToolParameter], handler: Callable[..., Any]) -> None:
        self._tools[name] = ToolDefinition(name=name, description=description, parameters=parameters, handler=handler)

    def list_tools(self) -> list[dict[str, Any]]:
        result = []
        for name, tool in self._tools.items():
            properties = {}
            required = []
            for param_name, param in tool.parameters.items():
                properties[param_name] = {"type": param.type, "description": param.description}
                if param.required:
                    required.append(param_name)
            result.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })
        return result

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    # Tools that mutate files — we snapshot before execution so undo always works
    _FILE_MUTATION_TOOLS = {
        "create_file", "write_file", "delete_file",
        "patch_file", "replace_text", "insert_text", "delete_text",
        "move_file", "rename_file",
    }

    def _snapshot_before(self, name: str, args: dict[str, Any]) -> None:
        """Record a PatchTools snapshot before a file-mutating tool runs."""
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
            # Store a preliminary snapshot; new_content will be empty until after execution
            # We use _record_snapshot with empty new_content — undo just needs old_content
            snapshot = FileChangeSnapshot(
                path=rel,
                previous_content=old_content,
                new_content="",  # updated after execution
                diff="",
                hash_before=self.patch_tools._hash(old_content),
                hash_after="",
            )
            self.patch_tools.history.append(snapshot)
        except Exception:
            pass

    def _snapshot_after(self, name: str, args: dict[str, Any]) -> None:
        """Update the last snapshot with actual post-execution content."""
        if name not in self._FILE_MUTATION_TOOLS or not self.patch_tools.history:
            return
        path_str = args.get("path") or args.get("source") or args.get("destination") or ""
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

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return {
                "tool": name,
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Unknown tool: '{name}'",
                "duration": 0.0,
                "files_changed": [],
            }

        self._snapshot_before(name, args)
        start_time = time.monotonic()
        try:
            raw_res = tool.handler(**args)
            duration = time.monotonic() - start_time
            self._snapshot_after(name, args)

            if isinstance(raw_res, dict) and "stdout" in raw_res:
                return {
                    "tool": name,
                    "exit_code": raw_res.get("exit_code", 0),
                    "stdout": str(raw_res.get("stdout", "")),
                    "stderr": str(raw_res.get("stderr", "")),
                    "duration": duration,
                    "files_changed": raw_res.get("files_changed", []),
                    "data": raw_res,
                }

            stdout_str = json.dumps(raw_res, indent=2) if isinstance(raw_res, (dict, list)) else str(raw_res)
            return {
                "tool": name,
                "exit_code": 0,
                "stdout": stdout_str,
                "stderr": "",
                "duration": duration,
                "files_changed": [args.get("path")] if "path" in args and isinstance(args["path"], str) else [],
                "data": raw_res,
            }
        except Exception as exc:
            # Remove the dangling snapshot on failure — nothing was actually changed
            if name in self._FILE_MUTATION_TOOLS and self.patch_tools.history:
                self.patch_tools.history.pop()
            duration = time.monotonic() - start_time
            return {
                "tool": name,
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Tool execution failed ({name}): {exc}",
                "duration": duration,
                "files_changed": [],
            }

    def _register_default_tools(self) -> None:
        # Filesystem
        self.register("list_directory", "List contents of directory", {"path": ToolParameter("string", "Directory path", False, ".")}, self.fs_tools.list_directory)
        self.register("tree", "Get folder hierarchy tree", {"path": ToolParameter("string", "Path", False, "."), "max_depth": ToolParameter("integer", "Max depth", False, 3)}, self.fs_tools.tree)
        self.register("read_file", "Read text content of a file", {"path": ToolParameter("string", "File path"), "start_line": ToolParameter("integer", "Start line", False, 1), "end_line": ToolParameter("integer", "End line", False, None)}, self.fs_tools.read_file)
        self.register("read_multiple_files", "Read text of multiple files", {"paths": ToolParameter("array", "List of paths")}, self.fs_tools.read_multiple_files)
        self.register("write_file", "Write text to a file", {"path": ToolParameter("string", "File path"), "content": ToolParameter("string", "Content text")}, self.fs_tools.write_file)
        self.register("create_file", "Create a new file", {"path": ToolParameter("string", "File path"), "content": ToolParameter("string", "Content text", False, "")}, self.fs_tools.create_file)
        self.register("delete_file", "Delete a file or folder", {"path": ToolParameter("string", "File path")}, self.fs_tools.delete_file)
        self.register("move_file", "Move or rename file", {"source": ToolParameter("string", "Source"), "destination": ToolParameter("string", "Destination")}, self.fs_tools.move_file)
        self.register("copy_file", "Copy file or folder", {"source": ToolParameter("string", "Source"), "destination": ToolParameter("string", "Destination")}, self.fs_tools.copy_file)
        self.register("rename_file", "Rename file", {"path": ToolParameter("string", "File path"), "new_name": ToolParameter("string", "New name")}, self.fs_tools.rename_file)
        self.register("file_exists", "Check if file exists", {"path": ToolParameter("string", "File path")}, self.fs_tools.file_exists)
        self.register("directory_exists", "Check if directory exists", {"path": ToolParameter("string", "Directory path")}, self.fs_tools.directory_exists)
        self.register("get_file_metadata", "Get file size and info", {"path": ToolParameter("string", "File path")}, self.fs_tools.get_file_metadata)

        # Search
        self.register("search_text", "Search text across workspace", {"query": ToolParameter("string", "Text query"), "case_sensitive": ToolParameter("boolean", "Case sensitive", False, False)}, self.search_tools.search_text)
        self.register("search_regex", "Regex search across workspace", {"pattern": ToolParameter("string", "Regex pattern")}, self.search_tools.search_regex)
        self.register("search_filename", "Search files by name pattern", {"pattern": ToolParameter("string", "Filename pattern")}, self.search_tools.search_filename)
        self.register("search_symbol", "Search definition of code symbol", {"name": ToolParameter("string", "Symbol name")}, self.search_tools.search_symbol)
        self.register("search_import", "Find imports of a module", {"module_name": ToolParameter("string", "Module name")}, self.search_tools.search_import)
        self.register("find_references", "Find references to a symbol", {"symbol_name": ToolParameter("string", "Symbol name")}, self.search_tools.find_references)
        self.register("find_definition", "Find definition of symbol", {"symbol_name": ToolParameter("string", "Symbol name")}, self.search_tools.find_definition)

        # Code understanding
        self.register("detect_language", "Detect programming language", {"file_path": ToolParameter("string", "File path")}, self.code_tools.detect_language)
        self.register("detect_project_type", "Detect project ecosystem, languages, frameworks", {}, self.code_tools.detect_project_type)
        self.register("detect_entry_points", "Detect main entry point files", {}, self.code_tools.detect_entry_points)
        self.register("detect_dependencies", "Detect python/npm dependencies", {}, self.code_tools.detect_dependencies)
        self.register("detect_build_system", "Detect project build system", {}, self.code_tools.detect_build_system)
        self.register("detect_test_framework", "Detect project test runner", {}, self.code_tools.detect_test_framework)
        self.register("inspect_package_configuration", "Inspect configuration files", {}, self.code_tools.inspect_package_configuration)

        # Editing
        self.register("patch_file", "Replace exact target block in file with new content", {"path": ToolParameter("string", "File path"), "target_text": ToolParameter("string", "Target text to replace"), "replacement_text": ToolParameter("string", "New replacement text")}, self.patch_tools.patch_file)
        self.register("replace_text", "Replace text in file", {"path": ToolParameter("string", "File path"), "old_str": ToolParameter("string", "Old string"), "new_str": ToolParameter("string", "New string")}, self.patch_tools.replace_text)
        self.register("insert_text", "Insert text before or after position", {"path": ToolParameter("string", "File path"), "position_text": ToolParameter("string", "Position anchor text"), "text_to_insert": ToolParameter("string", "Text to insert"), "after": ToolParameter("boolean", "Insert after anchor", False, True)}, self.patch_tools.insert_text)
        self.register("delete_text", "Delete specific snippet from file", {"path": ToolParameter("string", "File path"), "text_to_delete": ToolParameter("string", "Snippet to delete")}, self.patch_tools.delete_text)

        # Terminal
        self.register("execute_command", "Execute shell command in project directory", {"command": ToolParameter("string", "Shell command"), "cwd": ToolParameter("string", "Directory", False, "."), "timeout": ToolParameter("integer", "Timeout seconds", False, 60)}, self.terminal_tools.execute_command)
        self.register("run_tests", "Run test suite", {"test_path": ToolParameter("string", "Optional test path", False, None), "timeout": ToolParameter("integer", "Timeout", False, 120)}, self.terminal_tools.run_tests)
        self.register("run_linter", "Run code linter", {"path": ToolParameter("string", "Path", False, "."), "timeout": ToolParameter("integer", "Timeout", False, 60)}, self.terminal_tools.run_linter)
        self.register("run_formatter", "Run code formatter", {"path": ToolParameter("string", "Path", False, "."), "timeout": ToolParameter("integer", "Timeout", False, 60)}, self.terminal_tools.run_formatter)
        self.register("run_build", "Run project build", {"timeout": ToolParameter("integer", "Timeout", False, 180)}, self.terminal_tools.run_build)

        # Git
        self.register("git_status", "Get Git status summary", {}, self.git_tools.git_status)
        self.register("git_diff", "Get Git diff", {"file_path": ToolParameter("string", "Optional file path", False, None)}, self.git_tools.git_diff)
        self.register("git_log", "Get recent Git commit log", {"limit": ToolParameter("integer", "Limit", False, 10)}, self.git_tools.git_log)
        self.register("git_branch", "List Git branches", {}, self.git_tools.git_branch)
        self.register("git_commit", "Stage all changes and commit with message", {"message": ToolParameter("string", "Commit message")}, self.git_tools.git_commit)
        self.register("git_restore", "Restore file to last committed state", {"path": ToolParameter("string", "File path")}, self.git_tools.git_restore)
        self.register("git_checkout", "Checkout a branch", {"branch_name": ToolParameter("string", "Branch name")}, self.git_tools.git_checkout)

        # Extra search
        self.register("find_usages", "Find all usages of a symbol across workspace", {"symbol_name": ToolParameter("string", "Symbol")}, self.search_tools.find_references)


def default_tool_registry(workspace_root: str | Path = ".") -> ToolRegistry:
    return ToolRegistry(workspace_root)
