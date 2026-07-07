"""ASM Core — 通用原则与评估器（按 GPT 规格修正）

ASM.core 始终加载，是方法论基底。
原则：
1. 参数不是裸值，而是意图+约束+风险的投影
2. 所有推荐必须可解释
3. 不要直接生成最终产物，先理解目标结构
4. 产物必须可验证（GPT 规格强调：不是只检查结果，是有客观 finish_line）
5. 证据优先于直觉
6. 失败必须写入 EventLog（从 CWIM "失败不是结束而是学习" 泛化）
"""

from core.asm import (
    BaseMethodology,
    MethodologyCheck,
    MethodologyPhase,
    MethodologyPolicy,
    RiskLevel,
    TaskProfile,
    register,
)


class CoreMethodology(BaseMethodology):
    name = "ASM.core"
    description = "通用原则：参数语义化、可解释、先理解后执行、产物可验证、证据优先"
    version = "1.0.0"
    max_risk = RiskLevel.CRITICAL

    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        checks = []

        # ── BEFORE ──
        if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            checks.append(
                MethodologyCheck(
                    phase=MethodologyPhase.BEFORE,
                    name="understand-goal",
                    description="高/临界风险：执行前确认目标理解正确，finish_line 是否明确",
                    severity="block",
                )
            )

        if task.has_side_effects and not task.is_reversible:
            checks.append(
                MethodologyCheck(
                    phase=MethodologyPhase.BEFORE,
                    name="confirm-side-effects",
                    description="不可逆操作：检查是否有备份或回滚方案",
                    severity="block",
                )
            )

        # ── AFTER ──
        checks.append(
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="verify-result",
                description="验证 finish_line 是否达成（不是'看起来好了'，是客观证据）",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            )
        )

        checks.append(
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="check-regression",
                description="检查是否有副作用/回归问题",
                severity="warn",
            )
        )

        # GPT 规格新增：副作用确认
        if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            checks.append(
                MethodologyCheck(
                    phase=MethodologyPhase.WRAP,
                    name="confirm-no-side-effects",
                    description="确认没有未预期的副作用（文件修改/依赖变化/目录创建）",
                    severity="block",
                )
            )

        return checks

    def get_policies(self) -> list[MethodologyPolicy]:
        return [
            MethodologyPolicy(
                name="explain-recommendation",
                condition="所有推荐必须附带理由（why this, why not alternatives）",
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
            # GPT 新增
            MethodologyPolicy(
                name="log-failures",
                condition="所有失败必须写入 EventLog（错误签名+上下文+时间）",
                action="require_confirmation",
            ),
        ]


register(CoreMethodology())
