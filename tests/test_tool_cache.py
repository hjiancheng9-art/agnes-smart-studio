"""Tests for core/tool_cache.py — 工具结果缓存"""

import pytest

from core.tool_cache import ToolResultCache


@pytest.fixture
def cache():
    return ToolResultCache()


class TestToolResultCache:
    """工具缓存全链路测试"""

    def test_put_and_get(self, cache):
        cache.put("read_file", '{"path":"test.txt"}', "file_content")
        assert cache.get("read_file", '{"path":"test.txt"}') == "file_content"

    def test_get_missing(self, cache):
        assert cache.get("nonexistent", "{}") is None

    def test_put_overwrites(self, cache):
        cache.put("tool", '{"k":"v"}', "v1")
        cache.put("tool", '{"k":"v"}', "v2")
        assert cache.get("tool", '{"k":"v"}') == "v2"

    def test_different_args_different_cache(self, cache):
        cache.put("tool", '{"a":1}', "ra")
        cache.put("tool", '{"a":2}', "rb")
        assert cache.get("tool", '{"a":1}') == "ra"
        assert cache.get("tool", '{"a":2}') == "rb"

    def test_invalidate_all(self, cache):
        cache.put("t1", "{}", "v1")
        cache.put("t2", "{}", "v2")
        cache.invalidate_all()
        assert cache.get("t1", "{}") is None
        assert cache.get("t2", "{}") is None

    def test_stats_is_dict(self, cache):
        assert isinstance(cache.stats, dict)

    def test_stats_has_keys(self, cache):
        assert "size" in cache.stats
        assert "hits" in cache.stats
        assert "misses" in cache.stats

    def test_stats_tracks_hits(self, cache):
        cache.put("k", "{}", "v")
        cache.get("k", "{}")
        assert cache.stats["hits"] >= 1

    def test_stats_tracks_misses(self, cache):
        cache.get("nope", "{}")
        assert cache.stats["misses"] >= 1

    def test_stats_tracks_size(self, cache):
        cache.put("a", "{}", "1")
        cache.put("b", "{}", "2")
        assert cache.stats["size"] >= 2

    def test_make_key(self, cache):
        key = cache.make_key("read_file", '{"path":"test.txt"}')
        assert isinstance(key, str)

    def test_put_string_result(self, cache):
        cache.put("s", "{}", "hello")
        assert cache.get("s", "{}") == "hello"

    def test_put_int_as_str(self, cache):
        cache.put("i", "{}", str(42))
        assert cache.get("i", "{}") == "42"

    def test_put_json_result(self, cache):
        import json

        d = json.dumps({"a": 1})
        cache.put("d", "{}", d)
        assert json.loads(cache.get("d", "{}")) == {"a": 1}
