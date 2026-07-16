"""
Resource Budget — CRUX 资源预算管理
====================================
控制工具调用次数、token 消耗、执行时间，防止失控。

功能:
1. ToolBudget: 工具调用预算（每轮最大调用次数）
2. TokenBudget: token 消耗预算
3. TimeBudget: 执行时间预算
4. BudgetManager: 统一预算管理器
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BudgetLimit:
    """预算限制"""

    max_tool_calls: int = 30  # 最大工具调用次数
    max_token_cost: int = 50000  # 最大 token 消耗
    max_duration_seconds: float = 300.0  # 最大执行时间（秒）
    max_agent_calls: int = 10  # 最大子 agent 调用
    max_repair_rounds: int = 5  # 最大修复轮数

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tool_calls": self.max_tool_calls,
            "max_token_cost": self.max_token_cost,
            "max_duration_seconds": self.max_duration_seconds,
            "max_agent_calls": self.max_agent_calls,
            "max_repair_rounds": self.max_repair_rounds,
        }


@dataclass
class BudgetUsage:
    """预算使用情况"""

    tool_calls: int = 0
    token_cost: int = 0
    duration_seconds: float = 0.0
    agent_calls: int = 0
    repair_rounds: int = 0
    started_at: float = 0.0

    def __post_init__(self):
        if not self.started_at:
            self.started_at = time.time()

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_calls": self.tool_calls,
            "token_cost": self.token_cost,
            "duration_seconds": round(self.duration_seconds or self.elapsed, 1),
            "agent_calls": self.agent_calls,
            "repair_rounds": self.repair_rounds,
        }


class BudgetExceededError(RuntimeError):
    """预算超限异常"""

    def __init__(self, category: str, limit: Any, actual: Any):
        self.category = category
        self.limit = limit
        self.actual = actual
        super().__init__(f"Budget {category} exceeded: {actual} > {limit}")


class BudgetManager:
    """预算管理器 — 追踪和限制资源消耗"""

    def __init__(self, limit: BudgetLimit | None = None):
        self.limit = limit or BudgetLimit()
        self.usage = BudgetUsage()
        self._paused: bool = False

    # ── 工具调用次数 ──

    def record_tool_call(self, count: int = 1) -> None:
        """记录工具调用"""
        if self._paused:
            return
        self.usage.tool_calls += count
        if self.usage.tool_calls > self.limit.max_tool_calls:
            raise BudgetExceededError("tool_calls", self.limit.max_tool_calls, self.usage.tool_calls)

    def can_call_tool(self) -> bool:
        return self.usage.tool_calls < self.limit.max_tool_calls

    @property
    def remaining_tool_calls(self) -> int:
        return max(0, self.limit.max_tool_calls - self.usage.tool_calls)

    # ── Token 消耗 ──

    def record_token_cost(self, tokens: int) -> None:
        """记录 token 消耗"""
        if self._paused:
            return
        self.usage.token_cost += tokens
        if self.usage.token_cost > self.limit.max_token_cost:
            raise BudgetExceededError("token_cost", self.limit.max_token_cost, self.usage.token_cost)

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.limit.max_token_cost - self.usage.token_cost)

    # ── 时间预算 ──

    def check_time(self) -> None:
        """检查是否超时"""
        if self._paused:
            return
        elapsed = self.usage.elapsed
        self.usage.duration_seconds = elapsed
        if elapsed > self.limit.max_duration_seconds:
            raise BudgetExceededError("duration", self.limit.max_duration_seconds, elapsed)

    @property
    def remaining_time(self) -> float:
        return max(0, self.limit.max_duration_seconds - self.usage.elapsed)

    # ── Agent 调用 ──

    def record_agent_call(self) -> None:
        if self._paused:
            return
        self.usage.agent_calls += 1
        if self.usage.agent_calls > self.limit.max_agent_calls:
            raise BudgetExceededError("agent_calls", self.limit.max_agent_calls, self.usage.agent_calls)

    # ── 修复轮次 ──

    def record_repair_round(self) -> None:
        if self._paused:
            return
        self.usage.repair_rounds += 1
        if self.usage.repair_rounds > self.limit.max_repair_rounds:
            raise BudgetExceededError("repair_rounds", self.limit.max_repair_rounds, self.usage.repair_rounds)

    # ── 控制 ──

    def pause(self) -> None:
        """暂停预算追踪"""
        self._paused = True

    def resume(self) -> None:
        """恢复预算追踪"""
        self._paused = False

    def reset(self) -> None:
        """重置"""
        self.usage = BudgetUsage()

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit.to_dict(),
            "usage": self.usage.to_dict(),
            "remaining_tool_calls": self.remaining_tool_calls,
            "remaining_tokens": self.remaining_tokens,
            "remaining_time_seconds": round(self.remaining_time, 1),
            "paused": self._paused,
        }


# ── 快捷函数 ──


def make_budget(limit: BudgetLimit | None = None) -> BudgetManager:
    """创建预算管理器"""
    return BudgetManager(limit=limit)


def quick_budget(max_tool_calls: int = 30, max_duration: float = 300.0) -> BudgetManager:
    """快速创建预算管理器"""
    return BudgetManager(
        BudgetLimit(
            max_tool_calls=max_tool_calls,
            max_duration_seconds=max_duration,
        )
    )
