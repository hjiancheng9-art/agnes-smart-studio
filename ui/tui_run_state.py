"""
TUI Run State Store — 每个 run_id 独立状态管理
================================================
解决：状态栏不归位、多个 run_id 并发串台、stream_end 后消息没 close。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TuiRunState:
    """单个会话的运行状态"""

    run_id: str
    status: str = "STARTED"
    phase: str = ""
    is_streaming: bool = True
    message: str = ""
    error: str = ""
    last_event_at: float = 0.0
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        now = time.time()
        if not self.last_event_at:
            self.last_event_at = now
        if not self.created_at:
            self.created_at = now


class RunStateStore:
    """运行状态仓库 — 管理所有 run_id 的状态"""

    def __init__(self, max_runs: int = 100):
        self._runs: dict[str, TuiRunState] = {}
        self._max_runs = max_runs

    @property
    def runs(self) -> dict[str, TuiRunState]:
        return self._runs

    def get(self, run_id: str) -> TuiRunState:
        """获取或创建状态"""
        if run_id not in self._runs:
            if len(self._runs) >= self._max_runs:
                # 移除最旧的非活跃 run
                oldest = min(
                    (r for r in self._runs.values() if not r.is_streaming),
                    key=lambda r: r.last_event_at,
                    default=None,
                )
                if oldest:
                    del self._runs[oldest.run_id]
            self._runs[run_id] = TuiRunState(run_id=run_id)
        return self._runs[run_id]

    def update(self, run_id: str, **kwargs) -> TuiRunState:
        """更新状态"""
        state = self.get(run_id)
        for key, val in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, val)
        state.last_event_at = time.time()
        return state

    def finish(self, run_id: str, status: str = "DONE") -> TuiRunState:
        """标记完成"""
        return self.update(
            run_id,
            status=status,
            is_streaming=False,
            phase="stream_end",
        )

    def error(self, run_id: str, error: str) -> TuiRunState:
        """标记错误"""
        return self.update(
            run_id,
            status="ERROR",
            is_streaming=False,
            phase="error",
            error=error,
        )

    def get_active(self) -> list[TuiRunState]:
        """获取所有活跃 run"""
        return [s for s in self._runs.values() if s.is_streaming]

    def cleanup(self, max_age: float = 300) -> int:
        """清理过期非活跃 run"""
        now = time.time()
        to_remove = [rid for rid, s in self._runs.items() if not s.is_streaming and now - s.last_event_at > max_age]
        for rid in to_remove:
            del self._runs[rid]
        return len(to_remove)

    def stats(self) -> dict[str, int]:
        return {
            "total": len(self._runs),
            "active": len(self.get_active()),
        }
