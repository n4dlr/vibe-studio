"""ContextCompactor & ContextVirtualizer — High-Density Token Virtualization.

Empowers 1.5B, 2B, 3B, 7B models to reason over massive codebases by compressing
file contents into high-signal AST structural outlines and sliding execution windows.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


class ContextVirtualizer:
    """Compresses source code files and execution histories into high-density token formats."""

    @classmethod
    def outline_python(cls, source_code: str, max_chars: int = 1500) -> str:
        """Extract high-level Python AST outline (classes, methods, functions, signatures)."""
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            # Fallback to regex outline
            lines = []
            for line in source_code.splitlines():
                if re.match(r"^\s*(class\s+\w+|def\s+\w+|async\s+def\s+\w+)", line):
                    lines.append(line.rstrip())
            return "\n".join(lines[:30]) or source_code[:max_chars]

        outlines: list[str] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                doc = ast.get_docstring(node)
                doc_str = f" # {doc.splitlines()[0]}" if doc else ""
                outlines.append(f"def {node.name}({', '.join(args)}){ret}:{doc_str}")

            elif isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                base_str = f"({', '.join(bases)})" if bases else ""
                outlines.append(f"class {node.name}{base_str}:")
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [a.arg for a in sub.args.args]
                        ret = f" -> {ast.unparse(sub.returns)}" if sub.returns else ""
                        outlines.append(f"    def {sub.name}({', '.join(args)}){ret}")

        result = "\n".join(outlines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n    ... [outline truncated]"
        return result

    @classmethod
    def compress_history(cls, tool_history: list[dict[str, Any]], keep_recent: int = 3) -> str:
        """Compress execution history: older turns distilled into 1-line bullet points."""
        if not tool_history:
            return ""

        if len(tool_history) <= keep_recent:
            parts = []
            for step in tool_history:
                tool = step.get("tool", "")
                args = step.get("args", {})
                obs = step.get("observation", {})
                code = obs.get("exit_code", 0) if isinstance(obs, dict) else 0
                parts.append(f"- Step: {tool}({args}) -> exit {code}")
            return "\n".join(parts)

        # Distill older steps
        older = tool_history[:-keep_recent]
        recent = tool_history[-keep_recent:]

        older_summary = [
            f"  • Ran `{s.get('tool', '')}` on {s.get('args', {}).get('path', 'args')}"
            for s in older
        ]
        recent_details = []
        for s in recent:
            tool = s.get("tool", "")
            args = s.get("args", {})
            obs = s.get("observation", {})
            recent_details.append(f"- Recent: {tool}({args})\n  Observation: {str(obs)[:160]}")

        return (
            "Prior Steps Summary:\n"
            + "\n".join(older_summary)
            + "\n\nRecent Detailed Steps:\n"
            + "\n".join(recent_details)
        )

    @classmethod
    def extract_symbol_context(cls, file_content: str, symbol_name: str, surrounding_lines: int = 15) -> str:
        """Extract only the definition and surrounding context for a target symbol."""
        lines = file_content.splitlines()
        matches = []
        for i, line in enumerate(lines):
            if re.search(rf"\b(def|class)\s+{re.escape(symbol_name)}\b", line):
                matches.append(i)

        if not matches:
            return file_content[:1500]

        target_idx = matches[0]
        start = max(0, target_idx - 3)
        end = min(len(lines), target_idx + surrounding_lines)
        return "\n".join(lines[start:end])
