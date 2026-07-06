"""ASM File — 文件操作方法论

原则：
1. Patch 前 checksum — 任何写操作前记录文件状态
2. 备份 — 高风险操作创建 .bak 文件
3. Diff 可解释 — 每个修改附带 diff + 理由
4. Rollback — 失败时自动回滚到备份
"""

from core.asm import (
    BaseMethodology, MethodologyCheck, MethodologyPolicy,
    TaskProfile, TaskIntent, TaskDomain, RiskLevel,
    MethodologyPhase, register,
)


class FileMethodology(BaseMethodology):
    name = "ASM.file"
    description = "文件操作：checksum 前、备份、diff 可解释、回滚"
    version = "1.0.0"
    
    intent_filters = {TaskIntent.EXECUTE, TaskIntent.CREATE, TaskIntent.HEAL, TaskIntent.WRITE, TaskIntent.FIX}
    domain_filters = {TaskDomain.FILE, TaskDomain.CODE}
    
    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        checks = [
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="checksum-before-write",
                description="写文件前记录原文件 hash",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="backup-risky-files",
                description="高风险修改（.py/.json/.yaml 核心文件）创建 .bak",
                severity="block" if task.risk == RiskLevel.CRITICAL else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="diff-verifiable",
                description="修改后生成可读的 diff，确认只改了目标内容",
                severity="block",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="syntax-check",
                description="修改 .py / .json / .yaml 后检查语法",
                severity="block",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.WRAP,
                name="rollback-on-fail",
                description="如果后续步骤失败，自动回滚文件修改",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
        ]
        
        if task.risk == RiskLevel.CRITICAL:
            checks.append(MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="confirm-critical-change",
                description="临界风险文件修改需用户确认",
                severity="block",
            ))
        
        return checks
    
    def get_policies(self) -> list[MethodologyPolicy]:
        return [
            MethodologyPolicy(
                name="checksum-before-patch",
                condition="patch_file 执行前必须记录所有受影响文件 hash",
                action="deny" if TaskDomain.CODE else "require_confirmation",
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
                condition="删除文件前创建备份",
                action="deny",
            ),
        ]


register(FileMethodology())
