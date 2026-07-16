"""
Architecture Runtime — 架构设计运行时
========================================
专门处理：系统架构、重构方案、技术选型、模块拆分。

特性:
- 输出: architecture_plan / module_diagram / migration_steps / trade_offs
- 步骤: 分析现状 → 设计方案 → 对比权衡 → 迁移路线
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .base_runtime import BaseRuntime, RuntimeContext, RuntimeStatus

logger = logging.getLogger(__name__)


class ArchitectureRuntime(BaseRuntime):
    """架构设计运行时"""

    ARCH_KEYWORDS = [
        r"架构|架构设计|系统设计|模块拆分|微服务|分层架构",
        r"refactor|architecture|decouple|monolith|migration",
        r"拆分|迁移.*方案|重构.*架构|升级.*系统|替换.*模块",
    ]

    def __init__(self):
        super().__init__(name="architecture")

    def can_handle(self, request: str, mode: str) -> bool:
        text = request.lower()
        for pattern in self.ARCH_KEYWORDS:
            if re.search(pattern, text):
                return True
        # 多步骤 + 架构关键词
        return bool(mode == "DEEP" and re.search(r"方案|设计|架构|迁移|拆分", text))

    async def execute(self, ctx: RuntimeContext) -> dict[str, Any]:
        self._status = RuntimeStatus.RUNNING
        logger.info(f"ArchitectureRuntime: 架构设计 '{ctx.request[:60]}...'")

        # 1. 提取关键系统/模块
        systems = self._extract_systems(ctx.request)
        # 2. 确定架构风格
        style = self._determine_style(ctx.request)
        # 3. 生成迁移步骤
        steps = self._generate_migration_steps(ctx.request, systems)

        result = {
            "status": "success",
            "runtime": self.name,
            "systems": systems,
            "architecture_style": style,
            "migration_steps": steps,
            "step_count": len(steps),
        }

        self._status = RuntimeStatus.SUCCESS
        return result

    def _extract_systems(self, request: str) -> list[str]:
        """提取涉及的模块/系统"""
        modules = re.findall(
            r"(认证|用户|订单|支付|库存|商品|消息|通知|日志|配置|权限)\S{0,4}(模块|系统|服务)?", request
        )
        return [m[0] + (m[1] or "") for m in modules[:5]] or ["主系统"]

    def _determine_style(self, request: str) -> str:
        """确定架构风格"""
        text = request.lower()
        if any(kw in text for kw in ["微服务", "拆分", "microservice", "decouple"]):
            return "微服务架构"
        if any(kw in text for kw in ["分层", "layer", "tier"]):
            return "分层架构"
        if any(kw in text for kw in ["事件", "event", "mq", "消息队列"]):
            return "事件驱动架构"
        return "模块化单体架构"

    def _generate_migration_steps(self, request: str, systems: list[str]) -> list[dict[str, str]]:
        """生成迁移步骤"""
        return [
            {"step": "1", "action": "现状分析", "detail": f"梳理 {', '.join(systems)} 现有模块依赖"},
            {
                "step": "2",
                "action": "目标架构设计",
                "detail": f"设计 {systems[0] if systems else '目标'} 的{self._determine_style(request)}方案",
            },
            {"step": "3", "action": "接口契约定义", "detail": "定义模块间 API 协议和数据模型"},
            {"step": "4", "action": "增量迁移", "detail": "按模块逐个迁移，保持向后兼容"},
            {"step": "5", "action": "验证与清理", "detail": "集成测试验证后清理旧代码"},
        ]
