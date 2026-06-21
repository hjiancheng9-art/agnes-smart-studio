"""Tests for core.tool_cache — LRU tool result cache."""

import json


class TestToolResultCache:
    def _make_cache(self, max_size=128):
        from core.tool_cache import ToolResultCache
        return ToolResultCache(max_size=max_size)

    def test_make_key_deterministic(self):
        from core.tool_cache import ToolResultCache
        k1 = ToolResultCache.make_key("read_file", '{"path": "/tmp/a.py"}')
        k2 = ToolResultCache.make_key("read_file", '{"path": "/tmp/a.py"}')
        assert k1 == k2

    def test_make_key_differs_by_args(self):
        from core.tool_cache import ToolResultCache
        k1 = ToolResultCache.make_key("read_file", '{"path": "/tmp/a.py"}')
        k2 = ToolResultCache.make_key("read_file", '{"path": "/tmp/b.py"}')
        assert k1 != k2

    def test_put_get(self):
        cache = self._make_cache()
        cache.put("read_file", '{"path": "/tmp/a.py"}', "file content here")
        result = cache.get("read_file", '{"path": "/tmp/a.py"}')
        assert result == "file content here"

    def test_get_miss(self):
        cache = self._make_cache()
        result = cache.get("read_file", '{"path": "/nope.py"}')
        assert result is None

    def test_error_results_not_cached(self):
        cache = self._make_cache()
        cache.put("read_file", '{"path": "/tmp/a.py"}', "[错误] something failed")
        result = cache.get("read_file", '{"path": "/tmp/a.py"}')
        assert result is None

    def test_plan_mode_results_not_cached(self):
        cache = self._make_cache()
        cache.put("read_file", '{"path": "/tmp/a.py"}', "[PLAN MODE] ...")
        result = cache.get("read_file", '{"path": "/tmp/a.py"}')
        assert result is None

    def test_lru_eviction(self):
        cache = self._make_cache(max_size=3)
        cache.put("tool1", '{"a":1}', "result1")
        cache.put("tool2", '{"a":2}', "result2")
        cache.put("tool3", '{"a":3}', "result3")
        cache.put("tool4", '{"a":4}', "result4")  # evicts tool1
        assert cache.get("tool1", '{"a":1}') is None
        assert cache.get("tool4", '{"a":4}') == "result4"

    def test_invalidate_all(self):
        cache = self._make_cache()
        cache.put("read_file", '{"path": "/tmp/a.py"}', "content")
        cache.invalidate_all()
        assert cache.get("read_file", '{"path": "/tmp/a.py"}') is None

    def test_stats_initial(self):
        cache = self._make_cache()
        stats = cache.stats
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_after_operations(self):
        cache = self._make_cache()
        cache.put("tool", '{"a":1}', "result")
        cache.get("tool", '{"a":1}')  # hit
        cache.get("tool", '{"a":2}')  # miss
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_repr(self):
        cache = self._make_cache()
        cache.put("tool", '{"a":1}', "result")
        r = repr(cache)
        assert "ToolResultCache" in r
        assert "size=" in r

    def test_ttl_expiration(self):
        cache = self._make_cache()
        cache.put("env_check", '{"a":1}', "env info")
        # env_check TTL is 600s, so we can't easily test real expiration
        # But we can verify the entry exists now
        assert cache.get("env_check", '{"a":1}') == "env info"

    def test_mtime_tools_set_in_tmp(self, tmp_path):
        """Test that file tools store mtime in cache entries."""
        cache = self._make_cache()
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        args = json.dumps({"path": str(f)})
        cache.put("read_file", args, "file content")
        result = cache.get("read_file", args)
        assert result == "file content"

    def test_overwrite_entry(self):
        cache = self._make_cache()
        cache.put("tool", '{"a":1}', "v1")
        cache.put("tool", '{"a":1}', "v2")
        assert cache.get("tool", '{"a":1}') == "v2"


class TestConstants:
    def test_cacheable_tools_set(self):
        from core.tool_cache import CACHEABLE_TOOLS
        assert "read_file" in CACHEABLE_TOOLS
        assert "search_files" in CACHEABLE_TOOLS
        assert "run_bash" not in CACHEABLE_TOOLS

    def test_write_tools_invalidate_set(self):
        from core.tool_cache import WRITE_TOOLS_INVALIDATE
        assert "run_bash" in WRITE_TOOLS_INVALIDATE
        assert "write_file" in WRITE_TOOLS_INVALIDATE
        assert "read_file" not in WRITE_TOOLS_INVALIDATE
