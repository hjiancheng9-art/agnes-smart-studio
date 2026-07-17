"""Unit tests for core.cancellation — CancellationToken, TaskRegistry, TaskInfo."""

from __future__ import annotations

import pytest
from core.cancellation import (
    CancelledError,
    CancellationToken,
    TaskInfo,
    TaskRegistry,
    TaskStatus,
    get_registry,
    run_cancellable,
)


# ═══════════════════════════════════════════════════════════════
# CancellationToken
# ═══════════════════════════════════════════════════════════════

class TestCancellationToken:
    def test_default_not_cancelled(self):
        t = CancellationToken()
        assert t.cancelled is False
        assert t.is_cancelled() is False
        assert t.reason == ""

    def test_cancel_sets_state(self):
        t = CancellationToken()
        t.cancel("测试取消")
        assert t.cancelled is True
        assert t.is_cancelled() is True
        assert t.reason == "测试取消"

    def test_check_raises_when_cancelled(self):
        t = CancellationToken(task_id="task1")
        t.cancel("stopped")
        with pytest.raises(CancelledError) as exc:
            t.check()
        assert "task1" in str(exc.value)
        assert "stopped" in str(exc.value)

    def test_check_silent_when_active(self):
        t = CancellationToken()
        t.check()  # should not raise

    def test_reset_clears_cancellation(self):
        t = CancellationToken()
        t.cancel("x")
        t.reset()
        assert t.cancelled is False
        assert t.reason == ""
        t.check()  # should not raise

    def test_task_id_set_on_init(self):
        t = CancellationToken(task_id="abc123")
        assert t.task_id == "abc123"


# ═══════════════════════════════════════════════════════════════
# CancelledError
# ═══════════════════════════════════════════════════════════════

class TestCancelledError:
    def test_contains_task_id_and_reason(self):
        e = CancelledError("tid", "cancelled by user")
        assert e.task_id == "tid"
        assert e.reason == "cancelled by user"
        assert "tid" in str(e)
        assert "cancelled by user" in str(e)

    def test_is_runtime_error(self):
        e = CancelledError("t", "r")
        assert isinstance(e, RuntimeError)


# ═══════════════════════════════════════════════════════════════
# TaskInfo
# ═══════════════════════════════════════════════════════════════

class TestTaskInfo:
    def test_default_status_pending(self):
        info = TaskInfo(task_id="1", name="test")
        assert info.status == TaskStatus.PENDING
        assert info.task_id == "1"
        assert info.name == "test"

    def test_duration_zero_when_not_started(self):
        info = TaskInfo(task_id="1", name="t")
        assert info.duration == 0.0

    def test_to_dict(self):
        info = TaskInfo(task_id="1", name="test")
        d = info.to_dict()
        assert d["task_id"] == "1"
        assert d["name"] == "test"
        assert d["status"] == "pending"


# ═══════════════════════════════════════════════════════════════
# TaskRegistry
# ═══════════════════════════════════════════════════════════════

class TestTaskRegistry:
    def test_register_returns_id_and_token(self):
        reg = TaskRegistry()
        tid, token = reg.register("my-task")
        assert len(tid) == 12
        assert isinstance(token, CancellationToken)
        assert token.task_id == tid

    def test_register_sets_running_status(self):
        reg = TaskRegistry()
        tid, _ = reg.register("t")
        info = reg.get(tid)
        assert info.status == TaskStatus.RUNNING

    def test_complete_sets_completed(self):
        reg = TaskRegistry()
        tid, _ = reg.register("t")
        reg.complete(tid, "result")
        info = reg.get(tid)
        assert info.status == TaskStatus.COMPLETED
        assert info.result == "result"

    def test_fail_sets_failed(self):
        reg = TaskRegistry()
        tid, _ = reg.register("t")
        reg.fail(tid, "oops")
        info = reg.get(tid)
        assert info.status == TaskStatus.FAILED
        assert info.error == "oops"

    def test_cancel_sets_cancelled_and_token(self):
        reg = TaskRegistry()
        tid, token = reg.register("t")
        assert reg.cancel(tid, "user abort") is True
        info = reg.get(tid)
        assert info.status == TaskStatus.CANCELLED
        assert token.is_cancelled() is True

    def test_cancel_unknown_id_returns_false(self):
        reg = TaskRegistry()
        assert reg.cancel("nonexistent") is False

    def test_get_unknown_returns_none(self):
        reg = TaskRegistry()
        assert reg.get("ghost") is None

    def test_list_active_only_running(self):
        reg = TaskRegistry()
        tid1, _ = reg.register("a")
        tid2, _ = reg.register("b")
        reg.complete(tid1, "ok")
        active = reg.list_active()
        assert len(active) == 1
        assert active[0].task_id == tid2

    def test_list_all_returns_all(self):
        reg = TaskRegistry()
        tid1, _ = reg.register("a")
        tid2, _ = reg.register("b")
        reg.complete(tid1, "ok")
        assert len(reg.list_all()) == 2

    def test_cleanup_removes_old_completed(self):
        import time

        reg = TaskRegistry()
        tid, _ = reg.register("t")
        reg.complete(tid, "done")
        # Override ended_at to simulate old task
        info = reg.get(tid)
        info.ended_at = time.time() - 7200  # 2 hours ago
        removed = reg.cleanup(max_age=3600)
        assert removed == 1
        assert reg.get(tid) is None

    def test_cleanup_keeps_recent(self):
        reg = TaskRegistry()
        tid, _ = reg.register("t")
        reg.complete(tid, "done")
        removed = reg.cleanup(max_age=3600)
        assert removed == 0
        assert reg.get(tid) is not None

    def test_stats_counts_by_status(self):
        reg = TaskRegistry()
        tid1, _ = reg.register("a")
        tid2, _ = reg.register("b")
        reg.complete(tid1, "ok")
        s = reg.stats()
        assert s.get("running", 0) == 1
        assert s.get("completed", 0) == 1


# ═══════════════════════════════════════════════════════════════
# run_cancellable
# ═══════════════════════════════════════════════════════════════

class TestRunCancellable:
    def test_successful_execution(self):
        def work(*, token):
            token.check()
            return "done"

        result = run_cancellable("test", work)
        assert result == "done"

    def test_cancellation_propagates(self):
        def work(*, token):
            token.cancel("abort")
            token.check()

        with pytest.raises(CancelledError):
            run_cancellable("test", work)

    def test_exception_propagates(self):
        def work(*, token):
            raise ValueError("bad")

        with pytest.raises(ValueError, match="bad"):
            run_cancellable("test", work)

    def test_task_registered_and_completed(self):
        reg = get_registry()

        def work(*, token):
            token.check()
            return "ok"

        run_cancellable("test-job", work)
        all_tasks = reg.list_all()
        completed = [t for t in all_tasks if t.name == "test-job" and t.status == TaskStatus.COMPLETED]
        assert len(completed) >= 1


# ═══════════════════════════════════════════════════════════════
# get_registry singleton
# ═══════════════════════════════════════════════════════════════

class TestGetRegistry:
    def test_returns_same_instance(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
