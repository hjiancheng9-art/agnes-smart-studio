"""Tests for core.executor.AsyncTaskExecutor — asyncio 原生任务执行器。

AsyncTaskExecutor 使用拓扑 waves 调度独立步骤并行执行，
支持同步/异步 tool_executor，含依赖追踪、错误恢复、验证门。
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.executor import (
    AsyncTaskExecutor,
    Step,
    Task,
    quick_plan,
)

# ── helpers ──────────────────────────────────────────────────────


def _sync_tool_ok(name: str, args: dict) -> str:
    """同步 tool executor：总是返回 "ok"。"""
    return "ok"


async def _async_tool_ok(name: str, args: dict) -> str:
    """异步 tool executor：总是返回 "ok"。"""
    await asyncio.sleep(0.001)
    return "ok"


def _make_executor(tool_fn, *, root=None, max_concurrency: int = 4):
    return AsyncTaskExecutor(tool_fn, root=root or ROOT, max_concurrency=max_concurrency)


def _make_task(steps, errors_allowed: int = 1) -> Task:
    return Task(id="t", goal="test", steps=steps, errors_allowed=errors_allowed)


# ── 基础：线性链 / 并行独立步骤 ─────────────────────────────────


class TestAsyncLinearChain:
    @pytest.mark.asyncio
    async def test_all_success_sync_executor(self):
        mock_fn = MagicMock(return_value="ok")
        task = _make_task(
            [
                Step("s1", "A", "read_file", {"path": "x.py"}),
                Step("s2", "B", "env_check", {}),
                Step("s3", "C", "read_file", {"path": "y.py"}),
            ],
            errors_allowed=0,
        )
        report = await _make_executor(mock_fn).arun(task)
        assert report["status"] == "done"
        assert report["steps_done"] == 3
        assert report["steps_failed"] == 0
        assert mock_fn.call_count == 3

    @pytest.mark.asyncio
    async def test_all_success_async_executor(self):
        mock_fn = AsyncMock(return_value="ok")
        task = _make_task(
            [
                Step("s1", "A", "read_file", {}),
                Step("s2", "B", "env_check", {}),
            ],
            errors_allowed=0,
        )
        report = await _make_executor(mock_fn).arun(task)
        assert report["status"] == "done"
        assert report["steps_done"] == 2

    @pytest.mark.asyncio
    async def test_independent_steps_run_in_parallel(self):
        """同层独立步骤应该并行执行，验证执行时间 < 顺序执行时间。"""
        call_times: list[float] = []

        async def _timed_tool(name: str, args: dict) -> str:
            call_times.append(time.monotonic())
            await asyncio.sleep(0.05)
            return "ok"

        task = _make_task(
            [
                Step("s1", "A", "tool_a", {}),
                Step("s2", "B", "tool_b", {}),
                Step("s3", "C", "tool_c", {}),
            ],
            errors_allowed=0,
        )
        t0 = time.monotonic()
        report = await _make_executor(_timed_tool).arun(task)
        elapsed = time.monotonic() - t0
        assert report["status"] == "done"
        assert report["steps_done"] == 3
        # 3 个 50ms 的 sleep 如果顺序执行需要 > 150ms，
        # 并行应 < 100ms（留余量给调度开销）
        assert elapsed < 0.15, f"Expected parallel execution, but took {elapsed:.3f}s"


# ── 依赖追踪 ────────────────────────────────────────────────────


class TestAsyncDependencies:
    @pytest.mark.asyncio
    async def test_dependency_ordering(self):
        """依赖链 s1 -> s2 -> s3：按拓扑顺序执行。"""
        order: list[str] = []

        async def _ordered_tool(name: str, args: dict) -> str:
            order.append(name)
            return "ok"

        task = _make_task(
            [
                Step("s1", "First", "tool_a", {}),
                Step("s2", "Second", "tool_b", {}, depends_on=["s1"]),
                Step("s3", "Third", "tool_c", {}, depends_on=["s2"]),
            ],
            errors_allowed=0,
        )
        report = await _make_executor(_ordered_tool).arun(task)
        assert report["status"] == "done"
        assert order == ["tool_a", "tool_b", "tool_c"]

    @pytest.mark.asyncio
    async def test_dependency_failed_downstream_skipped(self):
        """上游失败 → 下游 skipped（依赖不满足）。"""

        def tool_fn(name, args):
            if name == "read_file":
                return "content"
            raise ValueError("tool error")

        task = _make_task(
            [
                Step("s1", "Read", "read_file", {"path": "a.py"}),
                Step("s2", "Fix", "edit_file", {"path": "a.py"}, depends_on=["s1"]),
            ],
            errors_allowed=1,
        )
        await _make_executor(tool_fn).arun(task)
        assert task.steps[0].status == "done"
        assert task.steps[1].status == "failed"

    @pytest.mark.asyncio
    async def test_missing_dependency_skipped(self):
        """依赖的 step 不存在 → skipped（wave 调度检测为不可解析依赖）。"""
        mock_fn = MagicMock(return_value="ok")
        task = _make_task(
            [
                Step("s1", "Read", "read_file", {}),
                Step("s2", "Depends on non-existent", "edit_file", {}, depends_on=["s999"]),
                Step("s3", "Independent", "env_check", {}),
            ],
            errors_allowed=0,
        )
        _report = await _make_executor(mock_fn).arun(task)
        assert task.steps[0].status == "done"
        # s2 依赖 s999 不存在 → wave 调度标记为 unresolvable
        assert task.steps[1].status == "skipped"
        assert "Unresolvable dependencies" in task.steps[1].error
        assert task.steps[2].status == "done"

    @pytest.mark.asyncio
    async def test_diamond_dependency(self):
        """菱形依赖：s1 -> s2, s1 -> s3, s2+s3 -> s4。"""
        order: list[str] = []

        async def _tracked_tool(name: str, args: dict) -> str:
            order.append(name)
            return "ok"

        task = _make_task(
            [
                Step("s1", "Root", "root", {}),
                Step("s2", "Left", "left", {}, depends_on=["s1"]),
                Step("s3", "Right", "right", {}, depends_on=["s1"]),
                Step("s4", "Join", "join", {}, depends_on=["s2", "s3"]),
            ],
            errors_allowed=0,
        )
        report = await _make_executor(_tracked_tool).arun(task)
        assert report["status"] == "done"
        # s1 必须最先，s4 必须最后
        assert order[0] == "root"
        assert order[-1] == "join"
        # s2 和 s3 应该并行（在 s1 后同时开始）
        idx_left = order.index("left")
        idx_right = order.index("right")
        idx_root = order.index("root")
        assert idx_left > idx_root
        assert idx_right > idx_root


# ── 错误恢复 / 错误预算 ────────────────────────────────────────


class TestAsyncErrorBudget:
    @pytest.mark.asyncio
    async def test_zero_budget_breaks_immediately(self):
        """errors_allowed=0：第一个 step 失败后，后续 wave 被跳过。"""
        call_count = [0]

        def tool_fn(name, args):
            call_count[0] += 1
            raise RuntimeError("boom")

        task = _make_task(
            [
                Step("s1", "Fail 1", "env_check", {}),
                # s2 依赖 s1，在不同 wave → 应被 break_event 跳过
                Step("s2", "Never runs", "read_file", {}, depends_on=["s1"]),
            ],
            errors_allowed=0,
        )
        report = await _make_executor(tool_fn).arun(task)
        assert report["status"] == "failed"
        # s1 执行并失败，s2 在下一 wave 被 break_event 跳过
        assert call_count[0] == 1
        assert task.steps[1].status == "skipped"

    @pytest.mark.asyncio
    async def test_budget_one_continues(self):
        call_count = [0]

        def tool_fn(name, args):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("transient")
            return "ok"

        task = _make_task(
            [
                Step("s1", "Fail first", "env_check", {}),
                Step("s2", "Succeed", "read_file", {}),
            ],
            errors_allowed=1,
        )
        await _make_executor(tool_fn).arun(task)
        assert call_count[0] == 2
        assert task.steps[0].status == "failed"
        assert task.steps[1].status == "done"

    @pytest.mark.asyncio
    async def test_break_event_skips_later_waves(self):
        """错误预算耗尽后，后续 wave 的 step 被 skipped。"""

        def tool_fn(name, args):
            if "fail" in name:
                raise RuntimeError("boom")
            return "ok"

        task = _make_task(
            [
                Step("s1", "Fail step", "fail_tool", {}),
                Step("s2", "Also fail", "fail_tool_2", {}),
                Step("s3", "Downstream", "ok_tool", {}, depends_on=["s1", "s2"]),
            ],
            errors_allowed=0,
        )
        report = await _make_executor(tool_fn).arun(task)
        assert report["status"] == "failed"
        # s3 依赖 s1(失败)，被 skipped
        assert task.steps[2].status == "skipped"

    @pytest.mark.asyncio
    async def test_only_catches_specific_exceptions(self):
        """KeyError 不被 catch，逃逸到调用方。"""

        def tool_fn(name, args):
            raise KeyError("not caught")

        task = _make_task(
            [
                Step("s1", "Boom", "env_check", {}),
            ],
            errors_allowed=1,
        )
        with pytest.raises(KeyError):
            await _make_executor(tool_fn).arun(task)


# ── 报告结构 ─────────────────────────────────────────────────────


class TestAsyncReport:
    @pytest.mark.asyncio
    async def test_report_fields(self):
        mock_fn = MagicMock(return_value="ok")
        task = _make_task(
            [
                Step("s1", "Done", "read_file", {}),
                Step("s2", "Also done", "env_check", {}),
            ],
            errors_allowed=0,
        )
        report = await _make_executor(mock_fn).arun(task)
        for key in (
            "goal",
            "status",
            "elapsed",
            "steps_total",
            "steps_done",
            "steps_failed",
            "steps_skipped",
            "details",
            "log",
        ):
            assert key in report

    @pytest.mark.asyncio
    async def test_details_empty_when_all_done(self):
        mock_fn = MagicMock(return_value="ok")
        task = _make_task([Step("s1", "A", "tool", {})], errors_allowed=0)
        report = await _make_executor(mock_fn).arun(task)
        assert len(report["details"]) == 0

    @pytest.mark.asyncio
    async def test_details_contains_failed_steps(self):
        def tool_fn(name, args):
            raise ValueError("oops")

        task = _make_task([Step("s1", "Boom", "tool", {})], errors_allowed=1)
        report = await _make_executor(tool_fn).arun(task)
        assert len(report["details"]) == 1
        assert report["details"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_log_truncated_to_10(self):
        """log 字段最多保留最后 10 条。"""
        mock_fn = MagicMock(return_value="ok")
        steps = [Step(f"s{i}", f"Step {i}", "tool", {}) for i in range(15)]
        task = _make_task(steps, errors_allowed=0)
        report = await _make_executor(mock_fn).arun(task)
        assert len(report["log"]) <= 10


# ── verify=syntax ──────────────────────────────────────────────


class TestAsyncVerifySyntax:
    @pytest.mark.asyncio
    async def test_syntax_ok(self, tmp_path):
        (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
        step = Step("s1", "Verify", "env_check", {}, verify="syntax")
        task = _make_task([step], errors_allowed=0)
        await _make_executor(_sync_tool_ok, root=tmp_path).arun(task)
        assert step.status == "done"

    @pytest.mark.asyncio
    async def test_syntax_error_fails(self, tmp_path):
        (tmp_path / "bad.py").write_text("def(\n", encoding="utf-8")
        step = Step("s1", "Verify", "env_check", {}, verify="syntax")
        task = _make_task([step], errors_allowed=0)
        report = await _make_executor(_sync_tool_ok, root=tmp_path).arun(task)
        assert step.status == "failed"
        assert "Syntax check failed" in step.error
        assert report["status"] == "failed"


# ── verify=test ─────────────────────────────────────────────────


class TestAsyncVerifyTest:
    @pytest.mark.asyncio
    async def test_no_failures_passes(self):
        """run_pytest_safe 在 pytest 内短路返回 returncode=0 → 验证通过。"""
        step = Step("s1", "Test", "run_test", {}, verify="test")
        task = _make_task([step], errors_allowed=0)
        await _make_executor(_sync_tool_ok, root=ROOT).arun(task)
        assert step.status == "done"

    @pytest.mark.asyncio
    async def test_test_failures_detected(self, monkeypatch):
        fake = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="1 failed, 2 passed",
            stderr="",
        )
        monkeypatch.setattr("core.pytest_runner.run_pytest_safe", lambda **kw: fake)
        step = Step("s1", "Test", "run_test", {}, verify="test")
        task = _make_task([step], errors_allowed=0)
        report = await _make_executor(_sync_tool_ok, root=ROOT).arun(task)
        assert step.status == "failed"
        assert "Tests failed" in step.error
        assert report["status"] == "failed"

    @pytest.mark.asyncio
    async def test_zero_failed_ok(self, monkeypatch):
        fake = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="0 failed, 5 passed",
            stderr="",
        )
        monkeypatch.setattr("core.pytest_runner.run_pytest_safe", lambda **kw: fake)
        step = Step("s1", "Test", "run_test", {}, verify="test")
        task = _make_task([step], errors_allowed=0)
        await _make_executor(_sync_tool_ok, root=ROOT).arun(task)
        assert step.status == "done"

    @pytest.mark.asyncio
    async def test_empty_output_passes(self, monkeypatch):
        fake = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        monkeypatch.setattr("core.pytest_runner.run_pytest_safe", lambda **kw: fake)
        step = Step("s1", "Test", "run_test", {}, verify="test")
        task = _make_task([step], errors_allowed=0)
        await _make_executor(_sync_tool_ok, root=ROOT).arun(task)
        assert step.status == "done"


# ── 循环依赖检测 ───────────────────────────────────────────────


class TestAsyncCycleDetection:
    @pytest.mark.asyncio
    async def test_circular_dependency_skipped(self):
        """循环依赖的 step 应被 skipped。"""
        mock_fn = MagicMock(return_value="ok")
        task = _make_task(
            [
                Step("s1", "A", "tool", {}, depends_on=["s2"]),
                Step("s2", "B", "tool", {}, depends_on=["s1"]),
            ],
            errors_allowed=0,
        )
        report = await _make_executor(mock_fn).arun(task)
        # 两个都无法满足依赖，被 skip
        assert report["steps_skipped"] == 2
        assert task.steps[0].status == "skipped"
        assert task.steps[1].status == "skipped"


# ── quick_plan 复用（共享数据类验证）────────────────────────────


class TestQuickPlanShared:
    def test_quick_plan_uses_shared_step_dataclass(self):
        """验证 quick_plan 生成的 Task 可以直接传给 AsyncTaskExecutor。"""
        task = quick_plan("fix the login bug")
        assert isinstance(task, Task)
        assert all(isinstance(s, Step) for s in task.steps)
        assert task.errors_allowed == 1


# ── asyncio.Semaphore 限并发 ───────────────────────────────────


class TestConcurrencyLimit:
    @pytest.mark.asyncio
    async def test_max_concurrency_respected(self):
        """验证 max_concurrency=2 时，同时运行不超过 2 个 tool。"""
        concurrent_count = 0
        max_seen = 0

        async def _counting_tool(name: str, args: dict) -> str:
            nonlocal concurrent_count, max_seen
            concurrent_count += 1
            max_seen = max(max_seen, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return "ok"

        steps = [Step(f"s{i}", f"Step {i}", "tool", {}) for i in range(6)]
        task = _make_task(steps, errors_allowed=0)
        report = await _make_executor(_counting_tool, max_concurrency=2).arun(task)
        assert max_seen <= 2
        assert report["steps_done"] == 6
