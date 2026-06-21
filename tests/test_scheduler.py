"""Tests for core.scheduler — task scheduler with cron parsing."""

import pytest
from datetime import datetime


class TestParseCron:
    def test_wildcard(self):
        from core.scheduler import parse_cron
        result = parse_cron("* * * * *")
        assert len(result["minute"]) == 60
        assert len(result["hour"]) == 24

    def test_specific_values(self):
        from core.scheduler import parse_cron
        result = parse_cron("30 9 * * 1")
        assert 30 in result["minute"]
        assert 9 in result["hour"]
        assert len(result["day"]) == 31  # wildcard

    def test_step(self):
        from core.scheduler import parse_cron
        result = parse_cron("*/15 * * * *")
        for v in [0, 15, 30, 45]:
            assert v in result["minute"]
        assert 7 not in result["minute"]

    def test_range(self):
        from core.scheduler import parse_cron
        result = parse_cron("0 9-17 * * 1-5")
        assert 9 in result["hour"]
        assert 17 in result["hour"]
        assert 8 not in result["hour"]
        assert 18 not in result["hour"]

    def test_comma_separated(self):
        from core.scheduler import parse_cron
        result = parse_cron("0,30 9,18 * * *")
        assert result["minute"] == {0, 30}
        assert result["hour"] == {9, 18}

    def test_invalid_field_count(self):
        from core.scheduler import parse_cron
        with pytest.raises(ValueError, match="5 fields"):
            parse_cron("* * *")

    def test_invalid_step(self):
        from core.scheduler import parse_cron
        with pytest.raises(ValueError, match="positive"):
            parse_cron("*/0 * * * *")

    def test_weekday_normalization(self):
        from core.scheduler import parse_cron
        # 7 should be normalized to 0 (Sunday)
        result = parse_cron("0 0 * * 0,7")
        assert result["weekday"] == {0}

    def test_all_fields_present(self):
        from core.scheduler import parse_cron
        result = parse_cron("0 0 1 1 *")
        assert set(result.keys()) == {"minute", "hour", "day", "month", "weekday"}


class TestScheduledTask:
    def test_creation(self):
        from core.scheduler import ScheduledTask
        task = ScheduledTask(
            id="abc123",
            name="Test Task",
            prompt="Do something",
            schedule_type="interval",
            schedule_value="300",
        )
        assert task.id == "abc123"
        assert task.enabled is True
        assert task.run_count == 0

    def test_to_dict(self):
        from core.scheduler import ScheduledTask
        task = ScheduledTask(id="x", name="y", prompt="z",
                              schedule_type="interval", schedule_value="60")
        d = task.to_dict()
        assert d["id"] == "x"
        assert d["name"] == "y"
        assert isinstance(d, dict)

    def test_from_dict(self):
        from core.scheduler import ScheduledTask
        data = {"id": "x", "name": "y", "prompt": "z",
                "schedule_type": "interval", "schedule_value": "60",
                "enabled": True, "last_run": "", "next_run": "",
                "created_at": "", "run_count": 0}
        task = ScheduledTask.from_dict(data)
        assert task.id == "x"

    def test_from_dict_missing_optional(self):
        from core.scheduler import ScheduledTask
        task = ScheduledTask.from_dict({"id": "x", "name": "y", "prompt": "z",
                                        "schedule_type": "interval", "schedule_value": "60"})
        assert task.enabled is True
        assert task.run_count == 0


class TestScheduler:
    def _make_scheduler(self, tmp_path):
        """Create a Scheduler without starting its background thread.

        Patches the module-level _SCHEDULE_FILE and _TRIGGER_FILE so tests
        don't pollute the real output directory.
        """
        import threading
        from core import scheduler as sched_mod
        from core.scheduler import Scheduler
        # Patch module-level constants directly (tests run serially)
        sched_mod._SCHEDULE_FILE = tmp_path / "scheduled_tasks.json"
        sched_mod._TRIGGER_FILE = tmp_path / "triggers.jsonl"
        sched = Scheduler.__new__(Scheduler)
        sched._tasks = {}
        sched._lock = threading.Lock()
        sched._callback = None
        sched._stop_event = threading.Event()
        sched._thread = threading.Thread(target=lambda: None, daemon=True)
        sched._load()
        return sched

    def test_add_interval_task(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        task = sched.add_task("Test", "prompt", "interval", "60")
        assert task.name == "Test"
        assert task.schedule_type == "interval"
        assert task.enabled is True

    def test_add_cron_task(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        task = sched.add_task("Daily", "prompt", "cron", "0 9 * * 1-5")
        assert task.schedule_type == "cron"

    def test_add_invalid_type(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        with pytest.raises(ValueError, match="interval.*cron"):
            sched.add_task("Bad", "prompt", "invalid", "60")

    def test_add_invalid_interval(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        with pytest.raises(ValueError):
            sched.add_task("Bad", "prompt", "interval", "not_a_number")

    def test_remove_task(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        task = sched.add_task("Remove", "prompt", "interval", "60")
        assert sched.remove_task(task.id) is True
        assert sched.remove_task(task.id) is False

    def test_list_tasks(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        sched.add_task("A", "p1", "interval", "60")
        sched.add_task("B", "p2", "interval", "120")
        tasks = sched.list_tasks()
        assert len(tasks) == 2

    def test_enable_disable_task(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        task = sched.add_task("Toggle", "prompt", "interval", "60")
        assert sched.disable_task(task.id) is True
        assert sched.enable_task(task.id) is True
        assert sched.enable_task("nope") is False
        assert sched.disable_task("nope") is False

    def test_set_callback(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        calls = []
        sched.set_execution_callback(lambda prompt: calls.append(prompt))
        sched._execute_task(type('obj', (object,), {  # type: ignore[arg-type]  # dynamic mock for test
            'id': 'x', 'name': 'test', 'prompt': 'hello'}))
        assert "hello" in calls

    def test_persistence(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        sched.add_task("Persistent", "prompt", "interval", "300")
        # Create new scheduler loading same file
        sched2 = self._make_scheduler(tmp_path)
        tasks = sched2.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "Persistent"

    def test_calculate_next_run_interval(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        task = sched.add_task("Interval", "prompt", "interval", "60")
        # next_run should be ~60 seconds from now
        next_time = datetime.fromisoformat(task.next_run)
        now = datetime.now()
        diff = (next_time - now).total_seconds()
        assert 50 < diff < 120  # generous window


class TestToolDefs:
    def test_tool_defs_exist(self):
        from core.scheduler import SCHEDULER_TOOL_DEFS
        assert len(SCHEDULER_TOOL_DEFS) == 6
        names = [d["function"]["name"] for d in SCHEDULER_TOOL_DEFS]
        assert "schedule_add" in names
        assert "schedule_remove" in names
        assert "schedule_list" in names

    def test_executor_map_exists(self):
        from core.scheduler import SCHEDULER_EXECUTOR_MAP
        assert "schedule_add" in SCHEDULER_EXECUTOR_MAP
        assert "schedule_remove" in SCHEDULER_EXECUTOR_MAP
