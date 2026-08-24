"""AgentMemoryGraph — Persistent Semantic Knowledge Base & Learning System.

Records every task, code change, error fix, architectural decision (ADR), and
agent insight into a SQLite-backed semantic graph. The agent learns from its own
history — every subsequent run starts smarter than the last.

Far beyond Cursor/OpenClaw: those reset each session. Vibe Studio accumulates
cross-session knowledge and surfaces relevant past decisions automatically.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Generator, Iterator


class MemoryKind(str, Enum):
    TASK_COMPLETED   = "TASK_COMPLETED"
    ERROR_FIXED      = "ERROR_FIXED"
    CODE_PATTERN     = "CODE_PATTERN"
    ADR              = "ADR"           # Architecture Decision Record
    TOOL_USAGE       = "TOOL_USAGE"
    USER_PREFERENCE  = "USER_PREFERENCE"
    BUG_SIGNATURE    = "BUG_SIGNATURE"
    WORKFLOW_RUN     = "WORKFLOW_RUN"
    INSIGHT          = "INSIGHT"


@dataclass
class MemoryEntry:
    id: str
    kind: MemoryKind
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    relevance_score: float = 0.0
    access_count: int = 0

    @property
    def age_hours(self) -> float:
        return (time.time() - self.timestamp) / 3600.0


@dataclass
class ADRRecord:
    """Architecture Decision Record — documents a significant technical decision."""
    title: str
    context: str
    decision: str
    consequences: str
    status: str = "accepted"
    tags: list[str] = field(default_factory=list)


class AgentMemoryGraph:
    """
    Cross-session persistent knowledge graph.

    Stores everything the agent has learned: task outcomes, error patterns, ADRs,
    user preferences, and code insights — indexed for fast similarity search.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata TEXT NOT NULL,
        tags TEXT NOT NULL,
        timestamp REAL NOT NULL,
        access_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS adrs (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        context TEXT NOT NULL,
        decision TEXT NOT NULL,
        consequences TEXT NOT NULL,
        status TEXT NOT NULL,
        tags TEXT NOT NULL,
        timestamp REAL NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
    CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_adrs_ts ON adrs(timestamp DESC);
    """

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self._db_dir = self.workspace_root / ".vibe_studio"
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._db_dir / "memory_graph.db"
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(self._SCHEMA)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _make_id(self, content: str) -> str:
        return hashlib.sha256(f"{time.time()}{content}".encode()).hexdigest()[:16]

    # ──────────────────────────────────────────────────────────────────────────
    # Write / Record
    # ──────────────────────────────────────────────────────────────────────────

    def record(self, kind: MemoryKind, content: str, metadata: dict[str, Any] | None = None, tags: list[str] | None = None) -> str:
        """Record a new memory entry and return its ID."""
        entry_id = self._make_id(content)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memories (id, kind, content, metadata, tags, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (entry_id, kind.value, content, json.dumps(metadata or {}), json.dumps(tags or []), time.time()),
            )
        return entry_id

    def record_task_completed(self, prompt: str, files_changed: list[str], quality_score: int = 0) -> str:
        return self.record(
            MemoryKind.TASK_COMPLETED,
            content=prompt,
            metadata={"files_changed": files_changed, "quality_score": quality_score},
            tags=["task"] + [Path(f).suffix.lstrip(".") for f in files_changed],
        )

    def record_error_fix(self, error_msg: str, fix_applied: str, file_path: str = "") -> str:
        return self.record(
            MemoryKind.ERROR_FIXED,
            content=f"ERROR: {error_msg}\nFIX: {fix_applied}",
            metadata={"error": error_msg, "fix": fix_applied, "file": file_path},
            tags=["error", "fix"] + ([Path(file_path).suffix.lstrip(".")] if file_path else []),
        )

    def record_code_pattern(self, pattern_name: str, example_code: str, language: str = "python") -> str:
        return self.record(
            MemoryKind.CODE_PATTERN,
            content=f"PATTERN: {pattern_name}\n```{language}\n{example_code}\n```",
            metadata={"pattern": pattern_name, "language": language},
            tags=["pattern", language],
        )

    def record_adr(self, adr: ADRRecord) -> str:
        """Persist an Architecture Decision Record."""
        adr_id = self._make_id(adr.title)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO adrs (id, title, context, decision, consequences, status, tags, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (adr_id, adr.title, adr.context, adr.decision, adr.consequences, adr.status, json.dumps(adr.tags), time.time()),
            )
        return adr_id

    def record_user_preference(self, preference: str, value: Any) -> str:
        return self.record(
            MemoryKind.USER_PREFERENCE,
            content=f"{preference}: {value}",
            metadata={"preference": preference, "value": value},
            tags=["preference"],
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Read / Retrieve
    # ──────────────────────────────────────────────────────────────────────────

    def search(self, query: str, kind: MemoryKind | None = None, limit: int = 10) -> list[MemoryEntry]:
        """Search memories by keyword and optional kind filter."""
        q = f"%{query.lower()}%"
        with self._connect() as conn:
            if kind:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE kind = ? AND (LOWER(content) LIKE ? OR LOWER(tags) LIKE ?) ORDER BY timestamp DESC LIMIT ?",
                    (kind.value, q, q, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE LOWER(content) LIKE ? OR LOWER(tags) LIKE ? ORDER BY timestamp DESC LIMIT ?",
                    (q, q, limit),
                ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_recent(self, limit: int = 20, kind: MemoryKind | None = None) -> list[MemoryEntry]:
        """Return most recent memory entries."""
        with self._connect() as conn:
            if kind:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE kind = ? ORDER BY timestamp DESC LIMIT ?",
                    (kind.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_similar_errors(self, error_msg: str, limit: int = 5) -> list[MemoryEntry]:
        """Retrieve past error fixes similar to the current error."""
        words = error_msg.lower().split()[:5]
        results = []
        for word in words:
            results.extend(self.search(word, kind=MemoryKind.ERROR_FIXED, limit=limit))
        seen = set()
        unique = [e for e in results if not (e.id in seen or seen.add(e.id))]
        return unique[:limit]

    def get_relevant_context(self, task_prompt: str, limit: int = 5) -> str:
        """Compose a concise context block from past relevant memories."""
        words = task_prompt.lower().split()[:8]
        entries: list[MemoryEntry] = []
        for word in words:
            entries.extend(self.search(word, limit=3))
        seen: set[str] = set()
        unique = [e for e in entries if not (e.id in seen or seen.add(e.id))][:limit]
        if not unique:
            return ""

        parts = ["## Relevant Past Knowledge (from Agent Memory Graph):"]
        for e in unique:
            parts.append(f"- [{e.kind.value}] {e.content[:200]}")
        return "\n".join(parts)

    def get_adrs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent Architecture Decision Records."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM adrs ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "context": r["context"],
                "decision": r["decision"],
                "consequences": r["consequences"],
                "status": r["status"],
                "tags": json.loads(r["tags"]),
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    def stats(self) -> dict[str, Any]:
        """Return memory graph statistics."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            adr_count = conn.execute("SELECT COUNT(*) FROM adrs").fetchone()[0]
            by_kind = conn.execute(
                "SELECT kind, COUNT(*) as cnt FROM memories GROUP BY kind"
            ).fetchall()
        return {
            "total_memories": total,
            "adrs": adr_count,
            "by_kind": {r["kind"]: r["cnt"] for r in by_kind},
        }

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            kind=MemoryKind(row["kind"]),
            content=row["content"],
            metadata=json.loads(row["metadata"]),
            tags=json.loads(row["tags"]),
            timestamp=row["timestamp"],
            access_count=row["access_count"],
        )
