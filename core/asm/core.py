"""ASM Core — 通用原则与评估器

适用于所有任务的基础方法论：
1. 参数不是裸值，而是意图+约束+风险的投影
2. 所有推荐必须可解释（why this, why not that）
3. 不要直接生成最终产物，先理解目标结构
4. 工作流要可验证、可回滚、可诊断
5. 证据优先于直觉
"""

from core.asm import (
    BaseMethodology, MethodologyCheck, MethodologyPolicy,
    TaskProfile, TaskIntent, TaskDomain, RiskLevel,
    MethodologyPhase,
)


class CoreMethodology(BaseMethodology):
    """ASM Core — 所有任务的基底方法论。"""
    name = "ASM.core"
    description = "通用原则：参数语义化、可解释性、先理解后执行、证据优先"
    version = "1.0.0"
    
    # 覆盖所有意图和领域
    max_risk = RiskLevel.CRITICAL
    
    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        checks = []
        
        # 执行前
        if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            checks.append(MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="understand-goal",
                description="高/临界风险：执行前确认目标理解是正确的",
                severity="block",
            ))
        
        if task.has_side_effects and not task.is_reversible:
            checks.append(MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="confirm-side-effects",
                description="不可逆操作：检查是否有备份或回滚方案",
                severity="block",
            ))
        
        # 执行后
        checks.append(MethodologyCheck(
            phase=MethodologyPhase.AFTER,
            name="verify-result",
            description="验证结果是否符合预期（finish_line 是否达成）",
            severity="warn",
        ))
        
        checks.append(MethodologyCheck(
            phase=MethodologyPhase.AFTER,
            name="check-regression",
            description="检查是否有副作用/回归问题",
            severity="warn",
        ))
        
        return checks
    
    def get_policies(self) -> list[MethodologyPolicy]:
        return [
            MethodologyPolicy(
                name="explain-recommendation",
                condition="所有推荐（工具/参数/方案）必须附带理由",
                action="require_confirmation",
            ),
            MethodologyPolicy(
                name="evidence-before-claim",
                condition="宣称目标达成前必须有可验证的证据",
                action="require_confirmation",
            ),
            MethodologyPolicy(
                name="no-blind-retry",
                condition="self-heal 在重试前必须确认上次失败的 root cause",
                action="require_confirmation",
            ),
            MethodologyPolicy(
                name="prefer-reversible",
                condition="有多个方案时，优先选择可回滚的方案",
                action="log_only",
            ),
        ]


# ── 注册 ──────────────────────────────────────────────────
from core.asm import register
register(CoreMethodology())
