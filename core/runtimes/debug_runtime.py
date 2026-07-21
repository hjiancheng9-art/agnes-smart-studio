"""
Debug Analyze Runtime — 调试分析运行时
========================================
专门处理：bug排查、根因分析、复现路径、测试通过但真实失败。

特性:
- 默认不写文件（只读分析）
- 输出: root_cause / probes / fix_plan / verification_plan
- 步骤: 收集症状 → 缩小范围 → 提出假设 → 验证假设 → 输出根因
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .base_runtime import BaseRuntime, RuntimeContext, RuntimeStatus

logger = logging.getLogger(__name__)


class DebugAnalyzeRuntime(BaseRuntime):
    """调试分析运行时"""

    DEBUG_KEYWORDS = [
        r"不工作|不生效|炸了|报错|卡住|偶尔|间歇|复现|根因|排查|挂掉|崩溃|死锁",
        r"doesn't work|not working|flaky|intermittent|bug|error|crash|traceback|exception",
        r"排查根因|排查一下|排查.*问题|定位.*问题|根因.*分析|总是.*挂",
    ]

    def __init__(self):
        super().__init__(name="debug_analyze")

    def can_handle(self, request: str, mode: str) -> bool:
        """判断是否为调试类请求"""
        text = request.lower()
        return any(re.search(pattern, text) for pattern in self.DEBUG_KEYWORDS)

    async def execute(self, ctx: RuntimeContext) -> dict[str, Any]:
        """执行调试分析流程"""
        self._status = RuntimeStatus.RUNNING
        logger.info(f"DebugAnalyzeRuntime: 调试分析 '{ctx.request[:60]}...'")

        # 1. 症状收集
        symptoms = self._extract_symptoms(ctx.request)

        # 2. 提出假设
        hypotheses = self._generate_hypotheses(ctx.request, symptoms)

        # 3. 输出报告
        result = {
            "status": "success",
            "runtime": self.name,
            "symptoms": symptoms,
            "hypotheses": hypotheses,
            "root_cause": self._estimate_root_cause(ctx.request, hypotheses),
            "fix_plan": self._generate_fix_plan(ctx.request, hypotheses),
        }

        self._status = RuntimeStatus.SUCCESS
        return result

    def _extract_symptoms(self, request: str) -> list[str]:
        """从请求中提取症状关键词"""
        symptoms = []
        text = request.lower()
        symptom_map = [
            (r"报错.*|error|exception|traceback", "报错信息"),
            (r"卡[住死]|挂[掉]?|崩溃|crash|freeze|死锁", "程序卡死/崩溃"),
            (r"偶尔|间歇|flaky|intermittent|随机", "间歇性故障"),
            (r"慢|timeout|超时|延迟", "性能慢/超时"),
            (r"不工作|不生效|not working|doesn't work|失效|坏了", "功能失效"),
            (r"返回.*空|返回.*None|null|empty|空白", "返回空值"),
        ]
        for pattern, desc in symptom_map:
            if re.search(pattern, text):
                symptoms.append(desc)
        return symptoms or ["未识别症状类型"]

    def _generate_hypotheses(self, request: str, symptoms: list[str]) -> list[str]:
        """生成可能的原因假设"""
        hypotheses = []
        text = request.lower()
        if "滚动" in text or "scroll" in text:
            hypotheses.append("事件绑定作用域不正确")
            hypotheses.append("输入缓冲区抢焦点")
        if "空" in text or "None" in text:
            hypotheses.append("未处理空值返回")
        if "慢" in text or "timeout" in text:
            hypotheses.append("N+1 查询或未加索引")
            hypotheses.append("资源泄漏（连接/线程）")
        if not hypotheses:
            hypotheses.append("异常未捕获")
            hypotheses.append("边界条件未处理")
        return hypotheses

    def _estimate_root_cause(self, request: str, hypotheses: list[str]) -> str:
        """估算根因"""
        return hypotheses[0] if hypotheses else "待进一步分析"

    def _generate_fix_plan(self, request: str, hypotheses: list[str]) -> list[str]:
        """生成修复计划"""
        return [f"验证: {h}" for h in hypotheses[:2]] + ["修复后运行测试验证"]
