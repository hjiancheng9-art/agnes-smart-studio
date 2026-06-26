"""Tests for AsyncMultiAgentCoordinator — asyncio-native multi-agent coordination.

Phase 4 把 core/multi_agent.py 的同步 threading 实现扩展为 asyncio 原生版。
本测试守护 async 版的核心不变式：

1. **依赖感知调度**：``depends_on`` 拓扑分层——同一波内并行，波间串行等待。
   通过给每个工具调用打时间戳，验证依赖的任务不会在前置完成前启动。
2. **executor 双模**：同步 ``Callable``（to_thread 包装）与 async ``Callable``
   （直接 await）都正常工作。
3. **失败传播**：单个任务失败标记 failed，不污染其他任务。
4. **并发上限**：``max_workers`` 限制同时在途任务数（通过计时断言）。
5. **结果聚合**：与同步版 ``execute`` 返回 dict 结构一致。

风格对齐 tests/test_async_render.py：同步测试方法 +
asyncio.run()，不用 @pytest.mark.asyncio（避免 pytest-asyncio teardown 清空
全局 loop，导致后续测试 get_event_loop() 抛 RuntimeError）。
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.multi_agent import (
    AgentTask,
    AsyncMultiAgentCoordinator,
    _topological_waves,
    async_coordinate,
)


def _run(coro):
    """同步运行 async 协程。

    用 asyncio.run 而非 get_event_loop().run_until_complete：
    pytest-asyncio 的 @pytest.mark.asyncio 测试在 teardown 时会清空当前线程的
    event loop（asyncio.set_event_loop(None)），导致后续 get_event_loop() 抛
    RuntimeError。asyncio.run 每次新建+关闭 loop，不受全局 loop 状态污染。

    重要：所有 asyncio 原语（gather / Semaphore / Event / Lock）必须在传入的
    coroutine 内部创建，否则会绑到调用时的 loop，与 asyncio.run 新建的 loop 冲突。
    本文件中带 gather 的用例均用 async _scenario() 包装就是这个原因。
    """
    return asyncio.run(coro)


# ── 构造与 spawn ───────────────────────────────────────────


class TestAsyncCoordinatorInit:
    """AsyncMultiAgentCoordinator 构造与 spawn_team。"""

    def test_requires_tool_executor(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        assert callable(coord.execute_tool)

    def test_default_max_workers(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        assert coord.max_workers == 4

    def test_custom_max_workers(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok", max_workers=2)
        assert coord.max_workers == 2

    def test_starts_empty(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        assert coord.agents == []
        assert coord.tasks == []

    def test_spawn_team_default_roles(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        coord.spawn_team()
        roles = [a.role for a in coord.agents]
        assert "reviewer" in roles
        assert "debugger" in roles
        assert "implementer" in roles
        assert "tester" in roles

    def test_spawn_team_respects_max_workers(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok", max_workers=2)
        coord.spawn_team(["a", "b", "c", "d"])
        assert len(coord.agents) == 2  # capped


# ── decompose（与同步版逻辑一致）──────────────────────────


class TestAsyncDecompose:
    """async 版 decompose 与同步版逻辑一致（共用 _decompose_goal）。"""

    def test_review_pattern(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        tasks = coord.decompose("review the code")
        assert len(tasks) >= 3
        dependent = [t for t in tasks if t.depends_on]
        assert len(dependent) > 0

    def test_debug_pattern(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        tasks = coord.decompose("debug the failing test")
        assert len(tasks) >= 3

    def test_default_pattern_first_task_independent(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        tasks = coord.decompose("analyze performance")
        assert tasks[0].depends_on == []

    def test_each_task_has_tool_sequence(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        tasks = coord.decompose("review code")
        for t in tasks:
            assert len(t.tool_sequence) >= 1


# ── execute（核心 async 流程）──────────────────────────────


class TestAsyncExecute:
    """async execute() 的端到端流程。"""

    def test_execute_returns_result_dict(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        result = _run(coord.execute("review the code"))
        assert isinstance(result, dict)
        for key in ("goal", "tasks_total", "tasks_done", "tasks_failed", "elapsed", "results", "log"):
            assert key in result, f"缺 key: {key}"

    def test_execute_with_working_sync_executor(self):
        """同步 executor（自动 to_thread 包装）。"""

        def executor(tool, args):
            return f"executed {tool}"

        coord = AsyncMultiAgentCoordinator(executor)
        result = _run(coord.execute("investigate architecture"))
        assert result["tasks_total"] >= 3
        assert result["tasks_done"] == result["tasks_total"]
        assert result["tasks_failed"] == 0
        # 每个完成的任务都有结果
        assert len(result["results"]) == result["tasks_done"]

    def test_execute_with_async_executor(self):
        """async executor（直接 await）。"""

        async def executor(tool, args):
            await asyncio.sleep(0)  # 让出事件循环
            return f"async-{tool}"

        coord = AsyncMultiAgentCoordinator(executor)
        result = _run(coord.execute("review code"))
        assert result["tasks_done"] == result["tasks_total"]
        # 验证 async executor 被调用（结果含 "async-" 前缀）
        for r in result["results"].values():
            assert "async-" in r

    def test_execute_logs_decomposition(self):
        coord = AsyncMultiAgentCoordinator(lambda t, a: "ok")
        result = _run(coord.execute("review code"))
        log_events = [e["event"] for e in result["log"]]
        assert "decomposed" in log_events

    def test_failed_task_marks_status(self):
        """executor 抛异常 → 任务标记 failed。"""

        def failing_executor(tool, args):
            raise RuntimeError("boom")

        coord = AsyncMultiAgentCoordinator(failing_executor)
        result = _run(coord.execute("review code"))
        assert result["tasks_failed"] == result["tasks_total"]
        assert result["tasks_done"] == 0


# ── 依赖感知调度（核心新增能力）──────────────────────────


class TestDependencyAwareScheduling:
    """asyncio 版真正按 depends_on 拓扑调度（同步版只 round-robin）。"""

    def test_dependent_task_starts_after_dependency(self):
        """后置任务的启动时间必须 >= 前置任务的完成时间。

        通过记录每个任务的 started_at/finished_at，验证依赖链顺序。
        """
        started_times: dict[str, float] = {}
        finished_times: dict[str, float] = {}

        async def executor(tool, args):
            # 每个 tool 调用睡 20ms，确保有时间差可观测
            await asyncio.sleep(0.02)
            return "ok"

        coord = AsyncMultiAgentCoordinator(executor)
        # 手工构造明确的依赖链：t1 → t2 → t3
        coord.tasks = [
            AgentTask("t1", "first", [{"tool": "x", "args": {}}]),
            AgentTask("t2", "second", [{"tool": "x", "args": {}}], depends_on=["t1"]),
            AgentTask("t3", "third", [{"tool": "x", "args": {}}], depends_on=["t2"]),
        ]
        coord.spawn_team()

        # 包装 _execute_task 以记录时间戳
        orig_exec = coord._execute_task

        async def _traced(task):
            await orig_exec(task)
            started_times[task.id] = task.started_at
            finished_times[task.id] = task.finished_at

        coord._execute_task = _traced
        # 复用 execute 的调度逻辑（但 tasks 已手工设置，跳过 decompose）
        import time as _time

        _started = _time.time()
        coord._log = []
        coord._results = {}
        coord._sem = asyncio.Semaphore(coord.max_workers)

        async def _run_manual():
            waves = _topological_waves(coord.tasks)
            for wave in waves:
                await asyncio.gather(*(_traced(t) for t in wave))

        _run(_run_manual())

        # 依赖链必须顺序执行：t2.started >= t1.finished, t3.started >= t2.finished
        assert started_times["t2"] >= finished_times["t1"] - 0.01  # 容差
        assert started_times["t3"] >= finished_times["t2"] - 0.01

    def test_independent_tasks_run_in_parallel(self):
        """无依赖的任务应该并行（总耗时 ≈ 单任务，而非 N 倍）。"""

        async def executor(tool, args):
            await asyncio.sleep(0.1)
            return "ok"

        async def _scenario():
            coord = AsyncMultiAgentCoordinator(executor, max_workers=4)
            # 3 个无依赖任务
            coord.tasks = [
                AgentTask("a", "a", [{"tool": "x", "args": {}}]),
                AgentTask("b", "b", [{"tool": "x", "args": {}}]),
                AgentTask("c", "c", [{"tool": "x", "args": {}}]),
            ]
            coord.spawn_team()
            # gather 必须在 event loop 内创建，否则绑到错误 loop（asyncio.run 契约）
            await asyncio.gather(*(coord._execute_task(t) for t in coord.tasks))

        started = time.time()
        _run(_scenario())
        elapsed = time.time() - started

        # 并行：3 个 0.1s 任务总耗时应 < 0.3s（允许调度开销，但远小于串行）
        assert elapsed < 0.25, f"任务未并行执行，耗时 {elapsed:.2f}s"

    def test_dependency_chain_does_not_deadlock(self):
        """长依赖链不应死锁（拓扑分层正确推进）。"""

        async def executor(tool, args):
            return "ok"

        coord = AsyncMultiAgentCoordinator(executor)
        # 5 层依赖链：t1 → t2 → t3 → t4 → t5
        coord.tasks = [
            AgentTask("t1", "1", [{"tool": "x", "args": {}}]),
            AgentTask("t2", "2", [{"tool": "x", "args": {}}], depends_on=["t1"]),
            AgentTask("t3", "3", [{"tool": "x", "args": {}}], depends_on=["t2"]),
            AgentTask("t4", "4", [{"tool": "x", "args": {}}], depends_on=["t3"]),
            AgentTask("t5", "5", [{"tool": "x", "args": {}}], depends_on=["t4"]),
        ]
        coord.spawn_team()
        # _sem 由 _execute_task 入口的 _ensure_runtime 兜底创建，无需手动初始化

        async def _run_manual():
            waves = _topological_waves(coord.tasks)
            for wave in waves:
                await asyncio.gather(*(coord._execute_task(t) for t in wave))

        _run(_run_manual())

        # 所有任务都应完成（没死锁）
        statuses = [t.status for t in coord.tasks]
        assert all(s == "done" for s in statuses), f"有任务未完成: {statuses}"


# ── _topological_waves（纯函数）───────────────────────────


class TestTopologicalWaves:
    """_topological_waves 的分层逻辑。"""

    def test_independent_tasks_single_wave(self):
        tasks = [
            AgentTask("a", "a"),
            AgentTask("b", "b"),
            AgentTask("c", "c"),
        ]
        waves = _topological_waves(tasks)
        assert len(waves) == 1
        assert {t.id for t in waves[0]} == {"a", "b", "c"}

    def test_linear_chain_multiple_waves(self):
        tasks = [
            AgentTask("t1", "1"),
            AgentTask("t2", "2", depends_on=["t1"]),
            AgentTask("t3", "3", depends_on=["t2"]),
        ]
        waves = _topological_waves(tasks)
        assert len(waves) == 3
        assert waves[0][0].id == "t1"
        assert waves[1][0].id == "t2"
        assert waves[2][0].id == "t3"

    def test_diamond_dependency(self):
        """菱形依赖：a → {b, c} → d。b/c 同波，d 单独一波。"""
        tasks = [
            AgentTask("a", "a"),
            AgentTask("b", "b", depends_on=["a"]),
            AgentTask("c", "c", depends_on=["a"]),
            AgentTask("d", "d", depends_on=["b", "c"]),
        ]
        waves = _topological_waves(tasks)
        assert len(waves) == 3
        assert {t.id for t in waves[0]} == {"a"}
        assert {t.id for t in waves[1]} == {"b", "c"}
        assert {t.id for t in waves[2]} == {"d"}

    def test_cycle_raises(self):
        """依赖环应抛 ValueError（防死锁）。"""
        tasks = [
            AgentTask("a", "a", depends_on=["b"]),
            AgentTask("b", "b", depends_on=["a"]),
        ]
        with pytest.raises(ValueError, match="环"):
            _topological_waves(tasks)

    def test_external_dependency_ignored(self):
        """依赖指向任务集外（不在 by_id）→ 视为可立即执行。"""
        tasks = [AgentTask("a", "a", depends_on=["external"])]
        waves = _topological_waves(tasks)
        assert len(waves) == 1
        assert waves[0][0].id == "a"


# ── max_workers 并发上限 ───────────────────────────────────


class TestConcurrencyLimit:
    """asyncio.Semaphore(max_workers) 限制同时在途任务数。"""

    def test_max_workers_limits_concurrency(self):
        """max_workers=2 时，同时运行的任务不超过 2。"""
        current = 0
        peak = 0

        async def executor(tool, args):
            nonlocal current, peak
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.05)
            current -= 1
            return "ok"

        async def _scenario():
            coord = AsyncMultiAgentCoordinator(executor, max_workers=2)
            # 4 个无依赖任务，理论上能同时跑 4 个，但被 semaphore 限到 2
            coord.tasks = [AgentTask(f"t{i}", f"task {i}", [{"tool": "x", "args": {}}]) for i in range(4)]
            coord.spawn_team()
            coord._log = []
            coord._results = {}
            # Semaphore 必须在 event loop 内构造，否则绑到错误 loop（asyncio.run 契约）
            coord._sem = asyncio.Semaphore(coord.max_workers)
            # gather 同理：在 loop 内创建，避免跨 loop 附加
            await asyncio.gather(*(coord._execute_task(t) for t in coord.tasks))

        _run(_scenario())
        assert peak <= 2, f"并发超过 max_workers，peak={peak}"


# ── async_coordinate 顶层入口 ──────────────────────────────


class TestAsyncCoordinateFunction:
    """模块级 async_coordinate() helper。"""

    def test_async_coordinate_runs_pipeline(self):
        result = _run(async_coordinate("review code", lambda t, a: "ok"))
        assert isinstance(result, dict)
        assert "tasks_total" in result
        assert result["tasks_total"] >= 3

    def test_async_coordinate_with_async_executor(self):
        async def executor(tool, args):
            return f"done-{tool}"

        result = _run(async_coordinate("analyze x", executor))
        assert result["tasks_done"] == result["tasks_total"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
