"""
Advisor 熔断器
==============
连续失败 N 次后熔断，冷却期间所有请求直接返回 unavailable。
成功后自动复位。
"""

from __future__ import annotations

import time


class CircuitBreaker:
    """简单的熔断器：失败阈值 + 冷却时间。

    状态机: CLOSED → (连续失败) → OPEN → (冷却超时) → HALF_OPEN → (成功) → CLOSED
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: int = 120,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failure_count = 0
        self._opened_until: float = 0.0

    # ── 查询 ──────────────────────────────────────

    def allow(self) -> bool:
        """当前是否允许请求通过。"""
        return time.time() >= self._opened_until

    @property
    def is_open(self) -> bool:
        """熔断器是否开启（拒绝请求）。"""
        return not self.allow()

    @property
    def failure_count(self) -> int:
        return self._failure_count

    # ── 状态变更 ──────────────────────────────────

    def record_success(self) -> None:
        """记录一次成功 — 复位计数器。"""
        self._failure_count = 0
        self._opened_until = 0.0

    def record_failure(self) -> None:
        """记录一次失败 — 可能触发熔断。"""
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._opened_until = time.time() + self.cooldown_seconds

    # ── 诊断 ──────────────────────────────────────

    def snapshot(self) -> dict:
        """返回当前状态快照。"""
        return {
            "allow": self.allow(),
            "is_open": self.is_open,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "opened_until": self._opened_until,
            "remaining_cooldown": max(0.0, self._opened_until - time.time()),
        }

    def reset(self) -> None:
        """强制复位（用于测试或手动恢复）。"""
        self._failure_count = 0
        self._opened_until = 0.0
