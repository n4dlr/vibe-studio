from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from vibe_studio.project.project_scanner import ProjectScanner


@dataclass
class ContextItem:
    path: str
    score: float
    reason: str
    kind: str = "file"
    content_snippet: str = ""


@dataclass
class ContextBundle:
    items: list[ContextItem] = field(default_factory=list)
    total_tokens_est: int = 0
    budget: int = 12000

    def format_prompt_context(self) -> str:
        if not self.items:
            return "No specific project file context retrieved."
        sections = []
        for item in self.items:
            sections.append(f"--- FILE: {item.path} (Relevance: {item.reason}, Score: {item.score:.1f}) ---\n{item.content_snippet}\n")
        return "\n".join(sections)


class ContextEngine:
    """Produces ranked relevance-based context retrieval for LLM prompt context packing."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.scanner = ProjectScanner(self.root)

    def _tokenize(self, text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"\b[A-Za-z0-9_\-\./]+\b", text) if len(token) > 1}

    def build(
        self,
        prompt: str,
        active_file: str | None = None,
        git_changes: list[str] | None = None,
        terminal_errors: str | None = None,
    ) -> ContextBundle:
        items: list[ContextItem] = []
        if not self.root.exists():
            return ContextBundle(items=items)

        prompt_tokens = self._tokenize(prompt)
        err_tokens = self._tokenize(terminal_errors) if terminal_errors else set()

        candidates: list[tuple[Path, float, str]] = []

        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            parts = rel.split("/")
            if any(p in {".git", ".venv", "node_modules", "__pycache__", "dist", "build"} for p in parts):
                continue

            score = 0.0
            reasons = []
            rel_lower = rel.lower()
            file_name = path.name.lower()

            # Active file boost
            if active_file and rel == active_file:
                score += 80
                reasons.append("active editor")

            # Git changes boost
            if git_changes and rel in git_changes:
                score += 50
                reasons.append("recent git change")

            # Query token matching in filename / path
            for token in prompt_tokens:
                if token in file_name:
                    score += 40
                    reasons.append(f"matched filename '{token}'")
                elif token in rel_lower:
                    score += 20
                    reasons.append(f"matched path '{token}'")

            # Terminal error relevance boost
            for token in err_tokens:
                if token in file_name:
                    score += 45
                    reasons.append("terminal error reference")

            # Natural language keyword relevance (login, auth, api, test, etc.)
            for kw in ["login", "auth", "user", "api", "page", "style", "css", "theme", "dark", "config"]:
                if kw in prompt.lower() and kw in rel_lower:
                    score += 30
                    reasons.append(f"matched domain keyword '{kw}'")

            # File extension weight
            if rel_lower.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".yaml", ".toml")):
                score += 5

            if score > 0:
                candidates.append((path, score, ", ".join(reasons) if reasons else "project relevance"))

        ranked = sorted(candidates, key=lambda item: item[1], reverse=True)[:15]

        total_est = 0
        for path, score, reason in ranked:
            try:
                rel = path.relative_to(self.root).as_posix()
                content = path.read_text(encoding="utf-8", errors="replace")
                snippet = content[:3000] if len(content) > 3000 else content
                est_tokens = len(snippet) // 4
                if total_est + est_tokens > 12000 and items:
                    break
                total_est += est_tokens
                items.append(ContextItem(path=rel, score=score, reason=reason, content_snippet=snippet))
            except Exception:
                continue

        return ContextBundle(items=items, total_tokens_est=total_est)
