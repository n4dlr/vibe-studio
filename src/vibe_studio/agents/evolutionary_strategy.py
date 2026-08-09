"""Evolutionary Agent Strategy — roulette-wheel strategy selection based on past success.

Sütun 2 (Evolutionary Agent):
  - AgentStrategy  : dataclass representing a specific agent execution configuration.
  - StrategyPool   : loads past successful strategies from ProjectMemory, selects via
                     fitness-proportionate (roulette-wheel) sampling, and evolves winners.

Usage::

    pool = StrategyPool(project_memory)
    strategy = pool.select(prompt="refactor auth module")
    # ... run agent with strategy ...
    pool.evolve(strategy, score=85, prompt="refactor auth module")
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibe_studio.core.project_memory import ProjectMemory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AgentStrategy
# ---------------------------------------------------------------------------

@dataclass
class AgentStrategy:
    """Execution configuration that an agent will use for a task."""

    rag_enabled: bool = True
    graph_expand: bool = False
    temperature_bias: float = 0.0      # -0.3 (conservative) to +0.3 (creative)
    max_iterations: int = 5
    use_moa: bool = False
    turbo_mode: bool = False
    fitness: float = 50.0              # 0-100, updated by evolve()
    generation: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentStrategy":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def default(cls) -> "AgentStrategy":
        return cls()

    @classmethod
    def creative(cls) -> "AgentStrategy":
        """High-variance strategy — good for novel/complex tasks."""
        return cls(rag_enabled=True, graph_expand=True, temperature_bias=0.2,
                   max_iterations=7, use_moa=True, fitness=50.0)

    @classmethod
    def conservative(cls) -> "AgentStrategy":
        """Low-variance strategy — good for well-understood fixes."""
        return cls(rag_enabled=False, graph_expand=False, temperature_bias=-0.2,
                   max_iterations=3, turbo_mode=True, fitness=50.0)


# ---------------------------------------------------------------------------
# StrategyPool
# ---------------------------------------------------------------------------

_MEMORY_KEY_PREFIX = "strategy:"
_MAX_POOL_SIZE = 20
_DEFAULT_POOL = [
    AgentStrategy.default(),
    AgentStrategy.creative(),
    AgentStrategy.conservative(),
]


class StrategyPool:
    """Manages a population of strategies, selecting based on fitness and evolving winners."""

    def __init__(self, memory: "ProjectMemory | None" = None) -> None:
        self._memory = memory

    # ------------------------------------------------------------------
    # Prompt fingerprint (short hash for keying memory)
    # ------------------------------------------------------------------

    @staticmethod
    def _task_hash(prompt: str) -> str:
        words = sorted(set(prompt.lower().split()))[:8]
        return hashlib.md5(" ".join(words).encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Load / save from ProjectMemory
    # ------------------------------------------------------------------

    def _load_pool(self) -> list[AgentStrategy]:
        if self._memory is None:
            return list(_DEFAULT_POOL)
        raw = self._memory.get("strategy_pool", None)
        if not raw:
            return list(_DEFAULT_POOL)
        try:
            entries = json.loads(raw) if isinstance(raw, str) else raw
            pool = [AgentStrategy.from_dict(e) for e in entries if isinstance(e, dict)]
            return pool or list(_DEFAULT_POOL)
        except Exception:
            return list(_DEFAULT_POOL)

    def _save_pool(self, pool: list[AgentStrategy]) -> None:
        if self._memory is None:
            return
        try:
            trimmed = sorted(pool, key=lambda s: s.fitness, reverse=True)[:_MAX_POOL_SIZE]
            self._memory.remember("strategy_pool", [s.to_dict() for s in trimmed])
        except Exception as exc:
            logger.warning("StrategyPool: failed to save pool: %s", exc)

    # ------------------------------------------------------------------
    # Load task-specific winner
    # ------------------------------------------------------------------

    def _load_task_winner(self, prompt: str) -> AgentStrategy | None:
        if self._memory is None:
            return None
        key = f"{_MEMORY_KEY_PREFIX}{self._task_hash(prompt)}"
        raw = self._memory.get(key, None)
        if raw:
            try:
                d = json.loads(raw) if isinstance(raw, str) else raw
                return AgentStrategy.from_dict(d)
            except Exception:
                pass
        return None

    def _save_task_winner(self, prompt: str, strategy: AgentStrategy) -> None:
        if self._memory is None:
            return
        key = f"{_MEMORY_KEY_PREFIX}{self._task_hash(prompt)}"
        try:
            self._memory.remember(key, strategy.to_dict())
        except Exception as exc:
            logger.warning("StrategyPool: failed to save task winner: %s", exc)

    # ------------------------------------------------------------------
    # Select
    # ------------------------------------------------------------------

    def select(self, prompt: str) -> AgentStrategy:
        """Select a strategy for *prompt* using fitness-proportionate sampling.

        If a task-specific winner exists (same prompt fingerprint), it is returned
        directly. Otherwise, roulette-wheel selection is applied over the pool.
        """
        # 1. Task-specific winner
        winner = self._load_task_winner(prompt)
        if winner is not None:
            logger.debug("StrategyPool: reusing task-specific strategy (fitness=%.1f)", winner.fitness)
            return winner

        # 2. Roulette-wheel over pool
        pool = self._load_pool()
        total_fitness = sum(max(s.fitness, 1.0) for s in pool)
        r = random.uniform(0, total_fitness)
        cumulative = 0.0
        for strategy in pool:
            cumulative += max(strategy.fitness, 1.0)
            if r <= cumulative:
                logger.debug("StrategyPool: roulette selected strategy (fitness=%.1f)", strategy.fitness)
                return AgentStrategy.from_dict(strategy.to_dict())

        # Fallback
        return AgentStrategy.default()

    # ------------------------------------------------------------------
    # Evolve
    # ------------------------------------------------------------------

    def evolve(self, strategy: AgentStrategy, score: float, prompt: str) -> None:
        """Update strategy fitness from task *score* (0-100) and persist.

        Uses exponential moving average: new_fitness = 0.7 * old + 0.3 * score
        """
        old_fitness = strategy.fitness
        strategy.fitness = round(0.7 * old_fitness + 0.3 * score, 2)
        strategy.generation += 1

        logger.debug(
            "StrategyPool: evolved strategy %.1f -> %.1f (score=%.1f, gen=%d)",
            old_fitness, strategy.fitness, score, strategy.generation,
        )

        # Save as task-specific winner if fitness improved
        if strategy.fitness >= old_fitness:
            self._save_task_winner(prompt, strategy)

        # Update global pool
        pool = self._load_pool()
        # Replace worst-fitness entry if pool is full and new strategy is better
        if len(pool) >= _MAX_POOL_SIZE:
            worst_idx = min(range(len(pool)), key=lambda i: pool[i].fitness)
            if strategy.fitness > pool[worst_idx].fitness:
                pool[worst_idx] = strategy
        else:
            pool.append(strategy)
        self._save_pool(pool)
