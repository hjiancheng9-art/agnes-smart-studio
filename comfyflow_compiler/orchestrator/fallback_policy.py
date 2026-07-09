"""Fallback Policy — MCP 失败分级 + 降级决策树"""

from __future__ import annotations
from enum import IntEnum
from typing import Optional


class FailureGrade(IntEnum):
    """MCP 失败严重程度分级"""
    NONE = 0                    # 无失败
    TIMEOUT = 1                 # 超时 — 可降级
    UNAVAILABLE = 2             # 不可用（断连/500）— 可降级
    INVALID_WORKFLOW = 3        # 返回非法 workflow — 可降级
    BLUEPRINT_MISSING = 4       # 缺少蓝图 — 不降级
    UNKNOWN = 5                 # 未知错误 — 可降级


# 是否需要降级的映射
GRADE_SHOULD_FALLBACK = {
    FailureGrade.TIMEOUT: True,
    FailureGrade.UNAVAILABLE: True,
    FailureGrade.INVALID_WORKFLOW: True,
    FailureGrade.BLUEPRINT_MISSING: False,
    FailureGrade.UNKNOWN: True,
    FailureGrade.NONE: False,
}


class FallbackPolicy:
    """降级策略 — 决定是否降级、如何降级"""

    def should_fallback(self, grade: FailureGrade) -> bool:
        """根据失败等级决定是否降级"""
        return GRADE_SHOULD_FALLBACK.get(grade, False)

    def select_fallback_mode(self, original_task_type: str,
                             available_blueprints: list[str]) -> str:
        """选择降级后的任务类型

        Args:
            original_task_type: 原始任务类型
            available_blueprints: 可用的本地蓝图类型列表

        Returns:
            降级后的任务类型
        """
        # 同类型降级
        if original_task_type in available_blueprints:
            return original_task_type

        # 跨类型降级（保守方案）
        fallback_map = {
            "t2v": "i2v",
            "i2v": "img2img",
            "txt2img": "img2img",
            "img2img": "txt2img",
        }
        return fallback_map.get(original_task_type, original_task_type)

    def classify_error(self, error: Exception | str) -> FailureGrade:
        """将异常/错误信息分类为失败等级"""
        error_str = str(error).lower() if not isinstance(error, str) else error.lower()

        if "timeout" in error_str:
            return FailureGrade.TIMEOUT
        if "unavailable" in error_str or "connect" in error_str or "refused" in error_str:
            return FailureGrade.UNAVAILABLE
        if "invalid" in error_str or "missing class_type" in error_str:
            return FailureGrade.INVALID_WORKFLOW
        if "missing_blueprint" in error_str or "蓝图" in error_str:
            return FailureGrade.BLUEPRINT_MISSING
        return FailureGrade.UNKNOWN

    def format_fallback_reason(self, grade: FailureGrade,
                                detail: str = "") -> str:
        """格式化降级原因"""
        labels = {
            FailureGrade.TIMEOUT: "MCP 超时",
            FailureGrade.UNAVAILABLE: "MCP 不可用",
            FailureGrade.INVALID_WORKFLOW: "MCP 返回非法工作流",
            FailureGrade.UNKNOWN: "MCP 未知错误",
        }
        label = labels.get(grade, "MCP 异常")
        if detail:
            return f"{label}: {detail}"
        return label
