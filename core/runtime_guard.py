"""
Runtime Guard — CRUX 运行时守护
================================
熔断器 + 限流 + 降级 + 健康检查。

功能:
1. CircuitBreaker: 熔断器 — 连续失败 N 次后熔断，冷却后半开
2. RateLimiter: 限流 — 控制工具调用频率
3. HealthCheck: 运行时健康检查 — 检查各组件状态
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"       # 正常
    OPEN = "open"           # 熔断
    HALF_OPEN = "half_open"  # 半开（尝试恢复）


@dataclass
class CircuitBreaker:
    """熔断器"""
    name: str
    failure_threshold: int = 3       # 连续失败 N 次熔断
    recovery_timeout: float = 30.0   # 冷却时间（秒）
    half_open_max_retries: int = 2   # 半开状态下最多尝试次数

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    half_open_attempts: int = 0
    total_failures: int = 0
    total_successes: int = 0

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        """执行受保护调用"""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_attempts = 0
                logger.info(f"CircuitBreaker '{self.name}' 半开，尝试恢复")
            else:
                raise RuntimeError(
                    f"CircuitBreaker '{self.name}' 已熔断 "
                    f"(冷却 {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s)"
                )

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    async def call_async(self, fn: Callable, *args, **kwargs) -> Any:
        """异步调用"""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_attempts = 0
                logger.info(f"CircuitBreaker '{self.name}' 半开，尝试恢复")
            else:
                raise RuntimeError(
                    f"CircuitBreaker '{self.name}' 已熔断 "
                    f"(冷却 {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s)"
                )

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self.total_successes += 1
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_attempts += 1
            if self.half_open_attempts >= self.half_open_max_retries:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info(f"CircuitBreaker '{self.name}' 恢复关闭状态")

    def _on_failure(self) -> None:
        self.total_failures += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"CircuitBreaker '{self.name}' 半开失败，回到熔断")
        else:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"CircuitBreaker '{self.name}' 熔断 (连续 {self.failure_count} 次失败)")

    def reset(self) -> None:
        """手动重置"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_attempts = 0
        logger.info(f"CircuitBreaker '{self.name}' 手动重置")

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "success_rate": self.total_successes / (self.total_successes + self.total_failures) * 100
            if (self.total_successes + self.total_failures) > 0 else 100.0,
        }


@dataclass
class RateLimiter:
    """限流器 — 滑动窗口"""
    name: str
    max_calls: int = 10       # 窗口内最大调用次数
    window_seconds: float = 60.0  # 窗口时间（秒）

    _calls: list[float] = field(default_factory=list)

    def acquire(self) -> bool:
        """尝试获取许可，返回是否允许"""
        now = time.time()
        # 清除过期记录
        self._calls = [t for t in self._calls if now - t < self.window_seconds]

        if len(self._calls) >= self.max_calls:
            wait = self._calls[0] + self.window_seconds - now
            raise RuntimeError(
                f"RateLimiter '{self.name}' 限流 "
                f"({self.max_calls} 次/{self.window_seconds:.0f}s)，请等待 {wait:.0f}s"
            )

        self._calls.append(now)
        return True

    def remaining(self) -> int:
        """剩余可用次数"""
        now = time.time()
        self._calls = [t for t in self._calls if now - t < self.window_seconds]
        return max(0, self.max_calls - len(self._calls))

    def reset(self) -> None:
        self._calls.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "remaining": self.remaining(),
            "max_calls": self.max_calls,
            "window_seconds": self.window_seconds,
        }


@dataclass
class GuardConfig:
    """运行时守护配置"""
    circuit_breaker_enabled: bool = True
    rate_limiter_enabled: bool = True
    health_check_enabled: bool = True
    default_circuit_breaker_threshold: int = 3
    default_circuit_breaker_timeout: float = 30.0
    default_rate_limit: int = 10
    default_rate_window: float = 60.0


class RuntimeGuard:
    """运行时守护 — 管理所有熔断器和限流器"""

    def __init__(self, config: GuardConfig | None = None):
        self.config = config or GuardConfig()
        self._breakers: dict[str, CircuitBreaker] = {}
        self._limiters: dict[str, RateLimiter] = {}

    # ── 熔断器 ──

    def get_breaker(self, name: str) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=self.config.default_circuit_breaker_threshold,
                recovery_timeout=self.config.default_circuit_breaker_timeout,
            )
        return self._breakers[name]

    def call_with_breaker(self, name: str, fn: Callable, *args, **kwargs) -> Any:
        """在熔断器保护下调用"""
        if not self.config.circuit_breaker_enabled:
            return fn(*args, **kwargs)
        return self.get_breaker(name).call(fn, *args, **kwargs)

    async def call_with_breaker_async(self, name: str, fn: Callable, *args, **kwargs) -> Any:
        """异步熔断保护调用"""
        if not self.config.circuit_breaker_enabled:
            return await fn(*args, **kwargs)
        return await self.get_breaker(name).call_async(fn, *args, **kwargs)

    # ── 限流 ──

    def get_limiter(self, name: str, max_calls: int | None = None) -> RateLimiter:
        if name not in self._limiters:
            self._limiters[name] = RateLimiter(
                name=name,
                max_calls=max_calls or self.config.default_rate_limit,
                window_seconds=self.config.default_rate_window,
            )
        return self._limiters[name]

    def check_rate(self, name: str) -> bool:
        if not self.config.rate_limiter_enabled:
            return True
        return self.get_limiter(name).acquire()

    # ── 健康检查 ──

    def health_check(self) -> dict[str, Any]:
        """完整健康检查"""
        if not self.config.health_check_enabled:
            return {"status": "ok", "message": "健康检查已禁用"}

        issues: list[str] = []
        status = "ok"

        for name, breaker in self._breakers.items():
            if breaker.state == CircuitState.OPEN:
                issues.append(f"熔断器 '{name}' 已熔断")
                status = "degraded"

        for name, limiter in self._limiters.items():
            remaining = limiter.remaining()
            if remaining == 0:
                issues.append(f"限流器 '{name}' 已耗尽")
                status = "degraded"

        info = {
            "status": status,
            "timestamp": time.time(),
            "circuit_breakers": {n: b.stats() for n, b in self._breakers.items()},
            "rate_limiters": {n: l.stats() for n, l in self._limiters.items()},
            "issues": issues[:5],
        }
        info["degraded"] = status == "degraded"
        return info

    def all_stats(self) -> dict[str, Any]:
        return {
            "breakers": {n: b.stats() for n, b in self._breakers.items()},
            "limiters": {n: l.stats() for n, l in self._limiters.items()},
        }


# ── 全局单例 ──
_guard: RuntimeGuard | None = None


def get_guard() -> RuntimeGuard:
    global _guard
    if _guard is None:
        _guard = RuntimeGuard()
    return _guard
