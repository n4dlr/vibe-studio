"""Tests for EvolutionaryStrategy — AgentStrategy + StrategyPool."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibe_studio.agents.evolutionary_strategy import AgentStrategy, StrategyPool


class TestAgentStrategy:
    def test_default_strategy(self):
        s = AgentStrategy.default()
        assert s.rag_enabled is True
        assert 0 <= s.fitness <= 100

    def test_creative_strategy(self):
        s = AgentStrategy.creative()
        assert s.graph_expand is True
        assert s.use_moa is True
        assert s.temperature_bias > 0

    def test_conservative_strategy(self):
        s = AgentStrategy.conservative()
        assert s.turbo_mode is True
        assert s.temperature_bias < 0

    def test_roundtrip_dict(self):
        s = AgentStrategy.creative()
        d = s.to_dict()
        s2 = AgentStrategy.from_dict(d)
        assert s2.rag_enabled == s.rag_enabled
        assert s2.temperature_bias == s.temperature_bias

    def test_from_dict_ignores_unknown_keys(self):
        d = AgentStrategy.default().to_dict()
        d["nonexistent_field"] = "value"
        s = AgentStrategy.from_dict(d)
        assert s.rag_enabled is True


class TestStrategyPool:
    def test_select_no_memory(self):
        pool = StrategyPool(memory=None)
        strategy = pool.select("fix the login bug")
        assert isinstance(strategy, AgentStrategy)

    def test_task_hash_stable(self):
        h1 = StrategyPool._task_hash("refactor authentication module")
        h2 = StrategyPool._task_hash("refactor authentication module")
        assert h1 == h2

    def test_task_hash_different_prompts(self):
        h1 = StrategyPool._task_hash("add tests for login")
        h2 = StrategyPool._task_hash("fix database connection")
        assert h1 != h2

    def test_evolve_increases_fitness_on_high_score(self):
        pool = StrategyPool(memory=None)
        strategy = AgentStrategy(fitness=50.0)
        pool.evolve(strategy, score=100.0, prompt="test task")
        assert strategy.fitness > 50.0
        assert strategy.generation == 1

    def test_evolve_decreases_fitness_on_low_score(self):
        pool = StrategyPool(memory=None)
        strategy = AgentStrategy(fitness=80.0)
        pool.evolve(strategy, score=0.0, prompt="failing task")
        assert strategy.fitness < 80.0

    def test_evolve_ema_formula(self):
        pool = StrategyPool(memory=None)
        strategy = AgentStrategy(fitness=50.0)
        pool.evolve(strategy, score=100.0, prompt="test")
        expected = round(0.7 * 50.0 + 0.3 * 100.0, 2)
        assert strategy.fitness == expected

    def test_select_with_mock_memory(self):
        class FakeMemory:
            def get(self, key, default=None): return default
            def remember(self, key, value): pass
        pool = StrategyPool(memory=FakeMemory())
        strategy = pool.select("implement new api endpoint")
        assert isinstance(strategy, AgentStrategy)
