"""Unit tests for core.tool_cache — ToolResultCache for idempotent tool results."""

from __future__ import annotations

import pytest
from core.tool_cache import CACHEABLE_TOOLS, WRITE_TOOLS_INVALIDATE, ToolResultCache, get_tool_cache


class TestToolResultCache:
    def test_get_miss_returns_none(self):
        cache = ToolResultCache()
        assert cache.get("read_file", '{"path":"/x"}') is None

    def test_put_and_get(self):
        cache = ToolResultCache()
        cache.put("read_file", '{"path":"/tmp/a.py"}', "content of a")
        assert cache.get("read_file", '{"path":"/tmp/a.py"}') == "content of a"

    def test_different_args_different_keys(self):
        cache = ToolResultCache()
        cache.put("read_file", '{"path":"/a"}', "A")
        cache.put("read_file", '{"path":"/b"}', "B")
        assert cache.get("read_file", '{"path":"/a"}') == "A"
        assert cache.get("read_file", '{"path":"/b"}') == "B"

    def test_invalidate_all_clears(self):
        cache = ToolResultCache()
        cache.put("read_file", '{"path":"/x"}', "data")
        cache.invalidate_all()
        assert cache.get("read_file", '{"path":"/x"}') is None

    def test_set_alias_for_put(self):
        cache = ToolResultCache()
        cache.set("read_file", '{"path":"/z"}', "zdata")
        assert cache.get("read_file", '{"path":"/z"}') == "zdata"

    def test_cache_key_deterministic(self):
        """Same input string always produces same cache key."""
        cache = ToolResultCache()
        cache.put("read_file", '{"path":"/x","max_lines":10}', "ok")
        assert cache.get("read_file", '{"path":"/x","max_lines":10}') == "ok"

    def test_max_size_eviction(self):
        cache = ToolResultCache(max_size=3)
        for i in range(5):
            cache.put("r", '{"i":' + str(i) + '}', str(i))
        assert cache.get("r", '{"i":0}') is None
        assert cache.get("r", '{"i":1}') is None
        assert cache.get("r", '{"i":4}') == "4"

    def test_does_not_cache_errors(self):
        cache = ToolResultCache()
        cache.put("run_bash", '{"cmd":"bad"}', "[错误] command failed")
        assert cache.get("run_bash", '{"cmd":"bad"}') is None

    def test_does_not_cache_plan_mode(self):
        cache = ToolResultCache()
        cache.put("run_bash", '{"cmd":"x"}', "[PLAN MODE] blocked")
        assert cache.get("run_bash", '{"cmd":"x"}') is None

    def test_stats_property(self):
        cache = ToolResultCache()
        cache.put("read_file", "{}", "x")
        cache.get("read_file", "{}")  # hit
        cache.get("read_file", '{"y":1}')  # miss
        s = cache.stats
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["size"] == 1

    def test_repr(self):
        cache = ToolResultCache()
        r = repr(cache)
        assert "ToolResultCache" in r


class TestToolCacheConstants:
    def test_cacheable_tools_is_set(self):
        assert isinstance(CACHEABLE_TOOLS, set)

    def test_write_tools_invalidate_is_set(self):
        assert isinstance(WRITE_TOOLS_INVALIDATE, set)

    def test_read_file_is_cacheable(self):
        assert "read_file" in CACHEABLE_TOOLS

    def test_write_file_triggers_invalidate(self):
        assert "write_file" in WRITE_TOOLS_INVALIDATE
        assert "edit_file" in WRITE_TOOLS_INVALIDATE


class TestGetToolCache:
    def test_singleton(self):
        c1 = get_tool_cache()
        c2 = get_tool_cache()
        assert c1 is c2
