"""Tests for core/cron.py — 定时任务"""

from core.cron import CronJob, CronScheduler, cron_list


class TestCronScheduler:
    def test_create(self):
        """创建定时任务调度器"""
        cs = CronScheduler()
        assert cs is not None

    def test_list_empty(self):
        jobs = cron_list()
        assert isinstance(jobs, list)


class TestCronJob:
    def test_is_dataclass(self):
        assert hasattr(CronJob, "__dataclass_fields__")

    def test_has_required_fields(self):
        fields = CronJob.__dataclass_fields__.keys()
        assert "id" in fields or "cron" in fields
