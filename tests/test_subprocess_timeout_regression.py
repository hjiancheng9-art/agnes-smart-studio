"""Regression tests for the subprocess timeout-hang root cause.

Root cause (fixed): run_subprocess killed only the direct child on timeout, so a
grandchild that inherited the pipes kept them open and communicate() blocked
until the grandchild died — freezing the whole agent. SafeExecutor also never
enforced its documented timeout.

These tests pin the fix: a timeout must free the caller within a tight budget,
even when a grandchild holds the pipes, and SafeExecutor must abandon a wedged
tool instead of blocking forever.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time

import pytest

from core.mcp_servers._mcp_utils import run_subprocess, run_subprocess_async
from core.resilience import SafeExecutor


def test_run_subprocess_success():
    r = run_subprocess([sys.executable, "-c", "print('ok')"], timeout=10)
    assert r.returncode == 0
    assert "ok" in r.stdout


def test_run_subprocess_simple_timeout_is_prompt():
    t0 = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        run_subprocess([sys.executable, "-c", "import time;time.sleep(30)"], timeout=2)
    # Must return close to the timeout, not after the full sleep.
    assert time.time() - t0 < 8, "timeout did not free the caller promptly"


def test_run_subprocess_grandchild_pipe_does_not_hang():
    """The exact bug: a grandchild inherits the pipes and sleeps 60s."""
    code = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "time.sleep(60)"
    )
    t0 = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        run_subprocess([sys.executable, "-c", code], timeout=3)
    elapsed = time.time() - t0
    # Before the fix this took ~60s; after the fix it must be well under that.
    assert elapsed < 15, f"grandchild pipe still hangs the caller: {elapsed:.1f}s"


def test_run_subprocess_inside_running_loop_does_not_hang():
    code = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "time.sleep(60)"
    )

    async def _main():
        t0 = time.time()
        with pytest.raises(subprocess.TimeoutExpired):
            run_subprocess([sys.executable, "-c", code], timeout=3)
        return time.time() - t0

    elapsed = asyncio.run(_main())
    assert elapsed < 25, f"ThreadPoolExecutor branch still blocks: {elapsed:.1f}s"


def test_async_runner_timeout_is_prompt():
    async def _main():
        t0 = time.time()
        with pytest.raises(subprocess.TimeoutExpired):
            await run_subprocess_async(
                [sys.executable, "-c", "import time;time.sleep(30)"], timeout=2
            )
        return time.time() - t0

    elapsed = asyncio.run(_main())
    assert elapsed < 10


def test_safeexecutor_enforces_timeout():
    se = SafeExecutor(timeout=2)

    def _wedged(**_kw):
        time.sleep(30)
        return "should never be seen"

    t0 = time.time()
    res = se.execute("wedged_tool", _wedged, {})
    elapsed = time.time() - t0
    assert elapsed < 6, f"SafeExecutor blocked on a wedged tool: {elapsed:.1f}s"
    assert res["success"] is False
    assert res["error_type"] == "timeout"


def test_safeexecutor_success_path():
    se = SafeExecutor(timeout=10)

    def _tool(x: str = "") -> str:
        return f"got:{x}"

    res = se.execute("ok_tool", _tool, {"x": "hi"})
    assert res["success"] is True
    assert res["result"] == "got:hi"
