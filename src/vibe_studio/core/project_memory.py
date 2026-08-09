"""ProjectMemory — SQLite-backed persistent project knowledge base.

Tables:
  tasks      — completed agent tasks with prompt, files, status, timestamp
  learnings  — patterns extracted from task outcomes
  errors     — error fingerprints + fixes applied
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)


@dataclass
class ProjectMemoryData:
    architecture: str = ""
    frameworks: list[str] = field(default_factory=list)
    build_system: str = ""
    test_framework: str = ""
    conventions: list[str] = field(default_factory=list)
    recent_modifications: list[dict[str, Any]] = field(default_factory=list)
    custom_notes: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskRecord:
    prompt: str
    status: str
    files_changed: list[str]
    summary: str
    timestamp: float
    error: str = ""
    id: int = 0


@dataclass
class ErrorRecord:
    file_path: str
    error_type: str
    error_message: str
    fix_applied: str
    timestamp: float
    id: int = 0


class ProjectMemory:
    """Manages project-specific metadata and decisions via SQLite (.vibe_studio/memory.db)."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        db_dir = self.project_root / ".vibe_studio"
        db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_dir / "memory.db"
        self._legacy_json = self.project_root / ".vibe_studio_memory.json"
        self._init_db()
        self._migrate_legacy()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    files_changed TEXT NOT NULL DEFAULT '[]',
                    summary TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    timestamp REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL DEFAULT '',
                    error_type TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL,
                    fix_applied TEXT NOT NULL DEFAULT '',
                    timestamp REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_timestamp ON tasks(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_errors_file ON errors(file_path);
            """)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _migrate_legacy(self) -> None:
        if not self._legacy_json.exists():
            return
        try:
            data = json.loads(self._legacy_json.read_text(encoding="utf-8"))
            for mod in data.get("recent_modifications", []):
                self.remember_task(
                    prompt=f"[migrated] {mod.get('action', 'edit')} {mod.get('file', '')}",
                    status="completed",
                    files_changed=[mod.get("file", "")],
                    summary=mod.get("summary", ""),
                )
            for k, v in data.get("custom_notes", {}).items():
                self.remember(k, v)
            self._legacy_json.rename(self._legacy_json.with_suffix(".json.bak"))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Task history
    # ------------------------------------------------------------------

    # remember_task is defined at the bottom of the class with GlobalMemory integration (Sütun 7)

    def recall_similar(self, prompt: str, limit: int = 3) -> list[TaskRecord]:
        words = [w.lower() for w in prompt.split() if len(w) > 3]
        if not words:
            return []
        with self._conn() as conn:
            clauses = " OR ".join(["LOWER(prompt) LIKE ?" for _ in words])
            params = [f"%{w}%" for w in words]
            params.append(limit * 4)
            rows = conn.execute(
                f"SELECT * FROM tasks WHERE ({clauses}) ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
        if not rows:
            return []

        def _score(row) -> int:
            p = row["prompt"].lower()
            return sum(1 for w in words if w in p)

        ranked = sorted(rows, key=_score, reverse=True)[:limit]
        return [
            TaskRecord(
                id=r["id"], prompt=r["prompt"], status=r["status"],
                files_changed=json.loads(r["files_changed"] or "[]"),
                summary=r["summary"], error=r["error"], timestamp=r["timestamp"],
            )
            for r in ranked
        ]

    def get_recent_tasks(self, limit: int = 10) -> list[TaskRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY id ASC LIMIT ?", (limit,)
            ).fetchall()
        return [
            TaskRecord(
                id=r["id"], prompt=r["prompt"], status=r["status"],
                files_changed=json.loads(r["files_changed"] or "[]"),
                summary=r["summary"], error=r["error"], timestamp=r["timestamp"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Error tracking
    # ------------------------------------------------------------------

    def record_error_fix(
        self,
        file_path: str,
        error_type: str,
        error_message: str,
        fix_applied: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO errors (file_path, error_type, error_message, fix_applied, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (file_path, error_type, error_message[:500], fix_applied[:500], time.time()),
            )

    def recall_error_fixes(self, error_type: str, limit: int = 3) -> list[ErrorRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM errors WHERE error_type=? ORDER BY timestamp DESC LIMIT ?",
                (error_type, limit),
            ).fetchall()
        return [
            ErrorRecord(
                id=r["id"], file_path=r["file_path"], error_type=r["error_type"],
                error_message=r["error_message"], fix_applied=r["fix_applied"],
                timestamp=r["timestamp"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Key-value store (backwards-compatible)
    # ------------------------------------------------------------------

    def remember(self, key: str, value: Any) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )

    def get(self, key: str, default: Any = None) -> Any:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default

    def load(self) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM kv").fetchall()
        result: dict[str, Any] = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except Exception:
                result[r["key"]] = r["value"]
        result["recent_modifications"] = [
            {"file": t.files_changed[0] if t.files_changed else "", "summary": t.summary}
            for t in self.get_recent_tasks(50)
        ]
        return result

    def save(self, data: dict[str, Any]) -> None:
        for k, v in data.items():
            if k != "recent_modifications":
                self.remember(k, v)

    def record_modification(self, file_path: str, action: str, summary: str) -> None:
        self.remember_task(
            prompt=f"{action}: {file_path}",
            status="completed",
            files_changed=[file_path],
            summary=summary,
        )

    def build_context_hint(self, prompt: str) -> str:
        """Generate a memory hint string for injection into agent system prompt.

        Combines project-local similar tasks with cross-project global patterns (Sütun 7).
        """
        similar = self.recall_similar(prompt, limit=3)
        lines: list[str] = []
        if similar:
            lines.append("PAST EXPERIENCE (similar tasks from project history):")
            for t in similar:
                status_icon = "✓" if t.status == "completed" else "✗"
                lines.append(f"  {status_icon} [{t.status}] {t.prompt[:100]}")
                if t.summary:
                    lines.append(f"     → {t.summary[:120]}")
                if t.error:
                    lines.append(f"     ⚠ Error was: {t.error[:80]}")

        # Sütun 7: append cross-project global patterns
        try:
            from vibe_studio.core.global_memory import GlobalMemory
            gm = GlobalMemory()
            global_hint = gm.build_global_hint(prompt)
            if global_hint:
                lines.append("")
                lines.append(global_hint)
        except Exception as exc:
            logger.debug("GlobalMemory hint skipped: %s", exc)

        return "\n".join(lines)

    def remember_task(
        self,
        prompt: str,
        status: str = "completed",
        files_changed: list[str] | None = None,
        summary: str = "",
        error: str = "",
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (prompt, status, files_changed, summary, error, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (prompt, status, json.dumps(files_changed or []), summary, error, time.time()),
            )
            task_id = cur.lastrowid or 0

        # Sütun 7: record successful patterns to global memory
        if status == "completed" and summary:
            try:
                from vibe_studio.core.global_memory import GlobalMemory
                gm = GlobalMemory()
                # Infer a generic keyword from the first 3 meaningful words of prompt
                words = [w.lower() for w in prompt.split() if len(w) >= 3][:3]
                keyword = " ".join(words) if words else prompt[:30].lower()
                gm.record_pattern(
                    framework="",
                    pattern_type="task",
                    keyword=keyword,
                    solution=summary[:300],
                )
            except Exception as exc:
                logger.debug("GlobalMemory record skipped: %s", exc)

        return task_id
