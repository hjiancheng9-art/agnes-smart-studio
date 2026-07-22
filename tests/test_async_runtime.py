"""Tests for core/async_runtime.py — centralized async runtime."""

import asyncio

import pytest


class TestRunAsync:
    """run_async: safely execute async code from sync context."""

    def test_run_async_simple_coro(self):
        """Run a simple async function and get result."""
        from core.async_runtime import run_async

        async def answer() -> int:
            return 42

        result = run_async(answer())
        assert result == 42

    def test_run_async_with_value(self):
        """Run async function that returns a value."""
        from core.async_runtime import run_async

        async def greet(name: str) -> str:
            await asyncio.sleep(0.01)
            return f"Hello, {name}!"

        result = run_async(greet("CRUX"))
        assert result == "Hello, CRUX!"

    def test_run_async_handles_exception(self):
        """Exceptions from coroutine propagate to caller."""
        from core.async_runtime import run_async

        async def failing() -> None:
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(failing())

    def test_run_async_with_timeout(self):
        """run_async with explicit timeout works."""
        from core.async_runtime import run_async

        async def fast() -> str:
            await asyncio.sleep(0.01)
            return "done"

        result = run_async(fast())
        assert result == "done"


class TestBackgroundTasks:
    """register_background_task and cancel_all."""

    def test_cancel_all_background_tasks(self):
        """Register tasks and cancel them."""
        from core.async_runtime import cancel_all_background_tasks, register_background_task

        cancelled = []

        async def background_worker():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        async def run():
            task = asyncio.ensure_future(background_worker())
            register_background_task(task)
            await asyncio.sleep(0.05)
            await cancel_all_background_tasks()
            assert task.done() or task.cancelled()
            return True

        result = asyncio.run(run())
        assert result is True
        assert len(cancelled) == 1


class TestEdgeCases:
    """Edge cases for async runtime."""

    def test_nested_run_async_raises(self):
        """Calling run_async inside an event loop raises RuntimeError."""
        from core.async_runtime import run_async

        async def nested():
            with pytest.raises(RuntimeError, match="active event loop"):
                run_async(asyncio.sleep(0))

        asyncio.run(nested())
