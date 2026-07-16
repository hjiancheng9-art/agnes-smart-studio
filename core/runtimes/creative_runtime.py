"""
Creative Runtime — 创意生成运行时
====================================
专门处理：UI 设计、文案创作、品牌设计、创意构思。

特性:
- 输出: creative_concepts / design_suggestions / variants
- 风格多样，多方案生成后评审选优
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .base_runtime import BaseRuntime, RuntimeContext, RuntimeStatus

logger = logging.getLogger(__name__)


class CreativeRuntime(BaseRuntime):
    """创意生成运行时"""

    CREATIVE_KEYWORDS = [
        r"创意|设计|风格|美观|配色|布局|UI|UX|文案|品牌|marketing|brand",
        r"好看|漂亮|科技感|简约|大气|现代感|酷炫|高级感",
        r"logo|banner|海报|落地页|首页|产品页|icon|图标|字体",
    ]

    def __init__(self):
        super().__init__(name="creative")

    def can_handle(self, request: str, mode: str) -> bool:
        text = request.lower()
        # 排除技术方案类
        if re.search(r"方案|架构|数据库|系统|模块|接口|协议|服务", text):
            return False
        for pattern in self.CREATIVE_KEYWORDS:
            if re.search(pattern, text):
                return True
        return mode == "CREATIVE"

    async def execute(self, ctx: RuntimeContext) -> dict[str, Any]:
        self._status = RuntimeStatus.RUNNING
        logger.info(f"CreativeRuntime: 创意生成 '{ctx.request[:60]}...'")

        concepts = self._generate_concepts(ctx.request)
        style = self._extract_style(ctx.request)

        result = {
            "status": "success",
            "runtime": self.name,
            "concepts": concepts,
            "style_direction": style,
            "variant_count": len(concepts),
        }

        self._status = RuntimeStatus.SUCCESS
        return result

    def _extract_style(self, request: str) -> dict[str, str]:
        text = request.lower()
        style = {}
        tones = []
        if "科技感" in text or "modern" in text:
            tones.append("科技感")
        if "简约" in text or "minimal" in text:
            tones.append("简约")
        if "大气" in text or "premium" in text:
            tones.append("大气")
        if "复古" in text or "vintage" in text:
            tones.append("复古")
        if "可爱" in text or "cute" in text:
            tones.append("可爱")
        style["tone"] = " + ".join(tones) if tones else "现代"
        if "配色" in text or "color" in text:
            style["color"] = "需进一步确定配色方案"
        if "字体" in text or "font" in text:
            style["font"] = "需进一步确定字体"
        return style

    def _generate_concepts(self, request: str) -> list[dict[str, str]]:
        """生成创意概念"""
        text = request.lower()
        concepts = []

        if "logo" in text or "品牌" in text:
            concepts.append({"variant": "A", "concept": "几何字母组合", "description": "将品牌首字母与几何图形结合"})
            concepts.append({"variant": "B", "concept": "渐变线条", "description": "使用渐变线条构成品牌符号"})
            concepts.append({"variant": "C", "concept": "极简图标", "description": "单色极简图形标识"})
        elif "首页" in text or "产品页" in text or "落地页" in text:
            concepts.append({"variant": "A", "concept": "大图模态布局", "description": "全屏视觉焦点+清晰 CTA"})
            concepts.append({"variant": "B", "concept": "卡片式信息流", "description": "结构化卡片展示核心卖点"})
        elif "文案" in text or "marketing" in text:
            concepts.append({"variant": "A", "concept": "痛点驱动型", "description": "先引发共鸣再给出解决方案"})
            concepts.append({"variant": "B", "concept": "数据说服型", "description": "用具体数据支撑价值主张"})
        else:
            concepts.append({"variant": "A", "concept": "方案一", "description": "初步创意方案"})
            concepts.append({"variant": "B", "concept": "方案二", "description": "备选创意方案"})

        return concepts
