"""Auto-Documentation Engine — Auto-generates README, API reference, and Mermaid architecture diagrams."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ModuleDoc:
    module_path: str
    docstring: str
    classes: List[Dict[str, Any]] = field(default_factory=list)
    functions: List[Dict[str, Any]] = field(default_factory=list)


class AutoDocGenerator:
    """Auto-documentation generator for Python codebases."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()

    def inspect_module(self, py_file: Path) -> ModuleDoc:
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_file))
            rel_path = str(py_file.relative_to(self.workspace_root))
            mod_docstring = ast.get_docstring(tree) or ""

            classes = []
            functions = []

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    cls_doc = ast.get_docstring(node) or ""
                    methods = [
                        {
                            "name": m.name,
                            "docstring": ast.get_docstring(m) or "",
                            "args": [a.arg for a in m.args.args],
                        }
                        for m in node.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    classes.append({"name": node.name, "docstring": cls_doc, "methods": methods})
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fn_doc = ast.get_docstring(node) or ""
                    args = [a.arg for a in node.args.args]
                    functions.append({"name": node.name, "docstring": fn_doc, "args": args})

            return ModuleDoc(module_path=rel_path, docstring=mod_docstring, classes=classes, functions=functions)
        except Exception:
            return ModuleDoc(module_path=str(py_file), docstring="")

    def generate_api_reference(self) -> str:
        md = ["# API Reference\n"]
        for py_file in sorted(self.workspace_root.rglob("*.py")):
            if ".venv" in py_file.parts or ".git" in py_file.parts or "tests" in py_file.parts:
                continue

            doc = self.inspect_module(py_file)
            if not doc.classes and not doc.functions:
                continue

            md.append(f"## Module: `{doc.module_path}`\n")
            if doc.docstring:
                md.append(f"> {doc.docstring}\n")

            for cls in doc.classes:
                md.append(f"### Class `{cls['name']}`")
                if cls["docstring"]:
                    md.append(f"*{cls['docstring']}*\n")
                for m in cls["methods"]:
                    args_str = ", ".join(m["args"])
                    md.append(f"- `def {m['name']}({args_str})` — {m['docstring'] or 'No docstring'}")
                md.append("")

            for fn in doc.functions:
                args_str = ", ".join(fn["args"])
                md.append(f"### Function `def {fn['name']}({args_str})`")
                if fn["docstring"]:
                    md.append(f"*{fn['docstring']}*\n")

        return "\n".join(md)

    def generate_mermaid_diagram(self) -> str:
        lines = ["```mermaid", "classDiagram"]
        for py_file in self.workspace_root.rglob("*.py"):
            if ".venv" in py_file.parts or ".git" in py_file.parts or "tests" in py_file.parts:
                continue

            doc = self.inspect_module(py_file)
            for cls in doc.classes:
                lines.append(f"    class {cls['name']} {{")
                for m in cls["methods"][:5]:
                    lines.append(f"        +{m['name']}()")
                lines.append("    }")
        lines.append("```")
        return "\n".join(lines)
