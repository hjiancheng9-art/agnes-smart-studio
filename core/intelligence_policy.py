"""
Intelligence Policy Router — CRUX 智能策略路由层 (V2)
=====================================================
V2 核心升级: 从关键词 if/elif 升级为信号评分路由。

路由策略 (3层):
1. **硬规则层**: 安全/破坏性操作强制 SAFE
2. **信号评分层**: 18个信号加权投票给 6 个模式
3. **置信度门禁**: 低于阈值回退到 BALANCED

ModeConfig 保持不变，下游代码不受影响。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .routing_signals import (
    compute_mode_scores,
    get_route_decision,
)


class IntelligenceMode(str, Enum):
    """智能执行模式"""
    FAST = "FAST"
    BALANCED = "BALANCED"
    DEEP = "DEEP"
    SAFE = "SAFE"
    RESEARCH = "RESEARCH"
    CREATIVE = "CREATIVE"


@dataclass
class RiskProfile:
    """请求的风险评估结果 (保持向后兼容)"""
    complexity: int = 0
    security_risk: int = 0
    destructive_risk: int = 0
    creative_load: int = 0
    has_code: bool = False
    has_shell: bool = False
    has_file_ops: bool = False
    has_multi_step: bool = False
    needs_research: bool = False
    is_ambiguous: bool = False
    confidence: float = 0.0

    def score(self) -> int:
        return (
            self.complexity * 3 + self.security_risk * 4
            + self.destructive_risk * 5 + self.creative_load * 2
            + int(self.has_multi_step) * 3 + int(self.needs_research) * 4
            + int(self.is_ambiguous) * 2
        )


@dataclass
class ModeConfig:
    """模式配置 (保持向后兼容)"""
    planner: bool = False
    critic: bool = False
    multi_agent: bool = False
    web_search: str = "never"
    allow_write: bool = True
    allow_shell: bool = False
    tests_required: bool = False
    approval_required: bool = False
    max_rounds: int = 1
    max_agents: int = 1
    min_confidence: float = 0.0
    review_type: str = ""
    goal_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "planner": self.planner,
            "critic": self.critic,
            "multi_agent": self.multi_agent,
            "web_search": self.web_search,
            "allow_write": self.allow_write,
            "allow_shell": self.allow_shell,
            "tests_required": self.tests_required,
            "approval_required": self.approval_required,
            "max_rounds": self.max_rounds,
            "max_agents": self.max_agents,
            "review_type": self.review_type,
            "goal_mode": self.goal_mode,
        }


# ── 模式配置表 ──
MODE_CONFIGS: dict[IntelligenceMode, ModeConfig] = {
    IntelligenceMode.FAST: ModeConfig(
        planner=False, critic=False, multi_agent=False,
        web_search="never", allow_write=False, allow_shell=False,
        tests_required=False, approval_required=False,
        max_rounds=1, max_agents=0, min_confidence=0.0,
    ),
    IntelligenceMode.BALANCED: ModeConfig(
        planner=True, critic=False, multi_agent=False,
        web_search="auto", allow_write=True, allow_shell=False,
        tests_required=False, approval_required=False,
        max_rounds=1, max_agents=1, min_confidence=0.3,
    ),
    IntelligenceMode.DEEP: ModeConfig(
        planner=True, critic=True, multi_agent=True,
        web_search="auto", allow_write=True, allow_shell=False,
        tests_required=True, approval_required=False,
        max_rounds=4, max_agents=4, min_confidence=0.7,
        review_type="code", goal_mode=True,
    ),
    IntelligenceMode.SAFE: ModeConfig(
        planner=True, critic=True, multi_agent=True,
        web_search="auto", allow_write=True, allow_shell=False,
        tests_required=True, approval_required=True,
        max_rounds=5, max_agents=6, min_confidence=0.8,
        review_type="security", goal_mode=True,
    ),
    IntelligenceMode.RESEARCH: ModeConfig(
        planner=True, critic=True, multi_agent=True,
        web_search="always", allow_write=False, allow_shell=False,
        tests_required=False, approval_required=False,
        max_rounds=5, max_agents=4, min_confidence=0.6,
        review_type="", goal_mode=True,
    ),
    IntelligenceMode.CREATIVE: ModeConfig(
        planner=True, critic=True, multi_agent=True,
        web_search="never", allow_write=True, allow_shell=False,
        tests_required=False, approval_required=False,
        max_rounds=3, max_agents=3, min_confidence=0.4,
        review_type="", goal_mode=False,
    ),
}


class IntelligencePolicyRouter:
    """智能策略路由器 V2 — 信号评分 + 硬规则 + 置信度门禁

    三层路由:
    1. 硬规则: 安全/破坏性操作 → SAFE
    2. 信号评分: 18个信号加权投票 → 最优模式
    3. 置信度门禁: 分数过低 → fallback BALANCED/FAST
    """

    # ── 硬规则: 强制 SAFE 的关键词 ──
    HARD_SAFE_PATTERNS: list[str] = [
        r"删除.*密码|删除.*token|删除.*secret|重置.*密码.*所有",
        r"批量重置|批量删除.*用户|清空.*数据库|drop\s+table|drop\s+database",
        r"rm\s+-rf|format.*disk|dd\s+if=|覆盖.*系统文件",
    ]

    def __init__(self, toolbus: Any = None):
        self.toolbus = toolbus
        self._stats: dict[str, int] = {mode.value: 0 for mode in IntelligenceMode}
        if toolbus:
            self._stats["total"] = 0

    # ── V2 核心: 信号评分路由 ──

    def analyze(self, request: str, context: dict[str, Any] | None = None) -> RiskProfile:
        """分析请求 (信号增强版)"""
        profile = RiskProfile()
        text = request.lower()

        # 硬规则检测
        for pat in self.HARD_SAFE_PATTERNS:
            if re.search(pat, text):
                profile.security_risk = max(profile.security_risk, 4)
                profile.destructive_risk = max(profile.destructive_risk, 4)

        # 信号评分 → 映射到 RiskProfile (向后兼容)
        scores = compute_mode_scores(request, context or {})
        profile.confidence = min(1.0, max(0.0, (max(scores.values()) if scores else 0) / 10))

        # 从信号反推 profile 字段
        from .routing_signals import (
            signal_has_code,
            signal_has_destructive_ops,
            signal_has_file_ops,
            signal_has_multi_step,
            signal_has_security_risk,
            signal_has_shell_ops,
            signal_is_ambiguous,
            signal_is_creative,
            signal_is_research,
        )

        ctx = context or {}
        profile.has_code = signal_has_code(text, ctx) > 0.3
        profile.has_multi_step = signal_has_multi_step(text, ctx) > 0.3
        profile.security_risk = min(5, int(signal_has_security_risk(text, ctx) * 5))
        profile.destructive_risk = min(5, int(signal_has_destructive_ops(text, ctx) * 5))
        profile.needs_research = signal_is_research(text, ctx) > 0.3
        profile.creative_load = min(5, int(signal_is_creative(text, ctx) * 5))
        profile.has_file_ops = signal_has_file_ops(text, ctx) > 0.3
        profile.is_ambiguous = signal_is_ambiguous(text, ctx) > 0.3
        profile.has_shell = signal_has_shell_ops(text, ctx) > 0.3
        profile.complexity = min(5, int(
            signal_has_code(text, ctx) * 2
            + signal_has_multi_step(text, ctx) * 2
            + (1 if profile.needs_research else 0)
        ))

        # 上下文增强
        if context:
            if context.get("previous_failures", 0) > 0:
                profile.complexity = min(5, profile.complexity + 1)
            if context.get("file_count", 0) > 3:
                profile.has_multi_step = True

        return profile

    def route(self, request: str, context: dict[str, Any] | None = None) -> IntelligenceMode:
        """V2 路由决策: 硬规则 → 信号评分 → 置信度门禁"""
        text = request.lower()
        ctx = context or {}

        # ── Layer 1: 硬规则 ──
        for pat in self.HARD_SAFE_PATTERNS:
            if re.search(pat, text):
                self._record("SAFE")
                return IntelligenceMode.SAFE

        # ── Layer 2: 信号评分 ──
        best_mode, all_scores = get_route_decision(request, context)
        top_score = all_scores.get(best_mode, 0) if all_scores else 0

        # ── Layer 3: 置信度门禁 ──
        # 低于阈值的 fallback
        if top_score < -1.0:
            mode = IntelligenceMode.FAST
        elif top_score < 0.5:
            mode = IntelligenceMode.BALANCED
        else:
            mode = IntelligenceMode(best_mode)

        # 安全修正: SAFE 必须同时有安全或破坏信号
        if mode == IntelligenceMode.SAFE:
            sec_score = all_scores.get("SAFE", 0)
            if sec_score < 0.5:
                mode = IntelligenceMode.DEEP

        self._record(mode.value)
        return mode

    def _record(self, mode: str) -> None:
        self._stats[mode] = self._stats.get(mode, 0) + 1
        self._stats["total"] = self._stats.get("total", 0) + 1

    def get_mode_config(self, mode: IntelligenceMode) -> ModeConfig:
        """获取模式配置"""
        return MODE_CONFIGS.get(mode, MODE_CONFIGS[IntelligenceMode.BALANCED])

    def get_stats(self) -> dict[str, int]:
        """获取路由统计"""
        return dict(self._stats)

    def summary(self, request: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """完整摘要: 风险分析 + 路由结果 + 模式配置 + 信号详情"""
        profile = self.analyze(request, context)
        mode = self.route(request, context)
        config = self.get_mode_config(mode)
        all_scores = compute_mode_scores(request, context or {})

        return {
            "mode": mode.value,
            "signal_scores": {k: round(v, 2) for k, v in sorted(all_scores.items(), key=lambda x: -x[1])},
            "profile": {
                "complexity": profile.complexity,
                "security_risk": profile.security_risk,
                "destructive_risk": profile.destructive_risk,
                "creative_load": profile.creative_load,
                "has_code": profile.has_code,
                "has_multi_step": profile.has_multi_step,
                "needs_research": profile.needs_research,
                "is_ambiguous": profile.is_ambiguous,
                "confidence": round(profile.confidence, 2),
            },
            "config": {
                "planner": config.planner,
                "critic": config.critic,
                "multi_agent": config.multi_agent,
                "web_search": config.web_search,
                "allow_write": config.allow_write,
                "tests_required": config.tests_required,
                "approval_required": config.approval_required,
                "max_rounds": config.max_rounds,
                "max_agents": config.max_agents,
                "review_type": config.review_type,
                "goal_mode": config.goal_mode,
            },
        }
