"""Self-Audit: UI Heartbeat + CDP Safe Executor + Mouse Mode Guard.

Tests the three-in-one fix for TUI mouse/keyboard/scroll freeze issues.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from ui.ui_heartbeat import CdpSafeExecutor, MouseModeGuard, UIHeartbeat


def _run_sync(coro):
    """Run an async test function synchronously."""
    return asyncio.run(coro())


class TestUIHeartbeat:
    """200ms heartbeat must detect loop freeze."""

    def test_heartbeat_initially_not_frozen(self):
        h = UIHeartbeat()
        assert h.freeze_count == 0
        assert h.total_freeze_time == 0.0

    def test_heartbeat_tick_updates_timestamp(self):
        h = UIHeartbeat(threshold=0.05)
        # tick() sets _last_tick = time.monotonic()
        h.tick()
        # Simply verify it doesn't throw and isn't frozen
        assert h.is_frozen is False

    def test_heartbeat_detects_freeze(self):
        h = UIHeartbeat(threshold=0.05)
        h._last_tick = time.monotonic() - 1.0  # pretend frozen for 1s
        assert h.is_frozen is True
        assert h.frozen_seconds >= 0.9

    def test_heartbeat_not_frozen_after_recent_tick(self):
        h = UIHeartbeat(threshold=0.5)
        h.tick()  # fresh tick
        assert h.is_frozen is False

    def test_heartbeat_stop_clears_task(self):
        """stop() should set _running=False and cancel the task."""
        async def _run():
            h = UIHeartbeat()
            h.start()
            assert h._task is not None, "Task should be created in running loop"
            assert not h._task.cancelled()
            h.stop()
            return h

        h = _run_sync(_run)
        assert h._running is False

    def test_heartbeat_no_double_start(self):
        """Starting twice should not create duplicate tasks."""
        async def _run():
            h = UIHeartbeat()
            h.start()
            task1 = h._task
            assert task1 is not None
            h.start()  # second start should be no-op
            assert h._task is task1
            return h

        _run_sync(_run)


class TestCdpSafeExecutor:
    """CDP ops must not block the event loop."""

    def test_execute_quick_op(self):
        """Fast operation should return result immediately."""
        async def run():
            s = CdpSafeExecutor(timeout=5.0)
            result = await s.execute(lambda: 42)
            return result
        import asyncio
        result = asyncio.run(run())
        assert result == 42

    def test_execute_timeout(self):
        """Slow operation should raise TimeoutError."""
        async def run():
            s = CdpSafeExecutor(timeout=0.5)
            with pytest.raises(asyncio.TimeoutError):
                await s.execute(lambda: time.sleep(2.0))
        import asyncio
        asyncio.run(run())

    def test_execute_raises_exception(self):
        """Operation that raises should propagate exception."""
        async def run():
            s = CdpSafeExecutor(timeout=5.0)
            def fail_func():
                raise ValueError("test error")
            with pytest.raises(ValueError, match="test error"):
                await s.execute(fail_func)
        import asyncio
        asyncio.run(run())

    def test_health_check_returns_true(self):
        """Health check should return True for working check."""
        async def run():
            s = CdpSafeExecutor(timeout=5.0)
            healthy = await s.health_check(lambda: True)
            assert healthy is True
        import asyncio
        asyncio.run(run())

    def test_health_check_returns_false(self):
        """Health check should return False for broken check."""
        async def run():
            s = CdpSafeExecutor(timeout=2.0)
            def fail_check():
                raise RuntimeError("fail")
            unhealthy = await s.health_check(fail_check)
            assert unhealthy is False
        import asyncio
        asyncio.run(run())

    def test_stats_tracking(self):
        """Stats should track ops and failures."""
        async def run():
            s = CdpSafeExecutor(timeout=5.0)
            await s.execute(lambda: 1)
            stats = s.stats()
            assert stats["total_ops"] >= 1
            assert "failures" in stats
            s.shutdown(wait=False)
        import asyncio
        asyncio.run(run())


class TestMouseModeGuard:
    """Mouse mode must be automatically restored."""

    def test_enable_restore(self):
        m = MouseModeGuard()
        m.enable()
        assert m._enabled is True
        m.restore()
        assert m._restore_count >= 1

    def test_disable(self):
        m = MouseModeGuard()
        m.enable()
        m.disable()
        assert m._enabled is False

    def test_strip_mouse_ansi(self):
        """Filter should remove mouse-disable sequences."""
        m = MouseModeGuard()
        dirty = "normal text \033[?1000l more \033[?1002l end"
        clean = m.strip_mouse_ansi(dirty)
        assert "\033[?1000l" not in clean
        assert "\033[?1002l" not in clean
        assert "normal text" in clean
        assert "more" in clean
        assert "end" in clean

    def test_strip_preserves_normal_text(self):
        m = MouseModeGuard()
        normal = "Hello, CRUX Studio v6.0.0! normal output"
        assert m.strip_mouse_ansi(normal) == normal

    def test_strip_handles_empty(self):
        m = MouseModeGuard()
        assert m.strip_mouse_ansi("") == ""
