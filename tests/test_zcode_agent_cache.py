"""RED phase tests for core/agent_cache.py.

Tests: AgentCache construction, get/set/clear, stats, cached_decompose,
cached_explore, singleton.
"""

import time
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# AgentCache construction
# ---------------------------------------------------------------------------


class TestAgentCacheConstruction:
    """AgentCache initialization."""

    def test_construction(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        assert ac is not None
        assert len(ac._decomp) == 0
        assert len(ac._explore) == 0

    def test_stats_on_empty_cache(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        s = ac.stats()
        assert s["decomp_entries"] == 0
        assert s["explore_entries"] == 0


# ---------------------------------------------------------------------------
# Decomposition cache
# ---------------------------------------------------------------------------


class TestDecompositionCache:
    """get_decomposition / set_decomposition / TTL."""

    def test_set_and_get_decomposition(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        value = ["task1", "task2", "task3"]
        ac.set_decomposition("build a thing", "explore", value)
        cached = ac.get_decomposition("build a thing", "explore")
        assert cached == value

    def test_get_missing_decomposition(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        assert ac.get_decomposition("never cached", "explore") is None

    def test_different_agent_types_different_keys(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        ac.set_decomposition("goal", "explore", ["a"])
        ac.set_decomposition("goal", "implement", ["b"])
        assert ac.get_decomposition("goal", "explore") == ["a"]
        assert ac.get_decomposition("goal", "implement") == ["b"]

    def test_decomposition_ttl_expiry(self, monkeypatch):
        from core.agent_cache import AgentCache, DECOMP_TTL
        ac = AgentCache()
        ac.set_decomposition("goal", "explore", ["val"])

        # Advance time beyond TTL using a fixed future time
        future = time.time() + DECOMP_TTL + 10
        monkeypatch.setattr(time, "time", lambda: future)
        assert ac.get_decomposition("goal", "explore") is None

    def test_lru_eviction(self):
        from core.agent_cache import AgentCache, MAX_DECOMPOSITIONS
        ac = AgentCache()
        # Fill beyond max
        for i in range(MAX_DECOMPOSITIONS + 5):
            ac.set_decomposition(f"goal_{i}", "explore", [i])
        # The oldest should be evicted
        assert ac.get_decomposition("goal_0", "explore") is None
        # Latest entries should still be present
        assert ac.get_decomposition(f"goal_{MAX_DECOMPOSITIONS + 4}", "explore") == [MAX_DECOMPOSITIONS + 4]


# ---------------------------------------------------------------------------
# Exploration cache
# ---------------------------------------------------------------------------


class TestExplorationCache:
    """get_exploration / set_exploration / TTL."""

    def test_set_and_get_exploration(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        value = ["file1.py", "file2.py"]
        ac.set_exploration("**/*.py", "src", value)
        cached = ac.get_exploration("**/*.py", "src")
        assert cached == value

    def test_get_missing_exploration(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        assert ac.get_exploration("never searched", "/tmp") is None

    def test_different_directories_different_keys(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        ac.set_exploration("**/*.py", "src", ["a.py"])
        ac.set_exploration("**/*.py", "tests", ["test_a.py"])
        assert ac.get_exploration("**/*.py", "src") == ["a.py"]
        assert ac.get_exploration("**/*.py", "tests") == ["test_a.py"]

    def test_exploration_ttl_expiry(self, monkeypatch):
        from core.agent_cache import AgentCache, EXPLORE_TTL
        ac = AgentCache()
        ac.set_exploration("query", "dir", ["result"])
        future = time.time() + EXPLORE_TTL + 5
        monkeypatch.setattr(time, "time", lambda: future)
        assert ac.get_exploration("query", "dir") is None

    def test_lru_eviction(self):
        from core.agent_cache import AgentCache, MAX_EXPLORATIONS
        ac = AgentCache()
        for i in range(MAX_EXPLORATIONS + 5):
            ac.set_exploration(f"query_{i}", "dir", [i])
        assert ac.get_exploration("query_0", "dir") is None
        assert ac.get_exploration(f"query_{MAX_EXPLORATIONS + 4}", "dir") == [MAX_EXPLORATIONS + 4]


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestCacheClear:
    """clear() method."""

    def test_clear_removes_all(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        ac.set_decomposition("goal", "explore", ["val"])
        ac.set_exploration("query", "dir", ["result"])
        ac.clear()
        assert len(ac._decomp) == 0
        assert len(ac._explore) == 0
        assert ac.get_decomposition("goal", "explore") is None
        assert ac.get_exploration("query", "dir") is None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestAgentCacheStats:
    """stats() method."""

    def test_reflects_decomp_entries(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        ac.set_decomposition("g1", "explore", ["a"])
        ac.set_decomposition("g2", "explore", ["b"])
        assert ac.stats()["decomp_entries"] == 2

    def test_reflects_explore_entries(self):
        from core.agent_cache import AgentCache
        ac = AgentCache()
        ac.set_exploration("q1", "d", ["a"])
        assert ac.stats()["explore_entries"] == 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestAgentCacheSingleton:
    """get_cache singleton pattern."""

    def test_returns_same_instance(self):
        from core.agent_cache import get_cache
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2

    def test_returns_agent_cache_instance(self):
        from core.agent_cache import get_cache, AgentCache
        c = get_cache()
        assert isinstance(c, AgentCache)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


class TestCachedDecompose:
    """cached_decompose decorator."""

    def test_returns_cached_on_hit(self):
        from core.agent_cache import cached_decompose, get_cache
        cache = get_cache()
        cache.clear()
        cache.set_decomposition("goal", "explore", ["cached_result"])

        call_count = [0]

        def expensive_fn():
            call_count[0] += 1
            return ["new_result"]

        result = cached_decompose("goal", "explore", expensive_fn)
        assert result == ["cached_result"]
        assert call_count[0] == 0  # expensive_fn was not called

    def test_calls_fn_on_miss(self):
        from core.agent_cache import cached_decompose, get_cache
        cache = get_cache()
        cache.clear()

        def expensive_fn():
            return ["computed"]

        result = cached_decompose("new_goal", "explore", expensive_fn)
        assert result == ["computed"]

        # Subsequent call should be cached
        def never_called():
            return ["should not be called"]

        result = cached_decompose("new_goal", "explore", never_called)
        assert result == ["computed"]


class TestCachedExplore:
    """cached_explore decorator."""

    def test_returns_cached_on_hit(self):
        from core.agent_cache import cached_explore, get_cache
        cache = get_cache()
        cache.clear()
        cache.set_exploration("**/*.py", "my_dir", ["cached.py"])

        call_count = [0]

        def expensive_fn():
            call_count[0] += 1
            return ["new.py"]

        result = cached_explore("**/*.py", "my_dir", expensive_fn)
        assert result == ["cached.py"]
        assert call_count[0] == 0

    def test_calls_fn_on_miss(self):
        from core.agent_cache import cached_explore, get_cache
        cache = get_cache()
        cache.clear()

        def expensive_fn():
            return ["found.py"]

        result = cached_explore("new_query", "new_dir", expensive_fn)
        assert result == ["found.py"]
