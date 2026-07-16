"""UI Heartbeat + CDP Safe Executor + Mouse Mode Guard.

针对 TUI 鼠标/键盘/滚动间歇性失效问题的三合一修复方案。

问题根源：
1. CDP (Playwright) 操作在主 asyncio loop 执行，阻塞了 prompt_toolkit 的事件处理
2. 子进程/外部命令输出可能意外发送 ANSI 序列关闭 terminal mouse mode
3. CDP websocket 半断线后操作 hang 住不抛异常

修复策略：
- UIHeartbeat: 200ms 心跳检测主 loop 卡死
- CdpSafeExecutor: CDP 操作放到独立线程执行
- MouseModeGuard: 自动恢复 terminal mouse mode
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import os
import signal
import sys
import time
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ── Constants ──

HEARTBEAT_INTERVAL = 0.2  # 200ms
FREEZE_THRESHOLD = 1.0  # 1s 以上无心跳视为卡死
CDP_OP_TIMEOUT = 10.0  # CDP 操作超时
MOUSE_MODE_SEQ = "\033[?1000h\033[?1002h\033[?1015h\033[?1006h"
MOUSE_MODE_OFF_SEQ = "\033[?1000l\033[?1002l\033[?1015l\033[?1006l"

# ── 1. UI Heartbeat ──


class UIHeartbeat:
    """监控主线程事件循环是否卡死。

    在 prompt_toolkit 的 Application 主 loop 中每隔 200ms 打一个时间戳。
    如果超过 FREEZE_THRESHOLD 没有更新，说明主线程被某个操作阻塞了。
    """

    def __init__(self, app: Any = None, threshold: float = FREEZE_THRESHOLD):
        self.app = app
        self.threshold = threshold
        self._last_tick = time.monotonic()
        self._last_freeze_log = 0.0  # 防重复刷日志
        self._task: asyncio.Task | None = None
        self._running = False
        self.freeze_count = 0
        self.total_freeze_time = 0.0

    @property
    def is_frozen(self) -> bool:
        """是否正处于卡死状态。"""
        return (time.monotonic() - self._last_tick) > self.threshold

    @property
    def frozen_seconds(self) -> float:
        """已卡死秒数。"""
        return time.monotonic() - self._last_tick

    def tick(self):
        """手动打心跳（从外部调用）。"""
        self._last_tick = time.monotonic()

    async def _beat(self):
        """心跳协程。"""
        self._running = True
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = time.monotonic()
            gap = now - self._last_tick

            if gap > self.threshold:
                self.freeze_count += 1
                self.total_freeze_time += gap
                # 防重复刷：同一段卡死只记一次
                if now - self._last_freeze_log > 1.0:
                    self._last_freeze_log = now
                    logger.warning(
                        f"⚠ UI LOOP FROZEN {gap:.1f}s "
                        f"(total freeze: {self.total_freeze_time:.1f}s, "
                        f"count: {self.freeze_count})"
                    )
                    # 尝试触发 UI 刷新（如果有 app 引用）
                    if self.app and hasattr(self.app, "invalidate"):
                        try:
                            self.app.invalidate()
                        except Exception:
                            logger.debug("Exception in ui_heartbeat", exc_info=True)
            else:
                self._last_freeze_log = 0.0

            self._last_tick = now

    def start(self):
        """启动心跳检测。"""
        if self._task is not None:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._task = loop.create_task(self._beat())
                logger.info("UIHeartbeat started (interval=%.1fs, threshold=%.1fs)", HEARTBEAT_INTERVAL, self.threshold)
        except RuntimeError:
            logger.warning("No running event loop — UIHeartbeat deferred")

    def stop(self):
        """停止心跳检测。"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None


# ── 2. CDP Safe Executor ──


