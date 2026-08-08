"""Context engine — builds a ranked, token-budgeted context bundle for LLM prompts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ContextItem:
    path: str
    score: float
    reason: str
    kind: str = "file"
    content_snippet: str = ""
    line_count: int = 0


@dataclass
class ContextBundle:
    items: list[ContextItem] = field(default_factory=list)
    total_tokens_est: int = 0
    budget: int = 16000

    def format_prompt_context(self) -> str:
        if not self.items:
            return "No project file context available."
        sections: list[str] = []
        for item in self.items:
            header = f"--- FILE: {item.path} (relevance: {item.reason}, score: {item.score:.0f}) ---"
            sections.append(f"{header}\n{item.content_snippet}")
        return "\n\n".join(sections)


# Files/dirs that are never useful in context
_ALWAYS_SKIP = {
    ".git", ".venv", "node_modules", "__pycache__", "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage", ".tox",
}
_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".otf", ".mp4", ".mp3", ".zip", ".tar", ".gz",
    ".lock", ".sum",
}
# Domain keywords → relevance bonus
_DOMAIN_KEYWORDS = {
    "login": ["login", "auth", "signin", "sign_in", "credentials"],
    "auth": ["auth", "login", "token", "jwt", "session", "permission"],
    "style": ["style", "css", "theme", "color", "gradient", "dark", "light"],
    "test": ["test", "spec", "fixture", "mock", "assert"],
    "api": ["api", "route", "endpoint", "handler", "controller", "view"],
    "model": ["model", "schema", "entity", "database", "db", "migration"],
    "config": ["config", "settings", "env", ".env", "configuration"],
    "component": ["component", "widget", "panel", "dialog", "page"],
}


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"\b[A-Za-z0-9_\-\.]+\b", text) if len(t) > 1}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ContextEngine:
    """
    Produces a ranked, token-budgeted context bundle.

    Ranking factors (higher = more relevant):
      +80  active editor file
      +50  recently git-changed file
      +40  token matches filename exactly
      +20  token matches directory path
      +35  terminal error references filename
      +30  domain keyword matches (e.g. "login" → login.css)
      +15  file in same directory as active file
      +10  important config/entry-point file
       +5  has relevant file extension
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def build(
        self,
        prompt: str,
        active_file: str | None = None,
        git_changes: list[str] | None = None,
        terminal_errors: str | None = None,
        token_budget: int = 16000,
    ) -> ContextBundle:
        if not self.root.exists():
            return ContextBundle()

        prompt_tokens = _tokenize(prompt)
        err_tokens = _tokenize(terminal_errors) if terminal_errors else set()
        prompt_lower = prompt.lower()

        # Determine active directory for proximity scoring
        active_dir = ""
        if active_file:
            active_dir = str(Path(active_file).parent)

        candidates: list[tuple[Path, float, list[str]]] = []

        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()

            # Skip noise directories
            parts = rel.split("/")
            if any(p in _ALWAYS_SKIP or p.endswith(".egg-info") for p in parts):
                continue
            if path.suffix.lower() in _SKIP_EXTENSIONS:
                continue

            score = 0.0
            reasons: list[str] = []
            rel_lower = rel.lower()
            file_name = path.name.lower()

            # Active file
            if active_file and rel == active_file:
                score += 80
                reasons.append("active file")

            # Git-changed files
            if git_changes and rel in git_changes:
                score += 50
                reasons.append("git change")

            # Token match in filename
            for token in prompt_tokens:
                if len(token) < 3:
                    continue
                if token == file_name or token == Path(file_name).stem:
                    score += 40
                    reasons.append(f"filename={token}")
                elif token in file_name:
                    score += 25
                    reasons.append(f"filename~{token}")
                elif token in rel_lower:
                    score += 12
                    reasons.append(f"path~{token}")

            # Terminal error references
            for token in err_tokens:
                if len(token) >= 3 and token in file_name:
                    score += 35
                    reasons.append("error ref")

            # Domain keyword matching
            for domain, synonyms in _DOMAIN_KEYWORDS.items():
                if any(d in prompt_lower for d in [domain] + synonyms):
                    if any(syn in rel_lower for syn in synonyms):
                        score += 30
                        reasons.append(f"domain:{domain}")
                        break

            # Proximity to active file
            if active_dir and str(Path(rel).parent) == active_dir:
                score += 15
                reasons.append("same dir")

            # Important file bonuses
            if file_name in {"main.py", "app.py", "index.ts", "index.js", "package.json",
                             "pyproject.toml", "requirements.txt", "tsconfig.json"}:
                score += 10
                reasons.append("entry point")

            # Extension weight
            if path.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx", ".html",
                                        ".css", ".scss", ".json", ".yaml", ".toml", ".md"}:
                score += 5

            if score > 0:
                candidates.append((path, score, reasons))

        # Sort by score descending, take top 20
        ranked = sorted(candidates, key=lambda x: x[1], reverse=True)[:20]

        items: list[ContextItem] = []
        total_tokens = 0

        for path, score, reasons in ranked:
            try:
                rel = path.relative_to(self.root).as_posix()
                content = path.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()

                # Budget management — larger files get truncated more aggressively
                if len(content) > 6000:
                    # Show first 2000 and last 500 chars (captures imports + recent changes)
                    snippet = content[:2000] + "\n...[truncated]...\n" + content[-500:]
                else:
                    snippet = content

                est = _estimate_tokens(snippet)
                if total_tokens + est > token_budget and items:
                    # Try a very short snippet
                    snippet = content[:800] + "\n...[truncated]..."
                    est = _estimate_tokens(snippet)
                    if total_tokens + est > token_budget:
                        break

                total_tokens += est
                items.append(ContextItem(
                    path=rel,
                    score=score,
                    reason=", ".join(reasons[:3]),
                    content_snippet=snippet,
                    line_count=len(lines),
                ))
            except Exception:
                continue

        return ContextBundle(items=items, total_tokens_est=total_tokens, budget=token_budget)
