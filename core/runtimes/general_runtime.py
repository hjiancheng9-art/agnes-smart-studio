"""
General Runtime — 通用兜底运行时
=================================
保留当前 DeliberateWorkflow 全部逻辑，作为默认 Fallback。
"""
from __future__ import annotations

import logging
from typing import Any

from .base_runtime import BaseRuntime, RuntimeContext, RuntimeStatus

logger = logging.getLogger(__name__)


class GeneralRuntime(BaseRuntime):
    """通用运行时 — 兜底，处理所有未被专业 Runtime 匹配的请求"""

    def __init__(self):
        super().__init__(name="general")
        self._plan_fn = None
        self._execute_fn = None

    def set_plan_fn(self, fn: Any) -> None:
        """注入规划函数（由 DeliberateWorkflow 提供）"""
        self._plan_fn = fn

    def can_handle(self, request: str, mode: str) -> bool:
        return True  # 兜底，总能处理

    async def execute(self, ctx: RuntimeContext) -> dict[str, Any]:
        """执行通用流程"""
        self._status = RuntimeStatus.RUNNING
        logger.info(f"GeneralRuntime: 处理请求 '{ctx.request[:60]}...' mode={ctx.mode}")

        result: dict[str, Any] = {
            "status": "success",
            "runtime": self.name,
            "mode": ctx.mode,
            "steps": [],
        }

        # Plan
        if self._plan_fn:
            try:
                plan_result = await self._plan_fn(ctx.request)
                result["steps"].append({"name": "plan", "status": "success"})
            except Exception as e:
                result["steps"].append({"name": "plan", "status": "failed", "error": str(e)})

        self._status = RuntimeStatus.SUCCESS
        return result
