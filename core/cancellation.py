"""
Cancellation — CRUX 任务取消机制
=================================
支持长时间运行任务的优雅取消、超时自动取消、取消传播。

功能:
1. CancellationToken: 取消令牌 — 任务定期检查是否被取消
2. CancellableTask: 可取消任务包装器
3. TaskRegistry: 任务注册表 — 跟踪所有运行中任务
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class CancelledError(RuntimeError):
    """任务被取消异常"""
    def __init__(self, task_id: str, reason: str = ""):
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"Task {task_id} cancelled: {reason}")


@dataclass
class CancellationToken:
    """取消令牌 — 任务定期检查"""
    cancelled: bool = False
    reason: str = ""

    def cancel(self, reason: str = "用户取消") -> None:
        self.cancelled = True
        self.reason = reason

    def check(self) -> None:
        """检查取消状态，已取消则抛异常"""
        if self.cancelled:
            raise CancelledError("unknown", self.reason)

    def is_cancelled(self) -> bool:
        return self.cancelled

    def reset(self) -> None:
        self.cancelled = False
        self.reason = ""


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: float = 0.0
    ended_at: float = 0.0
    progress: str = ""
    result: Any = None
    error: str = ""
    token: CancellationToken | None = None

    @property
    def duration(self) -> float:
        if self.ended_at and self.started_at:
            return self.ended_at - self.started_at
        if self.started_at:
            return time.time() - self.started_at
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "status": self.status.value,
            "duration": round(self.duration, 2),
            "progress": self.progress[:100],
            "error": self.error[:200],
        }


class TaskRegistry:
    """任务注册表 — 管理所有运行中任务"""

    def __init__(self):
        self._tasks: dict[str, TaskInfo] = {}

    def register(self, name: str) -> tuple[str, CancellationToken]:
        """注册新任务，返回 (task_id, token)"""
        task_id = str(uuid.uuid4())[:12]
        token = CancellationToken()
        self._tasks[task_id] = TaskInfo(
            task_id=task_id,
            name=name,
            status=TaskStatus.RUNNING,
            started_at=time.time(),
            token=token,
        )
        return task_id, token

    def complete(self, task_id: str, result: Any = None) -> None:
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.COMPLETED
            t.ended_at = time.time()
            t.result = result

    def fail(self, task_id: str, error: str) -> None:
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.FAILED
            t.ended_at = time.time()
            t.error = error

    def cancel(self, task_id: str, reason: str = "用户取消") -> bool:
        """取消任务"""
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.CANCELLED
            t.ended_at = time.time()
            if t.token:
                t.token.cancel(reason)
            return True
        return False

    def get(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def list_active(self) -> list[TaskInfo]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def list_all(self) -> list[TaskInfo]:
        return list(self._tasks.values())

    def cleanup(self, max_age: float = 3600) -> int:
        """清理过期任务"""
        now = time.time()
        to_remove = [
            tid for tid, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            and now - t.ended_at > max_age
        ]
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self._tasks.values():
            key = t.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts


# ── 任务执行器 ──

def run_cancellable(name: str, fn: Callable, *args, **kwargs) -> Any:
    """在取消令牌下运行同步函数"""
    registry = get_registry()
    task_id, token = registry.register(name)
    try:
        # 注入 token
        result = fn(*args, token=token, **kwargs)
        registry.complete(task_id, result)
        return result
    except CancelledError:
        registry.cancel(task_id)
        raise
    except Exception as e:
        registry.fail(task_id, str(e))
        raise


async def run_cancellable_async(name: str, fn: Callable, *args, **kwargs) -> Any:
    """在取消令牌下运行异步函数"""
    registry = get_registry()
    task_id, token = registry.register(name)
    try:
        result = await fn(*args, token=token, **kwargs)
        registry.complete(task_id, result)
        return result
    except CancelledError:
        registry.cancel(task_id)
        raise
    except Exception as e:
        registry.fail(task_id, str(e))
        raise


# ── 全局单例 ──
_registry: TaskRegistry | None = None


def get_registry() -> TaskRegistry:
    global _registry
    if _registry is None:
        _registry = TaskRegistry()
    return _registry
