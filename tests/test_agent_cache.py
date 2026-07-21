"""Tests for core/agent_cache.py — AgentCache LRU + TTL caching layer."""

from __future__ import annotations

import time

import pytest

from core.agent_cache import (
    MAX_DECOMPOSITIONS,
    MAX_EXPLORATIONS,
    AgentCache,
    cached_decompose,
    cached_explore,
    get_cache,
    reset_agent_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Isolate each test by resetting global cache singleton."""
    reset_agent_cache()
    yield
    reset_agent_cache()


# ── AgentCache class ──


class TestAgentCache:
    """Unit tests for AgentCache instance methods."""

    def test_set_and_get_decomposition(self):
        cache = AgentCache()
        cache.set_decomposition("test goal", "explore", [1, 2, 3])
        result = cache.get_decomposition("test goal", "explore")
        assert result == [1, 2, 3]

    def test_get_decomposition_miss(self):
        cache = AgentCache()
        assert cache.get_decomposition("nonexistent", "") is None

    def test_get_decomposition_expired(self):
        cache = AgentCache()
        cache.set_decomposition("stale", "agent", "old_value")
        # Force expiry by manipulating internal state
        key = cache._decomp_key("stale", "agent")
        old_ts = time.time() - 9999
        cache._decomp[key] = (old_ts, "old_value")
        assert cache.get_decomposition("stale", "agent") is None

    def test_set_and_get_exploration(self):
        cache = AgentCache()
        cache.set_exploration("*.py", "src", ["main.py"])
        assert cache.get_exploration("*.py", "src") == ["main.py"]

    def test_get_exploration_expired(self):
        cache = AgentCache()
        cache.set_exploration("query", "dir", "data")
        key = cache._explore_key("query", "dir")
        old_ts = time.time() - 9999
        cache._explore[key] = (old_ts, "data")
        assert cache.get_exploration("query", "dir") is None

    def test_different_goals_different_keys(self):
        cache = AgentCache()
        k1 = cache._decomp_key("goal_a", "")
        k2 = cache._decomp_key("goal_b", "")
        assert k1 != k2

    def test_same_goal_different_agent_type_different_keys(self):
        cache = AgentCache()
        k1 = cache._decomp_key("goal", "explore")
        k2 = cache._decomp_key("goal", "plan")
        assert k1 != k2

    def test_decomp_lru_eviction(self):
        cache = AgentCache()
        # Fill past MAX_DECOMPOSITIONS
        for i in range(MAX_DECOMPOSITIONS + 10):
            cache.set_decomposition(f"goal_{i}", "agent", i)
        # Oldest entries should be evicted
        assert cache.get_decomposition("goal_0", "agent") is None
        # Newest entries should survive
        assert cache.get_decomposition(f"goal_{MAX_DECOMPOSITIONS + 9}", "agent") is not None

    def test_explore_lru_eviction(self):
        cache = AgentCache()
        for i in range(MAX_EXPLORATIONS + 10):
            cache.set_exploration(f"q_{i}", "dir", i)
        assert cache.get_exploration("q_0", "dir") is None
        assert cache.get_exploration(f"q_{MAX_EXPLORATIONS + 9}", "dir") is not None

    def test_clear(self):
        cache = AgentCache()
        cache.set_decomposition("g", "a", 1)
        cache.set_exploration("q", "d", 2)
        cache.clear()
        assert cache.get_decomposition("g", "a") is None
        assert cache.get_exploration("q", "d") is None

    def test_stats(self):
        cache = AgentCache()
        stats = cache.stats()
        assert "decomp_entries" in stats
        assert "explore_entries" in stats
        assert stats["decomp_entries"] == 0
        cache.set_decomposition("g", "a", 1)
        assert cache.stats()["decomp_entries"] == 1

    def test_decomp_key_hash_consistency(self):
        k1 = AgentCache._decomp_key("hello world", "agent")
        k2 = AgentCache._decomp_key("hello world", "agent")
        assert k1 == k2
        # key = "agent:" + hexdigest[:16], total 22 chars
        assert len(k1) == 22
        assert k1.startswith("agent:")
        assert len(k1.split(":")[1]) == 16  # hexdigest[:16]

    def test_explore_key_includes_directory(self):
        k1 = AgentCache._explore_key("glob", "a")
        k2 = AgentCache._explore_key("glob", "b")
        assert k1 != k2

    def test_explore_key_consistency(self):
        k1 = AgentCache._explore_key("glob", "dir")
        k2 = AgentCache._explore_key("glob", "dir")
        assert k1 == k2


# ── Module-level singleton ──


class TestGetCache:
    def test_returns_agent_cache_instance(self):
        cache = get_cache()
        assert isinstance(cache, AgentCache)

    def test_singleton(self):
        assert get_cache() is get_cache()

    def test_reset_clears_singleton(self):
        c1 = get_cache()
        reset_agent_cache()
        c2 = get_cache()
        assert c1 is not c2


# ── cached_decompose / cached_explore helpers ──


class TestCachedDecompose:
    def test_first_call_invokes_fn(self):
        called = False

        def fn():
            nonlocal called
            called = True
            return "fresh"

        result = cached_decompose("goal", "agent", fn)
        assert result == "fresh"
        assert called

    def test_second_call_returns_cached(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            return f"call_{call_count}"

        r1 = cached_decompose("g", "a", fn)
        r2 = cached_decompose("g", "a", fn)
        assert r1 == r2 == "call_1"
        assert call_count == 1


class TestCachedExplore:
    def test_first_call_invokes_fn(self):
        called = False

        def fn():
            nonlocal called
            called = True
            return ["found.py"]

        result = cached_explore("*.py", "src", fn)
        assert result == ["found.py"]
        assert called

    def test_second_call_returns_cached(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            return [f"file_{call_count}"]

        r1 = cached_explore("q", "dir", fn)
        r2 = cached_explore("q", "dir", fn)
        assert r1 == r2
        assert call_count == 1
