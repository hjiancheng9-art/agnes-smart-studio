"""Tests for advisor cache, circuit breaker, and plan_executor.

These are pure unit tests — no CDP/browser dependency.
"""

from __future__ import annotations

import os
import time

import pytest

from advisor.base import AdvisorResult
from advisor.cache import AdvisorCache
from advisor.circuit_breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker
from core.plan_executor import (
    build_advisor_query,
    build_execution_context,
    extract_file_paths,
    should_consult_gpt,
)

# ════════════════════════════════════════════════════════════
#  AdvisorCache
# ════════════════════════════════════════════════════════════


class TestAdvisorCache:
    def test_set_and_get(self):
        cache = AdvisorCache(ttl_seconds=60)
        result = AdvisorResult(status="ok", content="test reply", source="test")
        cache.set("hello", "", result)
        got = cache.get("hello", "")
        assert got is not None
        assert got.content == "test reply"

    def test_miss_returns_none(self):
        cache = AdvisorCache(ttl_seconds=60)
        assert cache.get("nonexistent", "") is None

    def test_expired_entry_returns_none(self):
        cache = AdvisorCache(ttl_seconds=0)  # expires immediately
        result = AdvisorResult(status="ok", content="expired", source="test")
        cache.set("query", "", result)
        time.sleep(0.01)
        assert cache.get("query", "") is None

    def test_does_not_cache_failures(self):
        cache = AdvisorCache(ttl_seconds=60)
        fail_result = AdvisorResult(status="error", content="", source="test")
        cache.set("query", "", fail_result)
        assert cache.get("query", "") is None

    def test_context_variation(self):
        cache = AdvisorCache(ttl_seconds=60)
        r1 = AdvisorResult(status="ok", content="answer 1", source="test")
        cache.set("query", "ctx1", r1)
        assert cache.get("query", "ctx2") is None
        assert cache.get("query", "ctx1") is not None

    def test_size_and_clear(self):
        cache = AdvisorCache(ttl_seconds=60)
        cache.set("q1", "", AdvisorResult(status="ok", content="a", source="t"))
        cache.set("q2", "", AdvisorResult(status="ok", content="b", source="t"))
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0


# ════════════════════════════════════════════════════════════
#  CircuitBreaker
# ════════════════════════════════════════════════════════════


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CLOSED
        assert cb.allow() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CLOSED  # not yet
        cb.record_failure()
        assert cb.state == OPEN
        assert cb.allow() is False

    def test_success_resets(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CLOSED
        assert cb.failure_count == 0

    def test_half_open_allows_one_probe(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=1)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == OPEN

        time.sleep(1.1)
        # First call after cooldown → HALF_OPEN, one probe allowed
        assert cb.allow() is True
        assert cb.state == HALF_OPEN
        # Second call → blocked (probe in flight)
        assert cb.allow() is False

    def test_half_open_probe_success_closes(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=1)
        for _ in range(3):
            cb.record_failure()
        time.sleep(1.1)
        cb.allow()  # → HALF_OPEN
        cb.record_success()
        assert cb.state == CLOSED

    def test_half_open_probe_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=1)
        for _ in range(3):
            cb.record_failure()
        time.sleep(1.1)
        cb.allow()  # → HALF_OPEN
        cb.record_failure()
        assert cb.state == OPEN

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        for _ in range(3):
            cb.record_failure()
        cb.reset()
        assert cb.state == CLOSED
        assert cb.failure_count == 0

    def test_snapshot(self):
        cb = CircuitBreaker(failure_threshold=5, cooldown_seconds=30)
        snap = cb.snapshot()
        assert snap["state"] == CLOSED
        assert snap["failure_threshold"] == 5
        assert snap["cooldown_seconds"] == 30
        assert snap["remaining_cooldown"] == 0.0


# ════════════════════════════════════════════════════════════
#  PlanExecutor
# ════════════════════════════════════════════════════════════


