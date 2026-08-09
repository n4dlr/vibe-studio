"""GlobalMemory — cross-project pattern storage for Vibe Studio.

Sütun 7 (Multi-Project Memory):
  Stores cross-project patterns in ~/.vibe_studio/global_memory.db.

  Tables:
    patterns — (framework, pattern_type, prompt_keyword, solution_summary, use_count)
    global_kv — key-value store for agent-agnostic settings

  API:
    record_pattern(framework, pattern_type, keyword, solution)
    recall_patterns(prompt, frameworks) → list[PatternRecord]
    build_global_hint(prompt, frameworks) → str (ready for injection into system prompt)

Usage::

    gm = GlobalMemory()
    gm.record_pattern("django", "auth", "login", "Use LoginView with custom backend")
    hint = gm.build_global_hint("add login to app", frameworks=["django"])
    # → "GLOBAL PATTERNS (from past projects): ..."
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

_GLOBAL_DB_DIR = Path.home() / ".vibe_studio"
_GLOBAL_DB_PATH = _GLOBAL_DB_DIR / "global_memory.db"


class LRUPatternCache:
    """In-memory LRU cache for pattern lookups."""

    def __init__(self, capacity: int = 500) -> None:
        self.capacity = capacity
        self._cache: OrderedDict[str, list[PatternRecord]] = OrderedDict()

    def get(self, key: str) -> list[PatternRecord] | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: list[PatternRecord]) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PatternRecord:
    """A reusable solution pattern extracted from a past project task."""

    id: int
    framework: str
    pattern_type: str
    prompt_keyword: str
    solution_summary: str
    use_count: int
    last_seen: float

    @property
    def age_days(self) -> float:
        return (time.time() - self.last_seen) / 86400


# ---------------------------------------------------------------------------
# GlobalMemory
# ---------------------------------------------------------------------------

class GlobalMemory:
    """Manages cross-project patterns in a single user-level SQLite database."""

    def __init__(self, db_path: Path | None = None, cache_capacity: int = 500) -> None:
        self.db_path = db_path or _GLOBAL_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = LRUPatternCache(capacity=cache_capacity)
        self._init_db()

    # ------------------------------------------------------------------
    # DB setup
    # ------------------------------------------------------------------

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
                CREATE TABLE IF NOT EXISTS patterns (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    framework     TEXT NOT NULL DEFAULT '',
                    pattern_type  TEXT NOT NULL DEFAULT '',
                    prompt_keyword TEXT NOT NULL,
                    solution_summary TEXT NOT NULL,
                    use_count     INTEGER NOT NULL DEFAULT 1,
                    last_seen     REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_patterns_keyword
                    ON patterns(prompt_keyword);
                CREATE INDEX IF NOT EXISTS idx_patterns_framework
                    ON patterns(framework);
                CREATE TABLE IF NOT EXISTS global_kv (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_pattern(
        self,
        framework: str,
        pattern_type: str,
        keyword: str,
        solution: str,
    ) -> None:
        """Store or update a cross-project solution pattern.

        If a pattern with the same (framework, pattern_type, keyword) already exists,
        its use_count is incremented and solution_summary updated.
        """
        keyword = keyword.lower().strip()[:100]
        solution = solution.strip()[:500]
        framework = framework.lower().strip()[:50]
        pattern_type = pattern_type.lower().strip()[:50]

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM patterns WHERE framework=? AND pattern_type=? AND prompt_keyword=?",
                (framework, pattern_type, keyword),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE patterns SET use_count=use_count+1, solution_summary=?, last_seen=? WHERE id=?",
                    (solution, time.time(), existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO patterns (framework, pattern_type, prompt_keyword, solution_summary, use_count, last_seen) "
                    "VALUES (?, ?, ?, ?, 1, ?)",
                    (framework, pattern_type, keyword, solution, time.time()),
                )
        self._cache.clear()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall_patterns(
        self,
        prompt: str,
        frameworks: list[str] | None = None,
        limit: int = 5,
    ) -> list[PatternRecord]:
        """Return the most relevant patterns for *prompt*.

        Matching is done by checking if any word from the prompt appears in
        prompt_keyword, filtered optionally by *frameworks*.
        """
        words = [w.lower() for w in prompt.split() if len(w) >= 3]
        if not words:
            return []

        with self._conn() as conn:
            clauses = " OR ".join(["LOWER(prompt_keyword) LIKE ?" for _ in words])
            params: list[Any] = [f"%{w}%" for w in words]

            if frameworks:
                fw_lower = [f.lower() for f in frameworks]
                fw_clause = " OR ".join(["framework=?" for _ in fw_lower])
                query = (
                    f"SELECT * FROM patterns WHERE ({clauses}) AND ({fw_clause}) "
                    f"ORDER BY use_count DESC LIMIT ?"
                )
                params += fw_lower + [limit * 3]
            else:
                query = (
                    f"SELECT * FROM patterns WHERE ({clauses}) "
                    f"ORDER BY use_count DESC LIMIT ?"
                )
                params.append(limit * 3)

            rows = conn.execute(query, params).fetchall()

        # Re-rank by keyword overlap
        def _score(row: sqlite3.Row) -> int:
            kw = row["prompt_keyword"].lower()
            return sum(1 for w in words if w in kw)

        ranked = sorted(rows, key=_score, reverse=True)[:limit]
        return [
            PatternRecord(
                id=r["id"],
                framework=r["framework"],
                pattern_type=r["pattern_type"],
                prompt_keyword=r["prompt_keyword"],
                solution_summary=r["solution_summary"],
                use_count=r["use_count"],
                last_seen=r["last_seen"],
            )
            for r in ranked
        ]

    def build_global_hint(
        self,
        prompt: str,
        frameworks: list[str] | None = None,
    ) -> str:
        """Return a formatted hint string for injection into the agent system prompt."""
        patterns = self.recall_patterns(prompt, frameworks)
        if not patterns:
            return ""
        lines = ["GLOBAL PATTERNS (from past projects — apply if relevant):"]
        for p in patterns:
            fw_tag = f"[{p.framework}] " if p.framework else ""
            lines.append(f"  • {fw_tag}{p.pattern_type}: {p.solution_summary} (used {p.use_count}×)")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Key-value helpers
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO global_kv (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )

    def get(self, key: str, default: Any = None) -> Any:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM global_kv WHERE key=?", (key,)).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def consolidate_patterns(self, similarity_threshold: float = 0.8) -> int:
        """Consolidate highly similar patterns (Jaccard similarity on prompt_keyword).

        Merges duplicates by combining use_count into the pattern with highest use_count.
        Returns count of merged pattern entries deleted.
        """
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM patterns ORDER BY use_count DESC").fetchall()
            records = [
                PatternRecord(
                    id=r["id"], framework=r["framework"], pattern_type=r["pattern_type"],
                    prompt_keyword=r["prompt_keyword"], solution_summary=r["solution_summary"],
                    use_count=r["use_count"], last_seen=r["last_seen"],
                )
                for r in rows
            ]

            merged_ids: set[int] = set()
            for i in range(len(records)):
                if records[i].id in merged_ids:
                    continue
                kw_i = set(records[i].prompt_keyword.lower().split())
                if not kw_i:
                    continue
                for j in range(i + 1, len(records)):
                    if records[j].id in merged_ids:
                        continue
                    if records[i].framework != records[j].framework:
                        continue
                    kw_j = set(records[j].prompt_keyword.lower().split())
                    if not kw_j:
                        continue
                    jaccard = len(kw_i & kw_j) / float(len(kw_i | kw_j))
                    if jaccard >= similarity_threshold:
                        # Merge j into i
                        conn.execute(
                            "UPDATE patterns SET use_count = use_count + ? WHERE id = ?",
                            (records[j].use_count, records[i].id),
                        )
                        conn.execute("DELETE FROM patterns WHERE id = ?", (records[j].id,))
                        merged_ids.add(records[j].id)

        self._cache.clear()
        return len(merged_ids)

    def stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
            frameworks = conn.execute(
                "SELECT framework, COUNT(*) AS cnt FROM patterns GROUP BY framework ORDER BY cnt DESC"
            ).fetchall()
        return {
            "total_patterns": total,
            "frameworks": {r["framework"]: r["cnt"] for r in frameworks},
            "db_path": str(self.db_path),
        }
