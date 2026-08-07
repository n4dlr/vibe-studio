from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolCall:
    name: str
    description: str
    args: dict[str, object]


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, ToolCall] = {}

    def register(self, name: str, description: str, args: dict[str, object]) -> None:
        self.tools[name] = ToolCall(name=name, description=description, args=args)

    def list_tools(self) -> list[ToolCall]:
        return list(self.tools.values())

    def get(self, name: str) -> ToolCall | None:
        return self.tools.get(name)


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("read_file", "Read a file from disk", {"path": "str"})
    registry.register("write_file", "Write content to a file", {"path": "str", "content": "str"})
    registry.register("list_files", "List files in a directory", {"path": "str"})
    registry.register("run_command", "Execute a safe shell command", {"command": "str"})
    registry.register("run_tests", "Run project tests", {"path": "str"})
    return registry
