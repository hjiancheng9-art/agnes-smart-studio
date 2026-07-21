"""
Research Runtime — 研究调查运行时
====================================
专门处理：技术调研、方案对比、趋势分析、最佳实践研究。

特性:
- 依赖联网搜索（web_search / CDP 浏览器）
- 输出: research_summary / comparisons / recommendations
- 步骤: 收集资料 → 交叉验证 → 结构化输出
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .base_runtime import BaseRuntime, RuntimeContext, RuntimeStatus

logger = logging.getLogger(__name__)


class ResearchRuntime(BaseRuntime):
    """研究调查运行时"""

    RESEARCH_KEYWORDS = [
        r"研究|调研|调查|分析.*对比|对比.*分析|趋势|最新的|当前.*技术",
        r"research|survey|compare.*analysis|investigate|how to|best practice",
        r"选型|方案对比|技术选型|替代方案|vs\s|alternative",
    ]

    def __init__(self):
        super().__init__(name="research")

    def can_handle(self, request: str, mode: str) -> bool:
        text = request.lower()
        for pattern in self.RESEARCH_KEYWORDS:
            if re.search(pattern, text):
                return True
        return mode == "RESEARCH"

    async def execute(self, ctx: RuntimeContext) -> dict[str, Any]:
        self._status = RuntimeStatus.RUNNING
        logger.info(f"ResearchRuntime: 调查研究 '{ctx.request[:60]}...'")

        topics = self._extract_topics(ctx.request)
        comparisons = self._generate_comparisons(ctx.request, topics)

        result = {
            "status": "success",
            "runtime": self.name,
            "topics": topics,
            "comparisons": comparisons,
            "sources_needed": True,
            "needs_web_search": True,
        }

        self._status = RuntimeStatus.SUCCESS
        return result

    def _extract_topics(self, request: str) -> list[str]:
        topics = []
        # 提取 vs 前后的技术名
        vs_match = re.findall(
            r"(\w+(?:DB|SQL|NoSQL|MQ|API)?)\s*(?:vs|对比|与.*?对比|和.*?对比|还是)\s*(\w+(?:DB|SQL|NoSQL|MQ|API)?)",
            request,
        )
        for a, b in vs_match:
            topics.extend([a, b])
        # 提取技术关键词
        techs = re.findall(
            r"(RAG|LLM|GPT|向量|embedding|微服务|Docker|K8S|Kubernetes|AWS|GCP|Azure|React|Vue|Angular|PostgreSQL|MySQL|MongoDB|Redis|Kafka|RabbitMQ|gRPC|REST|GraphQL)",
            request,
        )
        topics.extend(techs)
        return list(set(topics))[:5] or ["待识别技术领域"]

    def _generate_comparisons(self, request: str, topics: list[str]) -> list[dict[str, str]]:
        """生成对比维度"""
        if len(topics) >= 2:
            return [
                {"dimension": "性能", "items": dict.fromkeys(topics[:2], "待查")},
                {"dimension": "可扩展性", "items": dict.fromkeys(topics[:2], "待查")},
                {"dimension": "社区活跃度", "items": dict.fromkeys(topics[:2], "待查")},
                {"dimension": "学习曲线", "items": dict.fromkeys(topics[:2], "待查")},
            ]
        return [{"dimension": "概述", "items": {topics[0]: "待查"}}]