class TestPlanExecutor:
    def test_build_advisor_query_contains_query(self):
        q = build_advisor_query("Write a login function")
        assert "Write a login function" in q
        assert "architect" in q.lower()

    def test_build_execution_context_no_truncation(self):
        long_plan = "A" * 5000  # would be truncated in old approach
        ctx = build_execution_context("do something", long_plan)
        assert long_plan in ctx  # full plan preserved
        assert "[GPT Advisor" in ctx
        assert "[用户原始请求]" in ctx
        assert "do something" in ctx

    def test_build_execution_context_has_tool_instructions(self):
        ctx = build_execution_context("test", "plan")
        assert "edit_file" in ctx
        assert "write_file" in ctx
        assert "run_test" in ctx

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            ("deep", True),
            ("coding", True),
            ("chat", False),
            ("quick_fix", False),
            ("skip", False),
            ("fallback", False),
        ],
    )
    def test_should_consult_gpt(self, tier, expected):
        assert should_consult_gpt(tier) is expected


# ════════════════════════════════════════════════════════════
#  File path extraction + file-aware prompts
# ════════════════════════════════════════════════════════════


class TestExtractFilePaths:
    def test_no_paths(self):
        assert extract_file_paths("hello world") == []

    def test_nonexistent_path_filtered(self):
        # Path format is valid but file doesn't exist
        result = extract_file_paths("check C:/nonexistent/path/to/file.py")
        assert result == []

    def test_existing_file_detected(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        # Use forward slashes — normpath handles it on Windows
        result = extract_file_paths(f"check {f}")
        assert len(result) == 1
        assert os.path.normpath(str(f)) in [os.path.normpath(p) for p in result]

    def test_multiple_existing_files(self, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.js"
        f1.write_text("a")
        f2.write_text("b")
        result = extract_file_paths(f"fix {f1} and {f2}")
        assert len(result) == 2

    def test_dedup(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x")
        result = extract_file_paths(f"check {f} and also {f}")
        assert len(result) == 1

    def test_max_files_cap(self, tmp_path):
        paths = []
        for i in range(8):
            f = tmp_path / f"f{i}.py"
            f.write_text(str(i))
            paths.append(str(f))
        text = " ".join(paths)
        result = extract_file_paths(text)
        assert len(result) <= 5

    def test_image_extension(self, tmp_path):
        # Create a fake image file (content doesn't matter for path detection)
        f = tmp_path / "screenshot.png"
        f.write_bytes(b"fake image")
        result = extract_file_paths(f"analyze {f}")
        assert len(result) == 1

    def test_video_extension(self, tmp_path):
        f = tmp_path / "demo.mp4"
        f.write_bytes(b"fake video")
        result = extract_file_paths(f"analyze {f}")
        assert len(result) == 1

    def test_multiple_video_formats(self, tmp_path):
        for ext in ("mov", "avi", "mkv", "webm"):
            f = tmp_path / f"clip.{ext}"
            f.write_bytes(b"x")
        str(tmp_path / "clip.*")
        # Test each format individually
        for ext in ("mov", "avi", "mkv", "webm"):
            f = tmp_path / f"clip.{ext}"
            result = extract_file_paths(f"check {f}")
            assert len(result) == 1, f"Failed for .{ext}"

    def test_unix_style_path(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("key: value")
        # Unix-style path (forward slash, no drive letter)
        path_str = str(f).replace("\\", "/")
        result = extract_file_paths(f"check {path_str}")
        assert len(result) == 1


class TestFileAwarePrompts:
    def test_build_advisor_query_without_files(self):
        q = build_advisor_query("do something", None)
        assert "attached" not in q.lower()

    def test_build_advisor_query_with_files(self):
        q = build_advisor_query("do something", ["a.py", "b.py"])
        assert "2 file" in q.lower()
        assert "attached" in q.lower()

    def test_build_execution_context_with_file_hint(self):
        ctx = build_execution_context("query", "plan", ["src/auth.py", "tests/test_auth.py"])
        assert "[GPT 已分析的文件]" in ctx
        assert "src/auth.py" in ctx
        assert "tests/test_auth.py" in ctx

    def test_build_execution_context_without_file_hint(self):
        ctx = build_execution_context("query", "plan", None)
        assert "[GPT 已分析的文件]" not in ctx
