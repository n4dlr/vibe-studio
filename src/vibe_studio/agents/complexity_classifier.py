"""Complexity Classifier — 3-tier task complexity routing for Adaptive Turbo Mode.

Sütun 5 (Adaptive Turbo Mode):
  Classifies a user prompt into one of three complexity tiers:

    FAST   — Single-file, surgical change (typo fix, rename, add comment).
              Skips RAG + Graph expansion. Target latency: < 2 seconds overhead.

    NORMAL — Multi-file change, well-bounded scope (add endpoint, write tests).
              Standard pipeline: RAG + LSP context, no MoA.

    DEEP   — Architectural change, refactoring, new feature spanning many files.
              Full pipeline: Graph RAG + LSP + MoA consensus judge.

Usage::

    cls = ComplexityClassifier()
    tier = cls.classify("fix typo in README")          # → TaskComplexity.FAST
    tier = cls.classify("add login endpoint to api")   # → TaskComplexity.NORMAL
    tier = cls.classify("refactor entire auth system") # → TaskComplexity.DEEP
"""
from __future__ import annotations

import re
from enum import Enum, auto
from pathlib import Path

# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

class TaskComplexity(Enum):
    FAST   = auto()   # sub-second overhead — skip RAG/Graph
    NORMAL = auto()   # standard pipeline
    DEEP   = auto()   # full Graph RAG + MoA


# ---------------------------------------------------------------------------
# Keyword heuristics
# ---------------------------------------------------------------------------

_FAST_KEYWORDS: frozenset[str] = frozenset({
    "fix typo", "rename", "add comment", "update docstring", "format",
    "indent", "whitespace", "spelling", "wording", "tweak", "minor",
    "one line", "single line", "quick fix", "small fix", "correct",
    "remove line", "delete line", "add line", "change variable",
    "update string", "update message", "change text", "edit",
})

_NORMAL_KEYWORDS: frozenset[str] = frozenset({
    "add", "implement", "create", "write", "endpoint", "function",
    "method", "class", "unit test", "test", "feature", "handler",
    "route", "model", "schema", "component", "hook", "util", "helper",
    "parse", "validate", "check", "update", "modify",
})

_DEEP_KEYWORDS: frozenset[str] = frozenset({
    "refactor", "rewrite", "redesign", "architect", "restructure",
    "migration", "migrate", "overhaul", "entire", "whole", "all",
    "system", "framework", "module", "package", "codebase", "project",
    "performance", "optimize entire", "split into", "extract service",
    "decouple", "monorepo", "pipeline",
})

_DEEP_PATTERN = re.compile(
    r"\b(refactor|rewrite|redesign|architect|restructure|overhaul|migrate|"
    r"entire|whole|codebase|system.wide|across.the)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# ComplexityClassifier
# ---------------------------------------------------------------------------

class ComplexityClassifier:
    """Heuristic-based task complexity classifier."""

    def classify(
        self,
        prompt: str,
        active_file: str | None = None,
        project_file_count: int = 0,
    ) -> TaskComplexity:
        """Return the complexity tier for *prompt*.

        Args:
            prompt            : User task description.
            active_file       : Currently open file (hint for single-file tasks).
            project_file_count: Total files in project (large repo → NORMAL floor).
        """
        prompt_lower = prompt.lower().strip()
        word_count = len(prompt_lower.split())

        # ── DEEP heuristics ──────────────────────────────────────────────
        if _DEEP_PATTERN.search(prompt_lower):
            return TaskComplexity.DEEP

        deep_hits = sum(1 for kw in _DEEP_KEYWORDS if kw in prompt_lower)
        if deep_hits >= 2:
            return TaskComplexity.DEEP

        # Very long prompts often describe complex tasks
        if word_count > 50:
            return TaskComplexity.DEEP

        # ── FAST heuristics ──────────────────────────────────────────────
        fast_hits = sum(1 for kw in _FAST_KEYWORDS if kw in prompt_lower)

        # Short prompt with any fast keyword → always FAST (active_file optional)
        if fast_hits >= 1 and word_count <= 10:
            return TaskComplexity.FAST

        # Single explicit file reference + fast keyword → FAST
        if fast_hits >= 1 and active_file:
            file_refs = re.findall(r'[\w/\-]+\.\w{1,6}', prompt_lower)
            if len(file_refs) <= 1:
                return TaskComplexity.FAST

        if fast_hits >= 2 and word_count <= 15:
            return TaskComplexity.FAST

        # Very short prompts with a known active file
        if word_count <= 8 and active_file:
            return TaskComplexity.FAST

        # ── NORMAL (default) ─────────────────────────────────────────────
        return TaskComplexity.NORMAL

    def describe(self, complexity: TaskComplexity) -> str:
        """Return a human-readable description of the complexity tier."""
        descriptions = {
            TaskComplexity.FAST: (
                "⚡ FAST — Single-file surgical change. "
                "RAG and Graph expansion skipped for minimum latency."
            ),
            TaskComplexity.NORMAL: (
                "🔄 NORMAL — Multi-file bounded task. "
                "Standard RAG + LSP context pipeline."
            ),
            TaskComplexity.DEEP: (
                "🧠 DEEP — Architectural / cross-cutting change. "
                "Full Graph RAG + LSP + MoA consensus active."
            ),
        }
        return descriptions[complexity]
