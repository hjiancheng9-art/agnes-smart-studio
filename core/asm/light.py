"""ASM Light — 轻量方法论（低风险任务专用）

不阻截、不检查、不要求证据。
仅保留最小前提：参数有效 + 结果可用。
适用于问答、搜索、只读分析等无副作用场景。
"""

from core.asm import (
    BaseMethodology,
    MethodologyCheck,
    TaskProfile,
    TaskIntent,
    TaskDomain,
    RiskLevel,
    MethodologyPhase,
    register,
)


class LightMethodology(BaseMethodology):
    name = "ASM.light"
    description = "轻量方法论：低风险任务免检通道，仅保底参数和结果可用性"
    version = "1.0.0"

    # 只覆盖低风险任务
    max_risk = RiskLevel.LOW

    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        return [
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="params-valid",
                description="确认输入参数完整/格式正确",
                severity="warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="result-usable",
                description="确认返回结果非空/非错误",
                severity="warn",
            ),
        ]


register(LightMethodology())
