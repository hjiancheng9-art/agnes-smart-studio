"""Tests for core/tool_executor.py — async tool execution with timeout control.

Functions tested:
  - ToolSpec.for_tool(name) -> ToolSpec
  - ToolExecutor.__init__(dispatch_fn, tool_registry)
  - ToolExecutor.execute(tool_name, tool_args)
  - ToolExecutor.cancel_all()
"""

import asyncio

import pytest

from core.tool_executor import BROWSER_TIMEOUT, DEFAULT_TIMEOUT, ToolExecutor, ToolSpec
from core.tool_outcome import ToolOutcome, ToolStatus

# ── ToolSpec ─────────────────────────────────────────────────────


class TestToolSpec:
    """ToolSpec.for_tool() heuristic defaults based on tool name."""

    def test_default_timeout(self):
        spec = ToolSpec.for_tool("read_file")
        assert spec.timeout_s == DEFAULT_TIMEOUT
        assert spec.slow is False
        assert spec.idempotent is False

    def test_browser_tools_get_browser_timeout(self):
        for name in ("browser_ai", "cdp_chatgpt", "pw_worker", "read_browser_page"):
            spec = ToolSpec.for_tool(name)
            assert spec.timeout_s == BROWSER_TIMEOUT, f"Expected {BROWSER_TIMEOUT} for {name}, got {spec.timeout_s}"
            assert spec.slow is True

    def test_generation_tools_get_long_timeout(self):
        for name in ("generate_video", "generate_image", "transcribe"):
            spec = ToolSpec.for_tool(name)
            assert spec.timeout_s == 180.0, f"Expected 180.0 for {name}, got {spec.timeout_s}"
            assert spec.slow is True

    def test_long_running_tools_get_300_timeout(self):
        for name in ("run_test", "execute_plan", "orchestrate"):
            spec = ToolSpec.for_tool(name)
            assert spec.timeout_s == 300.0, f"Expected 300.0 for {name}, got {spec.timeout_s}"
            assert spec.slow is True

    def test_git_tools_get_30_timeout(self):
        for name in ("git_status", "github_pr_create"):
            spec = ToolSpec.for_tool(name)
            assert spec.timeout_s == 30.0, f"Expected 30.0 for {name}, got {spec.timeout_s}"

    def test_for_tool_is_classmethod(self):
        spec = ToolSpec.for_tool("some_tool")
        assert isinstance(spec, ToolSpec)
        assert spec.name == "some_tool"


# ── ToolExecutor ─────────────────────────────────────────────────


def _make_dispatch(ret_val="ok", side_effects=None):
    """Factory for dispatch functions."""

    def dispatch(tool_name, args_json):
        return (ret_val, side_effects or {})

    return dispatch


class TestToolExecutorConstructor:
    """ToolExecutor.__init__ stores dispatch and registry."""

    def test_init_stores_dispatch(self):
        fn = _make_dispatch("hello")
        ex = ToolExecutor(fn)
        assert ex._dispatch is fn

    def test_init_stores_registry(self):
        registry = object()
        ex = ToolExecutor(_make_dispatch(), tool_registry=registry)
        assert ex._registry is registry

    def test_init_empty_active_tasks(self):
        ex = ToolExecutor(_make_dispatch())
        assert ex._active_tasks == {}


class TestToolExecutorExecute:
    """ToolExecutor.execute runs a tool and returns ToolOutcome."""

    @pytest.mark.asyncio
    async def test_execute_returns_tool_outcome(self):
        def dispatch(tool_name, args_json):
            return ("result_ok", {})

        ex = ToolExecutor(dispatch)
        outcome = await ex.execute("test_tool", {"x": 1})
        assert isinstance(outcome, ToolOutcome)

    @pytest.mark.asyncio
    async def test_execute_successful_tool(self):
        def dispatch(tool_name, args_json):
            return ("success_value", {})

        ex = ToolExecutor(dispatch)
        outcome = await ex.execute("echo", {"msg": "hello"})
        assert outcome.status == ToolStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_execute_clears_active_task_on_completion(self):
        def dispatch(tool_name, args_json):
            return ("done", {})

        ex = ToolExecutor(dispatch)
        await ex.execute("test_tool", {})
        assert "test_tool" not in ex._active_tasks

    @pytest.mark.asyncio
    async def test_execute_with_timeout_override(self):
        def dispatch(tool_name, args_json):
            return ("done", {})

        ex = ToolExecutor(dispatch)
        outcome = await ex.execute("test_tool", {}, timeout_s=5.0)
        assert outcome.status == ToolStatus.SUCCEEDED


class TestCancelAll:
    """cancel_all cancels all in-flight tasks."""

    @pytest.mark.asyncio
    async def test_cancel_all_cancels_active_tasks(self):
        import threading

        slow_started = threading.Event()

        def slow_dispatch(tool_name, args_json):
            slow_started.set()
            import time

            time.sleep(10)
            return ("never_reached", {})

        ex = ToolExecutor(slow_dispatch)
        # Start a task that will be cancelled
        task = asyncio.create_task(ex.execute("slow_tool", {}))
        # Wait until dispatch has started
        await asyncio.get_event_loop().run_in_executor(None, slow_started.wait)
        await asyncio.sleep(0.1)

        ex.cancel_all()

        # The CancelledError is caught internally and returns a cancelled outcome
        outcome = await task
        assert outcome.status == ToolStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_all_no_active_tasks_safe(self):
        ex = ToolExecutor(_make_dispatch())
        # Should not raise
        ex.cancel_all()

    @pytest.mark.asyncio
    async def test_cancel_all_removes_tasks_from_active(self):
        import threading

        slow_started = threading.Event()

        def slow_dispatch(tool_name, args_json):
            slow_started.set()
            import time

            time.sleep(10)
            return ("never_reached", {})

        ex = ToolExecutor(slow_dispatch)
        task = asyncio.create_task(ex.execute("slow_tool", {}))  # noqa: F841, RUF006
        await asyncio.get_event_loop().run_in_executor(None, slow_started.wait)
        await asyncio.sleep(0.1)

        assert "slow_tool" in ex._active_tasks
        ex.cancel_all()

        # After cancel, the tasks are popped from active_tasks
        # (because the finally block runs)
        await asyncio.sleep(0.1)
        assert "slow_tool" not in ex._active_tasks
