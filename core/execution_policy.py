"""ExecutionPolicy — cheap pre-model routing to decide execution mode.

Runs BEFORE the LLM call. Uses simple keyword matching to determine whether
the task should use direct tools, a skill, orchestrate, or agent_swarm.

Fixes the "model doesn't use orchestration" problem by making the decision
in code rather than hoping the model infers it from a bloated system prompt.
"""

from __future__ import annotations

from enum import Enum


class ExecutionMode(str, Enum):
    DIRECT = "direct"
    SKILL = "skill"
    ORCHESTRATE = "orchestrate"
    SWARM = "swarm"


class ExecutionPolicy:
    __slots__ = ("mode", "reason", "selected_skill")

    def __init__(self, mode: ExecutionMode, reason: str, selected_skill: str = ""):
        self.mode = mode
        self.reason = reason
        self.selected_skill = selected_skill

    def to_instruction(self) -> str:
        """Produce a short runtime instruction injectable near user message."""
        base = f"[执行策略] mode={self.mode.value} | {self.reason}"
        if self.mode == ExecutionMode.ORCHESTRATE:
            return f"{base}\n请分步骤执行：先规划 → 再实现 → 最后验证。每个步骤调用对应工具，不要一次性全做完。"
        if self.mode == ExecutionMode.SWARM:
            return f"{base}\n请使用 `agent_swarm` 并行分派子智能体。"
        if self.mode == ExecutionMode.SKILL and self.selected_skill:
            return f"{base}\n请先加载技能 `{self.selected_skill}`。"
        return f"{base}"


def choose_policy(user_text: str) -> ExecutionPolicy:
    """Rule-based execution mode selection. Cheap — no model call needed."""
    t = user_text.lower()

    # Swarm signals: multiple independent dimensions
    swarm_signals = sum(
        kw in t
        for kw in (
            "分别分析",
            "多方案",
            "对比",
            "交叉验证",
            "多个模块",
            "并行",
            "多角度",
            "同时检查",
            "分别检查",
            "分别",
            "多个文件",
            "审查并",
            "设计差异",
            "两个文件",
            "这几",
        )
    )
    # Orchestrate signals: multi-stage workflow (need 2+ matches to trigger)
    orch_signals = sum(
        kw in t
        for kw in (
            "实现",
            "完整方案",
            "修复并验证",
            "重构",
            "部署",
            "执行并测试",
            "从零搭建",
            "迁移",
            "升级",
            "写一个",
            "新建",
            "创建",
            "加一个",
            "加个",
            "改",
            "修",
            "跑测试",
            "审查",
            "跑一下",
            "写代码",
            "写个",
            "生成一个",
            "跑它",
            "跑这个",
            "运行测试",
            "验证一下",
            "跑验证",
            "写测试",
            "审查代码",
            "搭一个",
            "从零开始",
            "创建一个",
            "写个测试",
            "加上测试",
            "项目",
            "新功能",
            "写个脚本",
        )
    )
    # ── Self-check: semantic feature based (not fragile char-count) ──
    # Chinese self-audit keywords only escalate to ORCHESTRATE when paired
    # with scope or action signals — prevents casual "帮我自检一下" from
    # triggering a full orchestration run.
    _cn_audit_kw = ("自检", "自修", "审计", "audit")
    _scope_kw = (
        "整个",
        "全部",
        "所有",
        "全面",
        "系统",
        "模块",
        "核心",
        "整个项目",
        "代码质量",
        "安全漏洞",
        "entire",
        "full",
        "all",
        "system",
        "module",
        "codebase",
        "repository",
        "project",
    )
    _action_kw = (
        "修复",
        "输出",
        "报告",
        "审查",
        "扫描",
        "加固",
        "优化",
        "fix",
        "report",
        "output",
        "review",
        "scan",
        "harden",
        "optimize",
    )
    _has_cn_audit = any(kw in t for kw in _cn_audit_kw)
    _has_scope = any(kw in t for kw in _scope_kw)
    _has_action = any(kw in t for kw in _action_kw)
    # Must have audit keyword + at least one of scope or action
    _self_check = (_has_cn_audit and (_has_scope or _has_action)) or (
        # English self-heal/repair phrases are always strong signals
        "self heal" in t or "self-heal" in t or "self_heal" in t or "self repair" in t or "self fix" in t
    )
    if _self_check:
        return ExecutionPolicy(ExecutionMode.ORCHESTRATE, "自检/审计任务需要多阶段编排")

    if swarm_signals >= 1:
        return ExecutionPolicy(ExecutionMode.SWARM, f"检测到 {swarm_signals} 个并行维度信号")

    if orch_signals >= 2:
        return ExecutionPolicy(ExecutionMode.ORCHESTRATE, f"检测到 {orch_signals} 个编排信号")

    return ExecutionPolicy(ExecutionMode.DIRECT, "简单任务")
