"""ASM Code — 代码方法论

原则：
1. 先复现后修复 — 没复现的 bug 不算 bug
2. No evidence, no patch — 没有证据不修改
3. 假修复检测 — patch 前后必须有 diff 证明
4. 测试闭环 — 修复后测试必须通过，旧测试不能坏
"""

from core.asm import (
    BaseMethodology, MethodologyCheck, MethodologyPolicy,
    TaskProfile, TaskIntent, TaskDomain, RiskLevel,
    MethodologyPhase, register,
)


class CodeMethodology(BaseMethodology):
    name = "ASM.code"
    description = "代码修复：先复现后修复、no evidence no patch、测试闭环"
    version = "1.0.0"
    
    intent_filters = {TaskIntent.EXECUTE, TaskIntent.HEAL, TaskIntent.REVIEW, TaskIntent.FIX}
    domain_filters = {TaskDomain.CODE}
    
    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        checks = [
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="reproduce-failure",
                description="先复现原始失败，确认能稳定复现再开始修复",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="capture-pre-state",
                description="修复前记录文件 checksum + git diff + diagnostics",
                severity="block",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="verify-diff",
                description="确认 patch 产生了预期 diff（不是假修复）",
                severity="block",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="test-regression",
                description="运行测试确认没有回归",
                severity="block" if task.risk == RiskLevel.CRITICAL else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="evidence-log",
                description="将修复证据写入 EventLog（pre/post diff, test结果）",
                severity="warn",
            ),
        ]
        
        if task.risk == RiskLevel.CRITICAL:
            checks.append(MethodologyCheck(
                phase=MethodologyPhase.WRAP,
                name="rollback-ready",
                description="临界风险修复：确认回滚方案就绪",
                severity="block",
            ))
        
        return checks
    
    def get_policies(self) -> list[MethodologyPolicy]:
        return [
            MethodologyPolicy(
                name="reproducible-required",
                condition="未复现的失败不能宣称已修复",
                action="deny",
            ),
            MethodologyPolicy(
                name="no-empty-patch",
                condition="patch_file 提交空 diff 时视为假修复",
                action="deny",
            ),
            MethodologyPolicy(
                name="minimal-change",
                condition="只修改与目标直接相关的代码，不做附带重构",
                action="log_only",
            ),
            MethodologyPolicy(
                name="test-before-after",
                condition="修复前后需对比测试结果，输出到 diff",
                action="require_confirmation",
            ),
        ]


register(CodeMethodology())
