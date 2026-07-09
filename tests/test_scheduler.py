"""Tests for core/scheduler.py — 计划任务"""

from core.scheduler import get_scheduler, reset_scheduler


class TestScheduler:
    def test_get_scheduler(self):
        sched = get_scheduler()
        assert sched is not None

    def test_reset_scheduler(self):
        s1 = get_scheduler()
        reset_scheduler()
        s2 = get_scheduler()
        assert s1 is not s2