class CdpSafeExecutor:
    """将 CDP/Playwright 操作隔离到独立线程执行。

    原理：
    - 用 run_in_executor 把同步 CDP 操作交给线程池
    - 设置超时防止永久 hang
    - 操作前后自动 tick 心跳，让 UIHeartbeat 知道不是卡死

    用法：
        safe_cdp = CdpSafeExecutor(heartbeat)
        result = await safe_cdp.execute(lambda: page.evaluate("1+1"))
    """

    def __init__(
        self, heartbeat: UIHeartbeat | None = None, timeout: float = CDP_OP_TIMEOUT, thread_name: str = "cdp-worker"
    ):
        self.heartbeat = heartbeat
        self.timeout = timeout
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=thread_name,
        )
        self._op_count = 0
        self._fail_count = 0

    async def execute(
        self,
        fn: Callable[..., T],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T:
        """在独立线程中执行 CDP 操作，主 loop 不被阻塞。

        Args:
            fn: 同步或异步的可调用对象
            timeout: 超时秒数（默认 self.timeout）

        Returns:
            函数的返回值

        Raises:
            asyncio.TimeoutError: 操作超时
            Exception: 函数内部异常
        """
        t0 = time.monotonic()
        self._op_count += 1
        effective_timeout = timeout if timeout is not None else self.timeout

        # 心跳线程标记：告知 UIHeartbeat 这是 CDP 操作，不是卡死
        if self.heartbeat:
            self.heartbeat.tick()

        loop = asyncio.get_event_loop()

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(self._executor, fn, *args),
                timeout=effective_timeout,
            )
            elapsed = time.monotonic() - t0
            if elapsed > 0.5:
                logger.debug(f"CDP op completed in {elapsed:.2f}s ({self._op_count} total)")

            if self.heartbeat:
                self.heartbeat.tick()

            return result

        except asyncio.TimeoutError:
            self._fail_count += 1
            elapsed = time.monotonic() - t0
            logger.error(
                f"CDP op TIMEOUT after {elapsed:.1f}s "
                f"(timeout={effective_timeout}s, "
                f"fail_rate={self._fail_count}/{self._op_count})"
            )
            # 超时后强制 tick，让 UI 恢复
            if self.heartbeat:
                self.heartbeat.tick()
            raise

        except Exception as e:
            self._fail_count += 1
            logger.error(f"CDP op FAILED: {type(e).__name__}: {e}")
            if self.heartbeat:
                self.heartbeat.tick()
            raise

    async def health_check(self, browser_check: Callable[[], bool]) -> bool:
        """快速健康检查（2s 超时）。

        Args:
            browser_check: 返回 bool 的浏览器健康检查函数

        Returns:
            True=健康, False=失联
        """
        try:
            return await self.execute(browser_check, timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            return False

    def stats(self) -> dict:
        return {
            "total_ops": self._op_count,
            "failures": self._fail_count,
            "fail_rate": round(self._fail_count / max(self._op_count, 1), 4),
            "alive": not self._executor._shutdown,
        }

    def shutdown(self, wait: bool = True):
        """关闭线程池。"""
        self._executor.shutdown(wait=wait)


# ── 3. Mouse Mode Guard ──


class MouseModeGuard:
    """自动恢复 Terminal Mouse Mode。

    问题：
    - 子进程输出可能包含 ANSI 序列 \033[?1000l 关闭鼠标追踪
    - 窗口 focus 切换后 terminal 不自动重启用 mouse mode
    - prompt_toolkit 在事件处理异常时可能丢失 mouse state

    策略：
    - 每次 UI 渲染前检查并恢复
    - 提供 context manager 保护子进程执行
    - 定时刷新（由 UIHeartbeat 触发）
    """

    def __init__(self, stdout: Any | None = None):
        self.stdout = stdout or sys.stdout
        self._enabled = False
        self._restore_count = 0

    def enable(self):
        """启用 mouse mode。"""
        if os.name == "nt":
            # Windows Terminal 不完全支持 ANSI mouse mode，
            # 但 Windows Terminal / ConPTY 支持一部分
            pass
        self.stdout.write(MOUSE_MODE_SEQ)
        self.stdout.flush()
        self._enabled = True

    def disable(self):
        """关闭 mouse mode。"""
        self.stdout.write(MOUSE_MODE_OFF_SEQ)
        self.stdout.flush()
        self._enabled = False

    def restore(self):
        """恢复 mouse mode（在可能被关闭后调用）。"""
        self._restore_count += 1
        self.enable()

    @contextlib.contextmanager
    def protect(self):
        """保护子进程执行期间不丢失 mouse mode。

        用法：
            with mouse_guard.protect():
                subprocess.run(["some", "command"])
        """
        try:
            yield
        finally:
            # 子进程输出可能混入 ANSI 关闭序列，强制恢复
            self.restore()

    # ── Subprocess output filter ──

    @staticmethod
    def strip_mouse_ansi(data: str) -> str:
        """过滤子进程输出中的 mouse mode ANSI 关闭序列。

        这些序列如果漏到 terminal 会关闭鼠标追踪：
        \\033[?1000l, \\033[?1002l, \\033[?1015l, \\033[?1006l
        """
        # Remove common mouse-disable ANSI escape sequences
        result = data
        for ansi in ["\033[?1000l", "\033[?1002l", "\033[?1015l", "\033[?1006l"]:
            result = result.replace(ansi, "")
        return result

    def safe_subprocess_run(self, *args, **kwargs):
        """执行子进程并过滤其输出中的 mouse 破坏性 ANSI 序列。

        用法同 subprocess.run，但 stdout/stderr 会被过滤。
        """
        import subprocess

        # Capture output
        kwargs["capture_output"] = True
        kwargs["text"] = True
        kwargs.setdefault("timeout", 30)  # prevent hung subprocess
        result = subprocess.run(*args, **kwargs)
        # Filter ANSI sequences
        if result.stdout:
            result.stdout = self.strip_mouse_ansi(result.stdout)
        if result.stderr:
            result.stderr = self.strip_mouse_ansi(result.stderr)
        # Restore mouse mode after subprocess
        self.restore()
        return result

    @property
    def stats(self) -> dict:
        return {
            "enabled": self._enabled,
            "restore_count": self._restore_count,
        }


# ── 4. Convenience: freeze-safe asyncio sleep ──


async def safe_sleep(seconds: float, heartbeat: UIHeartbeat | None = None):
    """安全的 sleep，sleep 期间持续更新心跳。"""
    interval = min(seconds, 0.1)
    elapsed = 0.0
    while elapsed < seconds:
        await asyncio.sleep(interval)
        elapsed += interval
        if heartbeat:
            heartbeat.tick()


# ── 5. Integration helper ──


def patch_signal_handler(heartbeat: UIHeartbeat):
    """在信号处理器中打心跳。

    处理 SIGWINCH（窗口 resize）等信号时，可能触发 prompt_toolkit
    的渲染路径，此时也需要 tick 防止误报卡死。
    """
    original_handler = signal.getsignal(signal.SIGWINCH)

    def _handler(signum, frame):
        heartbeat.tick()
        if callable(original_handler):
            original_handler(signum, frame)

    try:
        signal.signal(signal.SIGWINCH, _handler)
    except (ValueError, RuntimeError):
        pass  # 不在主线程时忽略
