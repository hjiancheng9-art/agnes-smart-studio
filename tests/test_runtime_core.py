"""Tests for new core modules: runtime_types, runtime_result, tool_executor."""

from __future__ import annotations

from core.runtime_types import ExecutionMode, ExecutionPlan, plan_from_policy


class TestRuntimeTypes:
    def test_plan_orchestrate(self):
        """Self-audit keyword + scope + action → ORCHESTRATE (semantic, not len>40)."""
        plan = plan_from_policy("请自检整个系统的代码质量，全面审计并修复安全漏洞")
        assert plan.mode == ExecutionMode.ORCHESTRATE
        assert plan.complexity >= 3
        assert plan.use_orchestrator is True

    def test_plan_direct(self):
        plan = plan_from_policy("hello world")
        assert plan.mode == ExecutionMode.DIRECT
        assert plan.complexity <= 2

    def test_short_self_check_keyword_does_not_trigger_orchestrate(self):
        """Regression: casual single-keyword mentions (no scope/action)
        must NOT escalate to ORCHESTRATE. Guards the semantic-feature
        logic in execution_policy.choose_policy.
        """
        for casual in ("帮我自检一下", "这个要自修吗", "audit 一下", "自修吗"):
            plan = plan_from_policy(casual)
            assert plan.mode == ExecutionMode.DIRECT, f"短 prompt 不该触发编排: {casual!r} → {plan.mode}"

    def test_execution_plan_fields(self):
        plan = ExecutionPlan(
            complexity=2,
            mode=ExecutionMode.ORCHESTRATE,
            model_alias="pro",
            tool_names=("read_file", "orchestrate"),
            use_orchestrator=True,
            use_swarm=False,
        )
        assert plan.complexity == 2
        assert plan.mode == ExecutionMode.ORCHESTRATE
        assert "orchestrate" in plan.tool_names
        assert plan.use_orchestrator is True
        assert plan.use_swarm is False


class TestRuntimeResult:
    def test_tool_result_ok(self):
        from core.runtime_result import ToolResult

        r = ToolResult.from_raw(("hello world", [("info", "done")]))
        assert r.ok is True
        assert r.content == "hello world"

    def test_tool_result_error(self):
        from core.runtime_result import ToolResult

        r = ToolResult.from_raw(("[错误] something failed", []))
        assert r.ok is False
        assert r.error_code == "tool_error"

    def test_tool_result_timeout(self):
        from core.runtime_result import ToolResult

        r = ToolResult.from_raw(("[超时] run_bash 超时(120s)", []))
        assert r.ok is False
        assert r.error_code == "tool_timeout"


class TestToolExecutor:
    def test_executor_creation(self):
        from core.tool_executor import ToolExecutor

        executor = ToolExecutor(lambda n, a: (f"ok {n}", []))
        assert executor is not None

    def test_executor_execute_sync(self):
        from core.tool_executor import ToolExecutor

        calls = []

        def fake_dispatch(name, args):
            calls.append(name)
            return (f"result for {name}", [])

        executor = ToolExecutor(fake_dispatch)
        import asyncio

        result = asyncio.run(executor.execute("run_bash", {"command": "echo hi"}))
        assert "run_bash" in calls
        assert result is not None
