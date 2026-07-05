"""Tests for AgentTask trace_id propagation."""

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

    def test_injected_into_step_args_sync(self):
        """同步路径：trace_id 被注入 step args."""
        from core.multi_agent import MultiAgentCoordinator

        captured: list[dict] = []

        def fake_executor(tool: str, args: dict) -> str:
            captured.append(args)
            return "ok"

        coord = MultiAgentCoordinator(fake_executor)
        task = AgentTask(id="trace_test", description="check injection",
                         tool_sequence=[{"tool": "echo", "args": {"msg": "hello"}}])
        coord.tasks = [task]
        coord._execute_task(task)

        assert len(captured) == 1
        assert captured[0].get("_trace_id") == task.trace_id, \
            f"Expected {task.trace_id}, got {captured[0].get('_trace_id')}"

    def test_injected_into_step_args_async(self):
        """异步路径：trace_id 被注入 step args."""
        import asyncio
        from core.multi_agent import AsyncMultiAgentCoordinator

        captured: list[dict] = []

        async def fake_executor(tool: str, args: dict) -> str:
            captured.append(args)
            return "ok"

        async def run():
            coord = AsyncMultiAgentCoordinator(fake_executor)
            task = AgentTask(id="trace_test_async", description="check async injection",
                             tool_sequence=[{"tool": "echo", "args": {"msg": "async"}}])
            await coord._execute_task(task)

        asyncio.run(run())

        assert len(captured) == 1
        assert captured[0].get("_trace_id") is not None
