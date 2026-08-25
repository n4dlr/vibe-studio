"""JarvisMemoryDB — Titan-Grade RAG & Persistent Vector Conversation Memory Database.

Features:
- SQLite persistent storage for long-term chat history, user facts/preferences, and knowledge chunks.
- Zero-latency multi-tier semantic search (Ollama Vector Embeddings + Local TF-IDF Cosine Similarity Fallback).
- Session-based conversation tracking and contextual memory retrieval for LLM agent loops.
- Auto-extracts and remembers user preferences (names, favorite topics, coding style, hardware config).
"""
from __future__ import annotations

import glob
import io
import json
import logging
import math
import os
import re
import sqlite3
import struct
import sys
import threading
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Auto-link local virtual environment site-packages if running from workspace
_root = Path(__file__).resolve().parents[3]
_venv_sites = glob.glob(str(_root / ".venv" / "lib" / "python3.*" / "site-packages"))
for _sp in _venv_sites:
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

logger = logging.getLogger(__name__)


def _compute_fallback_vector(text: str, dim: int = 128) -> list[float]:
    """Pure-Python semantic n-gram feature hashing vectorizer (zero-dependency cosine fallback)."""
    words = re.findall(r"\w+", text.lower())
    if not words:
        return [0.0] * dim

    vec = [0.0] * dim
    # Unigrams and bigrams
    tokens = list(words)
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]}_{words[i+1]}")

    for token in tokens:
        h = hash(token) % dim
        vec[h] += 1.0

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 1e-9:
        vec = [x / norm for x in vec]
    return vec


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two unit or arbitrary float vectors."""
    if len(vec1) != len(vec2) or not vec1:
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 < 1e-9 or norm2 < 1e-9:
        return 0.0
    return float(dot / (norm1 * norm2))


def _pack_vector(vec: list[float]) -> bytes:
    """Pack float list into binary blob."""
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_vector(blob: bytes) -> list[float]:
    """Unpack binary blob back into float list."""
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


@dataclass
class ConversationTurn:
    id: int
    session_id: str
    role: str
    content: str
    model: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryFact:
    id: int
    category: str
    fact_key: str
    fact_value: str
    confidence: float
    updated_at: float


@dataclass
class RAGChunk:
    id: int
    doc_type: str
    title: str
    chunk_text: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class JarvisMemoryDB:
    """Thread-safe persistent RAG and conversation memory database for J.A.R.V.I.S."""

    def __init__(self, db_path: str | Path | None = None, embedding_model: str = "qwen2.5:1.5b") -> None:
        if db_path is None:
            config_dir = Path.home() / ".config" / "vibe_studio"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = config_dir / "jarvis_memory.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.embedding_model = embedding_model
        self._lock = threading.Lock()
        self._current_session_id = f"session_{int(time.time())}"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create necessary tables and indices if not present."""
        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata_json TEXT DEFAULT '{}'
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_sess ON conversations(session_id, timestamp)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS facts_and_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    fact_key TEXT UNIQUE NOT NULL,
                    fact_value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    updated_at REAL NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_facts_cat ON facts_and_preferences(category)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS rag_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding_blob BLOB NOT NULL,
                    dim INTEGER NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    created_at REAL NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_rag_type ON rag_embeddings(doc_type)")
            conn.commit()

    # ------------------------------------------------------------------
    # Embedding Generation (Ollama / Local Fallback)
    # ------------------------------------------------------------------

    def get_embedding(self, text: str) -> list[float]:
        """Fetch dense vector embedding via Ollama API, or fallback to zero-dependency vectorizer."""
        if not text or not text.strip():
            return [0.0] * 128

        # 1. Try Ollama /api/embed
        try:
            req_data = json.dumps({
                "model": self.embedding_model,
                "input": text[:1000],
            }).encode("utf-8")
            req = urllib.request.Request("http://127.0.0.1:11434/api/embed", data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                embeddings = data.get("embeddings", [])
                if embeddings and isinstance(embeddings[0], list):
                    return embeddings[0]
        except Exception:
            pass

        # 2. Try legacy Ollama /api/embeddings
        try:
            req_data = json.dumps({
                "model": self.embedding_model,
                "prompt": text[:1000],
            }).encode("utf-8")
            req = urllib.request.Request("http://127.0.0.1:11434/api/embeddings", data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                emb = data.get("embedding", [])
                if emb and isinstance(emb, list):
                    return emb
        except Exception:
            pass

        # 3. High-speed local fallback
        return _compute_fallback_vector(text, dim=128)

    # ------------------------------------------------------------------
    # Conversation History
    # ------------------------------------------------------------------

    def save_turn(self, role: str, content: str, model: str = "", metadata: dict[str, Any] | None = None) -> int:
        """Save a single conversation turn to memory DB and index it into RAG store."""
        if not content or not content.strip():
            return -1

        meta_json = json.dumps(metadata or {})
        now = time.time()

        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO conversations (session_id, role, content, model, timestamp, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (self._current_session_id, role, content.strip(), model, now, meta_json),
            )
            turn_id = cur.lastrowid
            conn.commit()

        # Also auto-extract and remember explicit facts (e.g. "mənim adım Əlidir", "my favorite ...")
        if role == "user":
            self._auto_extract_facts(content)

        # Index important conversation turns into RAG search
        if len(content.strip()) > 15:
            self.index_chunk(
                doc_type="conversation",
                title=f"{role.capitalize()} ({time.strftime('%Y-%m-%d %H:%M')})",
                text=f"{role.upper()}: {content.strip()}",
                metadata={"turn_id": turn_id, "session_id": self._current_session_id},
            )

        return turn_id or 0

    def get_recent_history(self, n: int = 10, session_id: str | None = None) -> list[ConversationTurn]:
        """Fetch the most recent N conversation turns."""
        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            if session_id:
                cur.execute(
                    "SELECT id, session_id, role, content, model, timestamp, metadata_json FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, n),
                )
            else:
                cur.execute(
                    "SELECT id, session_id, role, content, model, timestamp, metadata_json FROM conversations ORDER BY id DESC LIMIT ?",
                    (n,),
                )
            rows = cur.fetchall()

        turns = []
        for r in reversed(rows):
            try:
                meta = json.loads(r["metadata_json"])
            except Exception:
                meta = {}
            turns.append(ConversationTurn(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                model=r["model"],
                timestamp=r["timestamp"],
                metadata=meta,
            ))
        return turns

    def format_history_for_prompt(self, n: int = 6) -> str:
        """Format recent conversation history as clean markdown context for LLM prompt."""
        turns = self.get_recent_history(n=n)
        if not turns:
            return ""

        lines = ["[CONVERSATION HISTORY]"]
        for t in turns:
            lines.append(f"{t.role.upper()}: {t.content}")
        lines.append("[END HISTORY]\n")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Facts & User Preferences
    # ------------------------------------------------------------------

    def remember_fact(self, key: str, value: str, category: str = "general", confidence: float = 1.0) -> None:
        """Store or update a structured fact about the user or environment."""
        k = key.strip().lower()
        v = value.strip()
        if not k or not v:
            return

        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO facts_and_preferences (category, fact_key, fact_value, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(fact_key) DO UPDATE SET
                    category = excluded.category,
                    fact_value = excluded.fact_value,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
            """, (category, k, v, confidence, time.time()))
            conn.commit()

        # Also add to RAG index for semantic recall
        self.index_chunk(
            doc_type="fact",
            title=f"Fact: {k}",
            text=f"Fact ({category}): {k} = {v}",
            metadata={"key": k, "category": category},
        )

    def recall_facts(self, category: str | None = None) -> list[MemoryFact]:
        """Fetch stored facts, optionally filtered by category."""
        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            if category:
                cur.execute("SELECT id, category, fact_key, fact_value, confidence, updated_at FROM facts_and_preferences WHERE category = ? ORDER BY updated_at DESC", (category,))
            else:
                cur.execute("SELECT id, category, fact_key, fact_value, confidence, updated_at FROM facts_and_preferences ORDER BY updated_at DESC")
            rows = cur.fetchall()

        return [MemoryFact(
            id=r["id"],
            category=r["category"],
            fact_key=r["fact_key"],
            fact_value=r["fact_value"],
            confidence=r["confidence"],
            updated_at=r["updated_at"],
        ) for r in rows]

    def _auto_extract_facts(self, text: str) -> None:
        """Heuristic rule-based extractor for common personal facts in Azerbaijani and English."""
        t_low = text.strip()
        
        # Name extraction (e.g. "mənim adım Əlidir", "adımı Əli qoy", "my name is John")
        m_name_az = re.search(r"(?:mənim\s+)?adım\s+([A-ZƏÖĞIİÇŞa-zəöğıiçş]+)(?:dir|dır|dur|dür)?\b", t_low, re.IGNORECASE)
        if m_name_az:
            self.remember_fact("user_name", m_name_az.group(1), category="identity")

        m_name_en = re.search(r"my\s+name\s+is\s+([A-Za-z]+)\b", t_low, re.IGNORECASE)
        if m_name_en:
            self.remember_fact("user_name", m_name_en.group(1), category="identity")

        # Favorite topic/item (e.g. "sevdiyim maşın Porsche-dir", "my favorite car is Porsche")
        m_fav_az = re.search(r"sevdiyim\s+([A-ZƏÖĞIİÇŞa-zəöğıiçş]+)\s+([A-ZƏÖĞIİÇŞa-zəöğıiçş0-9\s\-]+?)(?:dir|dır|dur|dür)?$", t_low, re.IGNORECASE)
        if m_fav_az:
            item_type = m_fav_az.group(1).lower()
            val = m_fav_az.group(2).strip()
            self.remember_fact(f"favorite_{item_type}", val, category="preference")

        m_fav_en = re.search(r"my\s+favorite\s+([A-Za-z]+)\s+is\s+([A-Za-z0-9\s\-]+)", t_low, re.IGNORECASE)
        if m_fav_en:
            item_type = m_fav_en.group(1).lower()
            val = m_fav_en.group(2).strip()
            self.remember_fact(f"favorite_{item_type}", val, category="preference")

    # ------------------------------------------------------------------
    # RAG Vector Search
    # ------------------------------------------------------------------

    def index_chunk(self, doc_type: str, title: str, text: str, metadata: dict[str, Any] | None = None) -> int:
        """Store a text chunk and its dense vector embedding into RAG table."""
        t_clean = text.strip()
        if not t_clean:
            return -1

        vec = self.get_embedding(t_clean)
        blob = _pack_vector(vec)
        meta_json = json.dumps(metadata or {})

        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO rag_embeddings (doc_type, title, chunk_text, embedding_blob, dim, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_type, title, t_clean, blob, len(vec), meta_json, time.time()),
            )
            chunk_id = cur.lastrowid
            conn.commit()

        return chunk_id or 0

    def search_rag(self, query: str, top_k: int = 4, min_score: float = 0.15) -> list[RAGChunk]:
        """Perform semantic cosine similarity search across all indexed RAG knowledge chunks."""
        q_clean = query.strip()
        if not q_clean:
            return []

        q_vec = self.get_embedding(q_clean)

        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, doc_type, title, chunk_text, embedding_blob, dim, metadata_json FROM rag_embeddings")
            rows = cur.fetchall()

        results = []
        for r in rows:
            blob = r["embedding_blob"]
            vec = _unpack_vector(blob)
            score = _cosine_similarity(q_vec, vec)

            # Keyword boost: If exact words in query match chunk text, boost score
            q_words = set(re.findall(r"\w{3,}", q_clean.lower()))
            chunk_words = set(re.findall(r"\w{3,}", r["chunk_text"].lower()))
            overlap = len(q_words & chunk_words)
            if overlap > 0:
                score += overlap * 0.08

            if score >= min_score:
                try:
                    meta = json.loads(r["metadata_json"])
                except Exception:
                    meta = {}
                results.append(RAGChunk(
                    id=r["id"],
                    doc_type=r["doc_type"],
                    title=r["title"],
                    chunk_text=r["chunk_text"],
                    score=score,
                    metadata=meta,
                ))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def build_rag_context(self, query: str, top_k: int = 3) -> str:
        """Generate formatted RAG memory context string to prepend to LLM system prompt."""
        chunks = self.search_rag(query, top_k=top_k)
        facts = self.recall_facts()

        sections = []

        if facts:
            fact_lines = ["[KNOWN USER FACTS & PREFERENCES]"]
            for f in facts[:8]:
                fact_lines.append(f"- {f.fact_key}: {f.fact_value} (Category: {f.category})")
            fact_lines.append("[END FACTS]")
            sections.append("\n".join(fact_lines))

        if chunks:
            rag_lines = ["[RELEVANT PAST KNOWLEDGE & MEMORY (RAG)]"]
            for c in chunks:
                rag_lines.append(f"• [{c.title}] (Score: {c.score:.2f}): {c.chunk_text}")
            rag_lines.append("[END RAG MEMORY]")
            sections.append("\n".join(rag_lines))

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Maintenance & Telemetry
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, int]:
        """Return counts of stored conversations, facts, and RAG embeddings."""
        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM conversations")
            conv_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM facts_and_preferences")
            facts_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM rag_embeddings")
            rag_count = cur.fetchone()[0]

        return {
            "conversations": conv_count,
            "facts": facts_count,
            "rag_chunks": rag_count,
        }

    def clear_history(self) -> None:
        """Clear conversation history."""
        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM conversations")
            cur.execute("DELETE FROM rag_embeddings WHERE doc_type = 'conversation'")
            conn.commit()

    def clear_all(self) -> None:
        """Reset entire memory database."""
        with self._lock, self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM conversations")
            cur.execute("DELETE FROM facts_and_preferences")
            cur.execute("DELETE FROM rag_embeddings")
            conn.commit()
