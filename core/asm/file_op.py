"""ASM File — 文件操作方法论（按 GPT 规格修正）

GPT 规格关键修正：
- .bak 保留到会话结束，不是永久保留
- syntax-check 对所有 .py/.json/.yaml 必须执行
- 每步记录 checksum + diff
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


class FileMethodology(BaseMethodology):
    name = "ASM.file"
    description = "文件操作：checksum、会话级.bak、diff 可解释、语法检查、回滚"
    version = "1.0.0"
    intent_filters = {TaskIntent.EXECUTE, TaskIntent.CREATE, TaskIntent.HEAL, TaskIntent.WRITE, TaskIntent.FIX}
    domain_filters = {TaskDomain.FILE, TaskDomain.CODE}

    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        checks = [
            # BEFORE
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="checksum-before-write",
                description="写文件前记录原文件 hash（sha256 前16位）",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="backup-risky-files",
                description="高风险修改创建 .bak（保留到会话结束，不是永久）",
                severity="block" if task.risk == RiskLevel.CRITICAL else "warn",
            ),
            # AFTER
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="diff-verifiable",
                description="修改后生成可读的 diff，确认只改了目标内容",
                severity="block",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="syntax-check",
                description="修改 .py / .json / .yaml / .toml 后必须检查语法",
                severity="block",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.WRAP,
                name="rollback-on-fail",
                description="如果后续步骤失败，自动回滚文件修改",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
            # 会话结束时清理 .bak
            MethodologyCheck(
                phase=MethodologyPhase.WRAP,
                name="cleanup-bak",
                description="会话结束时清理 .bak 文件（保留不超过会话生命周期）",
                severity="warn",
            ),
        ]

        if task.risk == RiskLevel.CRITICAL:
            checks.append(
                MethodologyCheck(
                    phase=MethodologyPhase.BEFORE,
                    name="confirm-critical-change",
                    description="临界风险文件修改需用户确认",
                    severity="block",
                )
            )

        return checks

    def get_policies(self) -> list[MethodologyPolicy]:
        return [
            MethodologyPolicy(
                name="checksum-before-patch",
                condition="patch_file 执行前必须记录所有受影响文件 hash",
                action="deny",
            ),
            MethodologyPolicy(
                name="no-silent-write",
                condition="不允许不产生 diff 的写操作（空写入视为假操作）",
                action="deny",
            ),
            MethodologyPolicy(
                name="minimal-hunk",
                condition="只修改目标行，不附带格式调整或无关改动",
                action="log_only",
            ),
            MethodologyPolicy(
                name="backup-before-delete",
                condition="删除文件前创建 .bak 备份",
                action="deny",
            ),
            MethodologyPolicy(
                name="bak-session-only",
                condition=".bak 文件仅保留到会话结束，不永久驻留",
                action="log_only",
            ),
        ]


register(FileMethodology())
