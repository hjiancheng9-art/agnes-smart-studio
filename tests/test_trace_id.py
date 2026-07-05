"""Tests for AgentTask trace_id and root_trace_id propagation."""

import uuid
from core.multi_agent_models import AgentTask


class TestTraceId:
    def test_auto_generation(self):
        """每个新 AgentTask 自动获得 16 位 hex trace_id."""
        t = AgentTask(id="t1", description="test")
        assert len(t.trace_id) == 16
        assert all(c in "0123456789abcdef" for c in t.trace_id)

    def test_custom_trace_id(self):
        """手动传入 trace_id 不被覆盖."""
        t = AgentTask(id="t2", description="test", trace_id="my_custom_id")
        assert t.trace_id == "my_custom_id"

    def test_unique_trace_ids(self):
        """连续创建的任务 trace_id 互不相同."""
        tasks = [AgentTask(id=f"t{i}", description=str(i)) for i in range(10)]
        ids = [t.trace_id for t in tasks]
        assert len(set(ids)) == 10

    def test_root_trace_id_defaults_to_trace_id(self):
        """root_trace_id 默认等于 trace_id（独立任务场景）. """
        t = AgentTask(id="t3", description="standalone")
        assert t.root_trace_id == t.trace_id

    def test_root_trace_id_shared_after_execute(self):
        """一次 execute 的所有任务共享同一个 root_trace_id. """
        from core.multi_agent import MultiAgentCoordinator

        captured = []
        def fake_exec(tool, args):
            captured.append(args.get("_root_trace_id"))
            return "ok"

        coord = MultiAgentCoordinator(fake_exec)
        result = coord.execute("explore current directory briefly")

        root_ids = set()
        for task in coord.tasks:
            root_ids.add(task.root_trace_id)
            assert len(task.root_trace_id) == 16
        assert len(root_ids) == 1, f"Expected 1 root_trace_id, got {len(root_ids)}"
        # 日志中也应有 root_trace_id
        log_roots = [e.get("root_trace_id") for e in coord._log if "root_trace_id" in e]
        assert len(log_roots) > 0
        assert log_roots[0] == list(root_ids)[0]

    def test_root_trace_id_in_step_args_sync(self):
        """同步路径：step_args 同时携带 _trace_id 和 _root_trace_id. """
        from core.multi_agent import MultiAgentCoordinator

        captured = []
        def fake_executor(tool, args):
            captured.append(args)
            return "ok"

        coord = MultiAgentCoordinator(fake_executor)
        task = AgentTask(id="root_test", description="check root injection",
                         tool_sequence=[{"tool": "echo", "args": {"msg": "hi"}}])
        coord.tasks = [task]
        # 模拟 execute 已经设置 root_trace_id
        task.root_trace_id = "test_root_123456"
        coord._execute_task(task)

        assert len(captured) == 1
        assert captured[0].get("_trace_id") == task.trace_id
        assert captured[0].get("_root_trace_id") == "test_root_123456"

    def test_root_trace_id_in_log_sync(self):
        """同步路径：日志记录同时包含 trace_id 和 root_trace_id. """
        from core.multi_agent import MultiAgentCoordinator

        def fake_exec(tool, args):
            return "ok"

        coord = MultiAgentCoordinator(fake_exec)
        coord.execute("explore current directory briefly")

        for entry in coord._log:
            if "trace_id" in entry:
                assert "root_trace_id" in entry, f"Log entry missing root_trace_id: {entry.get('event')}"
                assert entry["root_trace_id"] == coord.tasks[0].root_trace_id

    def test_root_trace_id_in_log_async(self):
        """异步路径：日志记录同时包含 trace_id 和 root_trace_id. """
        import asyncio
        from core.multi_agent import AsyncMultiAgentCoordinator

        async def fake_exec(tool, args):
            return "ok"

        async def run():
            coord = AsyncMultiAgentCoordinator(fake_exec)
            task = AgentTask(id="async_root", description="check async root",
                             tool_sequence=[{"tool": "echo", "args": {"msg": "async"}}])
            coord.tasks = [task]
            task.root_trace_id = "async_root_1234"
            await coord._execute_task(task)
            return coord

        coord = asyncio.run(run())
        for entry in coord._log:
            if "trace_id" in entry:
                assert "root_trace_id" in entry, f"Async log missing root_trace_id: {entry.get('event')}"
                assert entry["root_trace_id"] == "async_root_1234"
