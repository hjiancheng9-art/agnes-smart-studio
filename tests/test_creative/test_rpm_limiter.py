"""Tests for core.creative.rpm_limiter — 速率限制器"""
import time

from core.creative.rpm_limiter import (
    RateBucket,
    RPMLimiter,
)


class TestRateBucket:
    def test_acquire_basic(self):
        bucket = RateBucket(max_rpm=10)
        assert bucket.acquire(block=False)

    def test_hit_limit(self):
        bucket = RateBucket(max_rpm=1)
        assert bucket.acquire(block=False)  # 第1个 OK
        assert not bucket.acquire(block=False)  # 第2个 blocked

    def test_cleanup_old(self):
        bucket = RateBucket(max_rpm=1)
        # 塞一个 61 秒前的时间戳
        bucket.timestamps = [time.time() - 61]
        assert bucket.acquire(block=False)

    def test_block_timeout(self):
        bucket = RateBucket(max_rpm=1)
        bucket.acquire(block=False)
        start = time.time()
        ok = bucket.acquire(block=True, timeout=1.0)
        # 应该等不到（刚占了一个 slot），超时后返回 False
        assert not ok or time.time() - start < 2


class TestRPMLimiter:
    def test_singleton(self):
        l1 = RPMLimiter()
        l2 = RPMLimiter()
        assert l1 is l2

    def test_default_limits(self):
        l = RPMLimiter()
        cfg = l.get_config()
        assert cfg["video"] == 1

    def test_set_limit(self):
        l = RPMLimiter()
        l.set_limit("video", 3)
        assert l.get_config()["video"] == 3
        l.set_limit("video", 1)

    def test_wait_image(self):
        # Use image (10 RPM, won't block)
        l = RPMLimiter()
        ok = l.wait("image", timeout=5.0)
        assert ok

    def test_stats(self):
        l = RPMLimiter()
        l.wait("image")
        stats = l.get_stats()
        assert "image" in stats

    def test_context_manager(self):
        l = RPMLimiter()
        with l.limit("image", timeout=5.0):
            pass

    def test_unknown_category(self):
        l = RPMLimiter()
        ok = l.wait("nonexistent", timeout=3.0)
        assert ok
