"""
Capability Runtime Router — 按请求类型分派到专业 Runtime
===========================================================
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .base_runtime import BaseRuntime, CapabilityRuntimeType, RuntimeContext

logger = logging.getLogger(__name__)


class CapabilityRuntimeRouter:
    """能力运行时路由器 — 分析请求并分派到最合适的 Runtime"""

    def __init__(self):
        self._runtimes: dict[CapabilityRuntimeType, BaseRuntime] = {}

    def register(self, runtime: BaseRuntime) -> None:
        """注册运行时"""
        for rt_type in CapabilityRuntimeType:
            if rt_type.value == runtime.name:
                self._runtimes[rt_type] = runtime
                logger.info(f"Runtime 注册: {runtime.name}")
                return
        # 按 can_handle 注册
        self._runtimes[CapabilityRuntimeType.GENERAL] = runtime

    def get_runtime(self, rt_type: CapabilityRuntimeType) -> BaseRuntime | None:
        return self._runtimes.get(rt_type)

    def select_runtime(self, request: str, mode: str) -> tuple[CapabilityRuntimeType, BaseRuntime | None]:
        """根据请求内容选择最合适的 Runtime"""
        text = request.lower()

        # 1. 先查注册表中特定 Runtime 的 can_handle
        for rt_type, runtime in self._runtimes.items():
            if rt_type != CapabilityRuntimeType.GENERAL and runtime.can_handle(request, mode):
                return rt_type, runtime

        # 2. 按模式映射
        rt_type = CapabilityRuntimeType.from_mode(mode)

        # 3. DEEP 模式下根据关键词细粒度分配
        if mode == "DEEP":
            if re.search(r"排查|根因|复现|挂|崩|偶尔|间歇|报错|traceback|exception|doesn't work", text):
                rt_type = CapabilityRuntimeType.DEBUG_ANALYZE
            elif re.search(r"修复|修改|补丁|patch|fix|bug", text):
                rt_type = CapabilityRuntimeType.CODE_PATCH
            elif re.search(r"架构|设计模式|分层|微服务|拆|迁移|refactor|architecture|decouple", text):
                rt_type = CapabilityRuntimeType.ARCHITECTURE

        # 4. 安全模式直接映射
        if mode == "SAFE":
            rt_type = CapabilityRuntimeType.SECURITY

        runtime = self._runtimes.get(rt_type) or self._runtimes.get(CapabilityRuntimeType.GENERAL)
        return rt_type, runtime

    async def route(self, ctx: RuntimeContext) -> dict[str, Any]:
        """路由并执行"""
        rt_type, runtime = self.select_runtime(ctx.request, ctx.mode)
        if runtime is None:
            return {"status": "failed", "error": f"未找到 {rt_type.value} 对应的 Runtime"}

        ctx.runtime_type = rt_type
        logger.info(f"Runtime 路由: {rt_type.value} → {runtime.name}")

        try:
            result = await runtime.execute(ctx)
            return result
        except Exception as e:
            logger.exception(f"Runtime {runtime.name} 执行失败")
            return {"status": "failed", "error": str(e), "runtime": runtime.name}

    def list_runtimes(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._runtimes.values()]
