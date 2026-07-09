"""
Stream Protocol — 统一事件协议 + RunStatus 生命周期状态机
==========================================================
确保 TUI 和后端之间的事件格式一致、状态可追踪。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    """任务生命周期状态"""
    STARTED = "started"
    ROUTING = "routing"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    TOOL_RUNNING = "tool_running"
    CRITICIZING = "criticizing"
    REPAIRING = "repairing"
    FINALIZING = "finalizing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


KNOWN_KINDS = {
    "text", "info", "status", "image", "video", "confirm",
    "error", "intel_analysis", "tool_start", "tool_result",
    "stream_start", "stream_end", "final",
}


@dataclass
class StreamEvent:
    """标准化事件"""
    run_id: str
    kind: str
    payload: dict[str, Any]
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.run_id:
            self.run_id = str(uuid.uuid4())[:12]

    @classmethod
    def from_tuple(cls, raw: tuple, run_id: str = "") -> StreamEvent:
        """从 (kind, payload) 元组创建标准化事件"""
        kind = "info"
        payload: dict[str, Any] = {}

        if isinstance(raw, tuple) and len(raw) >= 2:
            kind = str(raw[0]).lower()
            p = raw[1]
            if isinstance(p, dict):
                payload = p
            elif isinstance(p, str):
                payload = {"message": p}
            else:
                payload = {"data": str(p)}
        elif isinstance(raw, tuple) and len(raw) == 1:
            payload = {"message": str(raw[0])}
        elif isinstance(raw, str):
            payload = {"message": raw}

        # 未知 kind 降级
        if kind not in KNOWN_KINDS:
            kind = "info"

        return cls(run_id=run_id, kind=kind, payload=payload)

    def to_status(self, status: RunStatus, message: str = "") -> StreamEvent:
        """生成带生命周期状态的 status 事件"""
        return StreamEvent(
            run_id=self.run_id,
            kind="status",
            payload={
                "run_id": self.run_id,
                "status": status.value,
                "phase": status.value,
                "message": message or status.value,
            },
        )


def normalize_event(raw: Any, run_id: str = "") -> StreamEvent:
    """统一入口：任何输入 → StreamEvent"""
    if isinstance(raw, StreamEvent):
        return raw
    return StreamEvent.from_tuple(raw, run_id)


class EventQueue:
    """异步事件队列 — 解耦接收和渲染"""

    def __init__(self, max_size: int = 500):
        self._queue: list[StreamEvent] = []
        self._max_size = max_size

    def push(self, event: StreamEvent) -> None:
        if len(self._queue) >= self._max_size:
            self._queue.pop(0)  # 丢弃最老的事件
        self._queue.append(event)

    def pop_all(self) -> list[StreamEvent]:
        events = self._queue[:]
        self._queue.clear()
        return events

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def empty(self) -> bool:
        return len(self._queue) == 0


# ── 后端侧 helper ──

def make_status_event(run_id: str, status: RunStatus, message: str = "",
                      extra: dict[str, Any] | None = None) -> tuple:
    """生成带生命周期的 status yield"""
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": status.value,
        "phase": status.value,
        "message": message or status.value,
    }
    if extra:
        payload.update(extra)
    return ("status", payload)


def make_error_event(run_id: str, error: str, kind: str = "error",
                     extra: dict[str, Any] | None = None) -> tuple:
    """生成标准错误 yield"""
    payload: dict[str, Any] = {
        "run_id": run_id,
        "error": error,
        "kind": kind,
    }
    if extra:
        payload.update(extra)
    return ("error", payload)
