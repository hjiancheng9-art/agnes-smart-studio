"""Tests for core/background.py — 后台任务管理系统"""

import pytest

from core.background import BackgroundManager, BackgroundTask, get_background_manager, reset_background_manager


@pytest.fixture
def bm():
    return BackgroundManager()


@pytest.fixture(autouse=True)
def _clean_background_singleton():
    """Ensure module-level _bg_manager singleton is reset between tests."""
    reset_background_manager()
    yield
    reset_background_manager()


class TestBackgroundTaskCreation:
    """后台任务创建测试"""

    def test_launch_simple(self, bm):
        task = bm.launch("echo hello", description="测试任务")
        assert task.id is not None
        assert task.command == "echo hello"

    def test_launch_unique_ids(self, bm):
        t1 = bm.launch("echo 1", description="任务1")
        t2 = bm.launch("echo 2", description="任务2")
        assert t1.id != t2.id

    def test_launch_with_timeout(self, bm):
        task = bm.launch("sleep 1", description="耗时任务", timeout=60)
        assert task.timeout == 60

    def test_launch_empty_is_ok(self, bm):
        task = bm.launch("")
        assert task is not None


class TestBackgroundTaskList:
    """任务列表测试"""

    def test_list_tasks(self, bm):
        bm.launch("echo 1", description="任务1")
        bm.launch("echo 2", description="任务2")
        tasks = bm.list_tasks(active_only=True)
        assert len(tasks) >= 2

    def test_list_empty(self, bm):
        tasks = bm.list_tasks(active_only=True)
        assert isinstance(tasks, list)


class TestBackgroundTaskGet:
    """获取单个任务测试"""

    def test_get_task(self, bm):
        task = bm.launch("echo hello", description="测试")
        fetched = bm.get_task(task.id)
        assert fetched.id == task.id

    def test_get_nonexistent(self, bm):
        assert bm.get_task("no_such_task") is None


class TestBackgroundTaskStop:
    """停止任务测试"""

    def test_stop(self, bm):
        task = bm.launch("sleep 10", description="待停止")
        bm.stop(task.id)


class TestBackgroundTaskOutput:
    """获取输出测试"""

    def test_get_output(self, bm):
        import time

        task = bm.launch("echo hello", description="测试")
        time.sleep(1)
        output = bm.get_output(task.id)
        assert output is not None


class TestBackgroundTaskDataClass:
    """数据类行为测试"""

    def test_is_terminal_property(self):
        task = BackgroundTask(
            id="t-001",
            command="echo",
            description="test",
            status="running",
            pid=0,
            exit_code=None,
            created_at=0.0,
            started_at=0.0,
            finished_at=0.0,
            timeout=600,
            output_path="",
            stop_reason="",
            terminal_reason="",
        )
        # is_terminal is a property, accessed without ()
        assert not task.is_terminal

    def test_is_terminal_completed(self):
        task = BackgroundTask(
            id="t-002",
            command="echo",
            description="test",
            status="done",
            pid=0,
            exit_code=0,
            created_at=0.0,
            started_at=0.0,
            finished_at=0.0,
            timeout=600,
            output_path="",
            stop_reason="",
            terminal_reason="",
        )
        assert task.is_terminal

    def test_is_terminal_failed(self):
        task = BackgroundTask(
            id="t-003",
            command="echo",
            description="test",
            status="failed",
            pid=0,
            exit_code=1,
            created_at=0.0,
            started_at=0.0,
            finished_at=0.0,
            timeout=600,
            output_path="",
            stop_reason="",
            terminal_reason="",
        )
        assert task.is_terminal

    def test_is_terminal_stopped(self):
        task = BackgroundTask(
            id="t-004",
            command="echo",
            description="test",
            status="stopped",
            pid=0,
            exit_code=None,
            created_at=0.0,
            started_at=0.0,
            finished_at=0.0,
            timeout=600,
            output_path="",
            stop_reason="",
            terminal_reason="",
        )
        assert task.is_terminal

    def test_to_dict(self, bm):
        task = bm.launch("echo hi", description="测试")
        d = task.to_dict()
        assert isinstance(d, dict)

    def test_from_dict(self):
        d = {
            "id": "t-003",
            "command": "echo hello",
            "description": "test",
            "status": "running",
            "pid": 123,
            "exit_code": None,
            "created_at": 1000.0,
            "started_at": 1000.0,
            "finished_at": 0.0,
            "timeout": 600,
            "output_path": "/tmp/test.log",
            "stop_reason": "",
            "terminal_reason": "",
        }
        task = BackgroundTask.from_dict(d)
        assert task.id == "t-003"
        assert task.command == "echo hello"


class TestSingleton:
    """全局单例测试"""

    def test_singleton(self):
        bm1 = get_background_manager()
        bm2 = get_background_manager()
        assert bm1 is bm2

    def test_reset(self):
        from core.background import reset_background_manager

        bm1 = get_background_manager()
        reset_background_manager()
        bm2 = get_background_manager()
        assert bm1 is not bm2


class TestCleanup:
    def test_cleanup_old(self, bm):
        count = bm.cleanup_old(max_age_hours=0)
        assert count >= 0
