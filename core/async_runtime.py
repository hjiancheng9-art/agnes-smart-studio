"""Centralized async runtime — single event-loop owner for all CRUX components.

Prevents "event loop already running" deadlocks, nested asyncio.run() conflicts,
and ensures clean shutdown ordering.

Usage:
    from core.async_runtime import run_async
    result = run_async(some_coroutine())
"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Global task registry for clean shutdown
_pending_tasks: set[asyncio.Task] = set()


def run_async(coro: Coroutine[Any, Any, T], *, timeout: float | None = None) -> T:
    """Run an async coroutine safely. Handles both fresh and existing event loops.

    - If no loop is running: creates a new one via asyncio.run()
    - If a loop IS running (e.g. TUI or MCP context): raises RuntimeError to
      force the caller to use `await` directly — prevents nested event loops.

    Args:
        coro: The coroutine to run
        timeout: Optional timeout in seconds. Raises TimeoutError if exceeded.

    Raises:
        RuntimeError: If called inside an already-running event loop
        TimeoutError: If timeout is set and exceeded
    """
    try:
        _ = asyncio.get_running_loop()
    except RuntimeError:
        # No loop running — create one
        if timeout is not None:
            return asyncio.run(_with_timeout(coro, timeout))
        return asyncio.run(coro)

    # Loop already running — caller must await directly
    raise RuntimeError("Cannot call run_async() inside an active event loop. Use 'await coro' directly instead.")


async def _with_timeout(coro: Coroutine[Any, Any, T], timeout: float) -> T:
    """Wrap a coroutine with a timeout."""
    return await asyncio.wait_for(coro, timeout=timeout)


async def run_with_timeout(coro: Coroutine[Any, Any, T], timeout: float) -> T:
    """Await a coroutine with a hard timeout. For use inside existing event loops."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Async operation timed out after %.1fs", timeout)
        raise


def register_background_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Register a background task for lifecycle tracking.

    The task is added to _pending_tasks so cleanup can cancel all on shutdown.
    """
    task = asyncio.create_task(coro)
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
    return task


async def cancel_all_background_tasks() -> None:
    """Cancel all registered background tasks. Called during graceful shutdown."""
    for task in list(_pending_tasks):
        task.cancel()
    if _pending_tasks:
        await asyncio.gather(*_pending_tasks, return_exceptions=True)
    _pending_tasks.clear()
