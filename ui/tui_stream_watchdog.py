"""
Stream Watchdog — TUI 侧超时监控
==================================
解决：stream 中断但没有 stream_end，TUI 还显示 spinner。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .tui_dispatcher import TuiDispatcher
from .tui_run_state import RunStateStore

logger = logging.getLogger(__name__)


class StreamWatchdog:
    """流式看门狗 — 检测无事件超时并自动收尾"""

    def __init__(self, run_store: RunStateStore, dispatcher: TuiDispatcher, timeout_sec: float = 90.0):
        self.run_store = run_store
        self.dispatcher = dispatcher
        self.timeout_sec = timeout_sec
        self._last_tick = 0.0

    def tick(self) -> list[dict[str, Any]]:
        """执行一轮检查，返回超时产生的 action 列表"""
        actions: list[dict[str, Any]] = []
        now = time.time()

        for run_id, state in list(self.run_store.runs.items()):
            if not state.is_streaming:
                continue

            idle = now - state.last_event_at

            if idle > self.timeout_sec:
                state.status = "ERROR"
                state.is_streaming = False
                state.error = f"Stream idle timeout after {self.timeout_sec}s"

                action = {
                    "type": "error",
                    "run_id": run_id,
                    "error": f"Stream idle timeout after {self.timeout_sec}s",
                    "state": state,
                }
                actions.append(action)
                logger.warning(f"StreamWatchdog: run {run_id} timed out ({self.timeout_sec}s idle)")

        self._last_tick = now
        return actions

    def run_loop(self) -> None:
        """运行主循环（在 TUI 的主循环中调用）"""
        actions = self.tick()
        if actions:
            self.dispatcher.dispatch_batch(actions)
