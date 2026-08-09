"""Semantic Code Search — Natural language query engine over Graph RAG AST & project symbols."""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from vibe_studio.context.graph_rag import CodeGraph


class SimpleASTVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: Dict[str, int] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.symbols[node.name] = node.lineno
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.symbols[node.name] = node.lineno
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.symbols[node.name] = node.lineno
        self.generic_visit(node)


@dataclass
class SearchResult:
    file_path: str
    symbol_name: str
    symbol_type: str  # "function", "class", "module"
    score: float
    line_number: int
    snippet: str
    relevance_reason: str


class SemanticCodeSearch:
    """Natural Language Code Search using AST Symbol Indexing + Query Intent Expansion."""

    SYNONYM_MAP = {
        "database": ["db", "sql", "sqlite", "query", "session", "table", "crud", "model", "storage", "məlumat bazası", "qoşulan"],
        "auth": ["login", "user", "password", "token", "jwt", "permission", "security", "authenticate", "authentication"],
        "test": ["pytest", "assert", "mock", "fixture", "suite"],
        "api": ["http", "route", "endpoint", "request", "response", "server", "rest"],
        "search": ["query", "find", "filter", "semantic", "index"],
        "agent": ["orchestrator", "worker", "swarm", "executor", "task"],
    }

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.code_graph = CodeGraph.build_from_root(self.workspace_root)

    def _expand_query(self, query: str) -> List[str]:
        words = re.findall(r"\w+", query.lower())
        expanded = set(words)
        for w in words:
            for key, syns in self.SYNONYM_MAP.items():
                if w in syns or w == key or key in w:
                    expanded.add(key)
                    expanded.update(syns)
        return list(expanded)

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Search code symbols and files using natural language query."""
        keywords = self._expand_query(query)
        results: List[SearchResult] = []

        # Iterate all python files in workspace
        for py_file in self.workspace_root.rglob("*.py"):
            if ".venv" in py_file.parts or ".git" in py_file.parts or "__pycache__" in py_file.parts:
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content, filename=str(py_file))
                visitor = SimpleASTVisitor()
                visitor.visit(tree)

                lines = content.splitlines()
                rel_path = str(py_file.relative_to(self.workspace_root))

                # Rank file-level relevance
                file_score = 0.0
                content_lower = content.lower()
                for kw in keywords:
                    count = content_lower.count(kw)
                    if count > 0:
                        file_score += math.log(1 + count) * (2.0 if kw in query.lower() else 1.0)

                if file_score <= 0:
                    continue

                # Rank symbols inside file
                for sym_name, line_no in visitor.symbols.items():
                    snippet = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""
                    sym_lower = sym_name.lower()
                    sym_score = file_score

                    matched_kws = []
                    for kw in keywords:
                        if kw in sym_lower:
                            sym_score += 3.0
                            matched_kws.append(kw)

                    score = round(sym_score, 2)
                    sym_type = "class" if sym_name[0].isupper() else "function"
                    reason = f"Matched keywords: {', '.join(matched_kws or keywords[:3])}"

                    results.append(
                        SearchResult(
                            file_path=rel_path,
                            symbol_name=sym_name,
                            symbol_type=sym_type,
                            score=score,
                            line_number=line_no,
                            snippet=snippet.strip(),
                            relevance_reason=reason,
                        )
                    )
            except Exception:
                continue

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)

        # Deduplicate top_k
        seen = set()
        deduped = []
        for r in results:
            key = (r.file_path, r.symbol_name)
            if key not in seen:
                seen.add(key)
                deduped.append(r)
            if len(deduped) >= top_k:
                break

        return deduped
