"""Vibe Studio Plugin API — @vibe_plugin decorator and registry.

Usage in a plugin file (~/.vibe_studio/plugins/my_plugin.py):

    from vibe_studio.plugin.plugin_api import vibe_plugin

    @vibe_plugin(name="deploy_aws", description="Deploy to AWS", risk="MEDIUM")
    def deploy_aws(region: str, stack_name: str) -> str:
        # boto3 code here
        return f"Deployed {stack_name} to {region}"

    def register_tools():
        return get_registered_tools()
"""
from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable


RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

_REGISTRY: dict[str, "PluginTool"] = {}


@dataclass
class PluginTool:
    name: str
    description: str
    risk: str
    func: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    module: str = ""

    def to_tool_schema(self) -> dict[str, Any]:
        """Convert to ToolRegistry-compatible schema."""
        return {
            "name": self.name,
            "description": f"[Plugin/{self.risk}] {self.description}",
            "parameters": self.parameters,
        }

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)


def vibe_plugin(
    name: str,
    description: str = "",
    risk: str = "LOW",
    *,
    tags: list[str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that registers a function as a Vibe Studio tool plugin.

    Args:
        name:        Unique tool name (snake_case).
        description: Short description shown in the agent's tool list.
        risk:        One of LOW / MEDIUM / HIGH / CRITICAL.
                     MEDIUM+ triggers user approval before execution.
        tags:        Optional list of category tags (e.g. ["deploy", "aws"]).
    """
    risk_upper = risk.upper()
    if risk_upper not in RISK_LEVELS:
        raise ValueError(f"Invalid risk level '{risk}'. Choose from {RISK_LEVELS}")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Build JSON-schema parameters from function signature
        sig = inspect.signature(func)
        props: dict[str, Any] = {}
        required: list[str] = []
        for param_name, param in sig.parameters.items():
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                ptype = "string"
            elif ann in (str, "str"):
                ptype = "string"
            elif ann in (int, "int"):
                ptype = "integer"
            elif ann in (float, "float"):
                ptype = "number"
            elif ann in (bool, "bool"):
                ptype = "boolean"
            elif ann in (list, "list"):
                ptype = "array"
            else:
                ptype = "string"
            props[param_name] = {"type": ptype, "description": param_name}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        parameters_schema = {
            "type": "object",
            "properties": props,
            "required": required,
        }

        tool = PluginTool(
            name=name,
            description=description or func.__doc__ or "",
            risk=risk_upper,
            func=func,
            parameters=parameters_schema,
            module=func.__module__,
        )
        _REGISTRY[name] = tool

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        wrapper._vibe_plugin = tool  # type: ignore[attr-defined]
        return wrapper

    return decorator


def get_registered_tools() -> dict[str, Callable[..., Any]]:
    """Return all registered plugin tools as {name: callable} dict."""
    return {name: tool.func for name, tool in _REGISTRY.items()}


def get_plugin_schemas() -> list[dict[str, Any]]:
    """Return all plugin tool schemas for ToolRegistry."""
    return [tool.to_tool_schema() for tool in _REGISTRY.values()]


def clear_registry() -> None:
    """Clear all registered plugins (used in tests)."""
    _REGISTRY.clear()


def list_plugins() -> list[PluginTool]:
    """Return all registered PluginTool objects."""
    return list(_REGISTRY.values())
