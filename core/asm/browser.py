"""ASM Browser — 浏览器操控方法论

原则：
1. 只读优先 — 先观察页面状态，再决定动作
2. 提交动作需确认 — 表单/点击/输入等操作前确认目标
3. DOM 证据 — 操作前后截图或提取关键元素作为证据
4. 状态回放 — 关键路径可记录和回放
"""

from core.asm import (
    BaseMethodology, MethodologyCheck, MethodologyPolicy,
    TaskProfile, TaskIntent, TaskDomain, RiskLevel,
    MethodologyPhase, register,
)


class BrowserMethodology(BaseMethodology):
    name = "ASM.browser"
    description = "浏览器操控：只读优先、提交确认、DOM 证据、状态回放"
    version = "1.0.0"
    
    intent_filters = {TaskIntent.EXECUTE, TaskIntent.SEARCH, TaskIntent.BROWSE}
    domain_filters = {TaskDomain.BROWSER}
    
    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        checks = [
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="read-first",
                description="操作前先提取页面关键内容/状态（截图或 text）",
                severity="warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="verify-target",
                description="确认交互目标元素存在（visible/enabled）",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="capture-result",
                description="操作后截图或提取变化，验证结果",
                severity="warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="check-navigation",
                description="确认页面状态正确（未被重定向到意外页面）",
                severity="block",
            ),
        ]
        
        if task.risk == RiskLevel.HIGH or task.risk == RiskLevel.CRITICAL:
            checks.append(MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="confirm-submit",
                description="高风险提交操作（表单/删除/修改）需用户确认",
                severity="block",
            ))
        
        return checks
    
    def get_policies(self) -> list[MethodologyPolicy]:
        return [
            MethodologyPolicy(
                name="read-before-write",
                condition="修改浏览器状态前必须先读取当前页面",
                action="require_confirmation",
            ),
            MethodologyPolicy(
                name="screenshot-evidence",
                condition="关键步骤（登录/表单提交/页面跳转）需截图留证",
                action="log_only",
            ),
            MethodologyPolicy(
                name="no-blind-input",
                condition="不允许在不可见/不可交互的元素上执行输入",
                action="deny",
            ),
            MethodologyPolicy(
                name="limit-navigation",
                condition="不跳转到非预期域名（防止被钓鱼/重定向）",
                action="deny",
            ),
        ]


register(BrowserMethodology())
