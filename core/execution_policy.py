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
            return f"{base}\n请先调用 `orchestrate` 工具规划执行。不要用逐步思考替代编排。"
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
        kw in t for kw in ("分别分析", "多方案", "对比", "交叉验证", "多个模块",
                            "并行", "多角度", "同时检查", "分别检查")
    )
    # Orchestrate signals: multi-stage workflow
    orch_signals = sum(
        kw in t for kw in ("实现", "完整方案", "修复并验证", "重构", "部署",
                            "执行并测试", "从零搭建", "迁移", "升级")
    )
    # Self-check is a strong orchestrate signal
    _self_check = (
        "自检" in t or "自修" in t or "审计" in t or "audit" in t
        or "zicha" in t or "zixiu" in t or "zijian" in t
        or "self heal" in t or "self-heal" in t or "self_heal" in t
        or "self check" in t or "self repair" in t or "self fix" in t
    )
    if _self_check:
        return ExecutionPolicy(ExecutionMode.ORCHESTRATE, "自检/审计任务需要多阶段编排")

    if swarm_signals >= 2:
        return ExecutionPolicy(ExecutionMode.SWARM, f"检测到 {swarm_signals} 个并行维度信号")

    if orch_signals >= 2:
        return ExecutionPolicy(ExecutionMode.ORCHESTRATE, f"检测到 {orch_signals} 个编排信号")

    # Complex/critical keywords
    complex_kw = ("复杂", "多步骤", "全面", "系统化", "端到端")
    if any(kw in t for kw in complex_kw):
        return ExecutionPolicy(ExecutionMode.ORCHESTRATE, "任务复杂度较高")

    return ExecutionPolicy(ExecutionMode.DIRECT, "简单任务")
