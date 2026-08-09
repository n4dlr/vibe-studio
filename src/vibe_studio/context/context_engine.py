"""Context engine — ranked, token-budgeted context bundle for LLM prompts.

Now with:
  - SQLite index cache for incremental scanning (Maddə 6)
  - Optional semantic RAG with sentence-transformers (Maddə 1)
  - Keyword ranking as robust fallback when embeddings unavailable
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator


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


_ALWAYS_SKIP = {
    ".git", ".venv", "node_modules", "__pycache__", "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage", ".tox",
    ".vibe_studio",
}
_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".otf", ".mp4", ".mp3", ".zip", ".tar", ".gz",
    ".lock", ".sum",
}
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


def _file_hash(path: Path) -> str:
    try:
        stat = path.stat()
        return hashlib.md5(f"{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()[:16]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# SQLite file index (incremental scanning)
# ---------------------------------------------------------------------------

class _FileIndex:
    """SQLite-backed file index for fast incremental lookups."""

    def __init__(self, root: Path):
        self.root = root
        db_dir = root / ".vibe_studio"
        db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_dir / "index.db"
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS files (
                    rel_path TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    content_preview TEXT NOT NULL DEFAULT '',
                    line_count INTEGER NOT NULL DEFAULT 0,
                    indexed_at REAL NOT NULL
                );
            """)

    def upsert(self, rel_path: str, file_hash: str, preview: str, line_count: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO files (rel_path, file_hash, content_preview, line_count, indexed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (rel_path, file_hash, preview, line_count, time.time()),
            )

    def get(self, rel_path: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM files WHERE rel_path=?", (rel_path,)).fetchone()
        return dict(row) if row else None

    def all_paths(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT rel_path FROM files").fetchall()
        return [r["rel_path"] for r in rows]

    def remove(self, rel_path: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM files WHERE rel_path=?", (rel_path,))


# ---------------------------------------------------------------------------
# Semantic embedding (optional — requires sentence-transformers)
# ---------------------------------------------------------------------------

_EMBEDDER: Any = None
_EMBEDDER_TRIED = False


def _get_embedder() -> Any:
    global _EMBEDDER, _EMBEDDER_TRIED
    if _EMBEDDER_TRIED:
        return _EMBEDDER
    _EMBEDDER_TRIED = True
    try:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _EMBEDDER = None
    return _EMBEDDER


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# ContextEngine
# ---------------------------------------------------------------------------

class ContextEngine:
    """
    Ranked, token-budgeted context bundle.

    Ranking:
      +80  active editor file
      +50  recently git-changed file
      +40  token matches filename exactly
      +20  token matches directory path
      +35  terminal error references filename
      +30  domain keyword match
      +15  same directory as active file
      +10  important entry-point file
      +5   relevant extension
      +semantic cosine similarity bonus (0-60) when embeddings available
      +graph-neighbour expansion (Sütun 1) when graph_expand=True
    """

    def __init__(self, root: str | Path, rag_enabled: bool = False, graph_expand: bool = False):
        self.root = Path(root).resolve()
        self.rag_enabled = rag_enabled
        self.graph_expand = graph_expand
        self._index = _FileIndex(self.root)
        self._graph_expander: object = None  # lazy-init on first build

    def _should_skip(self, rel: str, path: Path) -> bool:
        parts = rel.split("/")
        if any(p in _ALWAYS_SKIP or p.endswith(".egg-info") for p in parts):
            return True
        if path.suffix.lower() in _SKIP_EXTENSIONS:
            return True
        return False

    def _index_file(self, path: Path, rel: str) -> tuple[str, int]:
        """Return (content_preview, line_count). Uses cache if hash unchanged."""
        fhash = _file_hash(path)
        cached = self._index.get(rel)
        if cached and cached["file_hash"] == fhash:
            return cached["content_preview"], cached["line_count"]
        # Re-read and update cache
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            if len(content) > 6000:
                preview = content[:2000] + "\n...[truncated]...\n" + content[-500:]
            else:
                preview = content
            self._index.upsert(rel, fhash, preview, len(lines))
            return preview, len(lines)
        except Exception:
            return "", 0

    def update_incremental(self, changed_files: list[str]) -> None:
        """Update index for a list of changed relative paths (from git/file watcher)."""
        for rel in changed_files:
            path = self.root / rel
            if path.exists() and path.is_file() and not self._should_skip(rel, path):
                self._index_file(path, rel)
            else:
                self._index.remove(rel)

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
        active_dir = str(Path(active_file).parent) if active_file else ""

        # Compute prompt embedding once if RAG enabled
        prompt_embedding: list[float] = []
        embedder = _get_embedder() if self.rag_enabled else None
        if embedder and prompt:
            try:
                prompt_embedding = embedder.encode(prompt).tolist()
            except Exception:
                pass

        candidates: list[tuple[Path, float, list[str]]] = []

        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            if self._should_skip(rel, path):
                continue

            score = 0.0
            reasons: list[str] = []
            rel_lower = rel.lower()
            file_name = path.name.lower()

            # Active file
            if active_file and rel == active_file:
                score += 80
                reasons.append("active file")

            # Git-changed
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

            # Terminal error refs
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

            # Proximity
            if active_dir and str(Path(rel).parent) == active_dir:
                score += 15
                reasons.append("same dir")

            # Entry point bonus
            if file_name in {"main.py", "app.py", "index.ts", "index.js", "package.json",
                             "pyproject.toml", "requirements.txt", "tsconfig.json"}:
                score += 10
                reasons.append("entry point")

            # Extension weight
            if path.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx", ".html",
                                       ".css", ".scss", ".json", ".yaml", ".toml", ".md"}:
                score += 5

            # Import graph
            if active_file:
                active_stem = Path(active_file).stem
                if active_stem and active_stem.lower() in rel_lower:
                    score += 25
                    reasons.append("imported graph")

            # Semantic similarity bonus (RAG)
            if embedder and prompt_embedding and score > 0:
                try:
                    preview, _ = self._index_file(path, rel)
                    if preview:
                        file_emb = embedder.encode(preview[:1000]).tolist()
                        sim = _cosine_sim(prompt_embedding, file_emb)
                        semantic_bonus = sim * 60
                        if semantic_bonus > 5:
                            score += semantic_bonus
                            reasons.append(f"semantic:{sim:.2f}")
                except Exception:
                    pass

            if score > 0:
                candidates.append((path, score, reasons))

        ranked = sorted(candidates, key=lambda x: x[1], reverse=True)[:20]

        items: list[ContextItem] = []
        total_tokens = 0

        for path, score, reasons in ranked:
            try:
                rel = path.relative_to(self.root).as_posix()
                preview, line_count = self._index_file(path, rel)
                if not preview:
                    continue
                est = _estimate_tokens(preview)
                if total_tokens + est > token_budget and items:
                    short = preview[:800] + "\n...[truncated]..."
                    est = _estimate_tokens(short)
                    if total_tokens + est > token_budget:
                        break
                    preview = short
                total_tokens += est
                items.append(ContextItem(
                    path=rel, score=score,
                    reason=", ".join(reasons[:3]),
                    content_snippet=preview, line_count=line_count,
                ))
            except Exception:
                continue

        bundle = ContextBundle(items=items, total_tokens_est=total_tokens, budget=token_budget)

        # Sütun 1: Graph RAG — expand with structurally related neighbours
        if self.graph_expand:
            expander = self._ensure_graph_expander()
            if expander is not None:
                try:
                    bundle = expander.expand(  # type: ignore[union-attr]
                        bundle,
                        max_extra_tokens=max(0, token_budget - total_tokens),
                    )
                except Exception:
                    pass

        return bundle

    def _ensure_graph_expander(self) -> object:
        """Lazy-initialise GraphContextExpander (builds graph on first call)."""
        if self._graph_expander is None:
            try:
                from vibe_studio.context.graph_rag import GraphContextExpander
                self._graph_expander = GraphContextExpander(self.root)
            except Exception:
                pass
        return self._graph_expander
