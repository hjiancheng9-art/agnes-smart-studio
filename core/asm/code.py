"""ASM Code — 代码方法论（按 GPT 规格修正）

GPT 规格关键修正：
- "先复现后修复" 不是在完整测试套件上复现，而是在 diagnostics 层面确认错误仍存在
- 新增 no-silent-fix（无 diff 视为假修复）+ minimal-change（只改目标行）
- 所有修复证据写入 EventLog
"""

from core.asm import (
    BaseMethodology,
    MethodologyCheck,
    MethodologyPhase,
    MethodologyPolicy,
    RiskLevel,
    TaskDomain,
    TaskIntent,
    TaskProfile,
    register,
)


class CodeMethodology(BaseMethodology):
    name = "ASM.code"
    description = "代码修复：diagnostics复现、no evidence no patch、测试闭环、最小变更"
    version = "1.0.0"
    intent_filters = {TaskIntent.EXECUTE, TaskIntent.HEAL, TaskIntent.REVIEW, TaskIntent.FIX}
    domain_filters = {TaskDomain.CODE}

    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        checks = [
            # BEFORE: 先查 diagnostics，不是跑完整测试套件
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="check-diagnostics",
                description="先查 diagnostics 确认错误当前仍存在（不跑完整测试，只看 lsp/diagnostics）",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="capture-pre-state",
                description="修复前记录文件 checksum + git diff + diagnostics",
                severity="block",
            ),
            # AFTER: 验证 diff 不为空
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="verify-diff",
                description="确认 patch 产生了预期 diff（不是空 patch/假修复）",
                severity="block",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="minimal-change",
                description="确认只改了目标行/函数/文件，没有附带重构",
                severity="warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="no-silent-fix",
                description="确认错误签名变化了（不只是改了 log/注释/提示语，真正修复了根因）",
                severity="block",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="test-regression",
                description="运行相关测试确认没有回归",
                severity="block" if task.risk == RiskLevel.CRITICAL else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="evidence-log",
                description="将修复证据写入 EventLog（pre/post diff, diagnostics, test结果）",
                severity="warn",
            ),
        ]

        # 临界风险额外检查
        if task.risk == RiskLevel.CRITICAL:
            checks.append(
                MethodologyCheck(
                    phase=MethodologyPhase.WRAP,
                    name="rollback-ready",
                    description="临界风险修复：确认回滚方案就绪（patch_undo 可用）",
                    severity="block",
                )
            )

        return checks

    def get_policies(self) -> list[MethodologyPolicy]:
        return [
            MethodologyPolicy(
                name="error-still-present",
                condition="修复前必须通过 diagnostics 确认错误当前仍存在（不复现不修复）",
                action="deny",
            ),
            MethodologyPolicy(
                name="no-empty-patch",
                condition="patch_file 产生的 diff 必须非空（空 diff 视为假修复）",
                action="deny",
            ),
            MethodologyPolicy(
                name="minimal-change-only",
                condition="只修改与目标直接相关的代码行/函数/文件，不做附带重构",
                action="log_only",
            ),
            MethodologyPolicy(
                name="test-before-after",
                condition="修复前后需对比测试结果，diff 输出到 metadata",
                action="require_confirmation",
            ),
        ]


register(CodeMethodology())
