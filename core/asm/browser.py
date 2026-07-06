"""ASM Browser — 浏览器操控方法论（按 GPT 规格修正）

GPT 规格关键修正：
- DOM 证据不只是截图，关键路径（登录/表单提交/页面跳转）必须截图 + innerText
- 新增 navigation-lock：不允许跳转到非预期域名
- 提交确认针对高风险操作
"""

from core.asm import (
    BaseMethodology, MethodologyCheck, MethodologyPolicy,
    TaskProfile, TaskIntent, TaskDomain, RiskLevel,
    MethodologyPhase, register,
)


class BrowserMethodology(BaseMethodology):
    name = "ASM.browser"
    description = "浏览器操控：只读优先、DOM证据（截图+text）、域名锁定、提交确认"
    version = "1.0.0"
    intent_filters = {TaskIntent.EXECUTE, TaskIntent.SEARCH, TaskIntent.BROWSE}
    domain_filters = {TaskDomain.BROWSER}
    
    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        checks = [
            # BEFORE
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="read-first",
                description="操作前先提取页面关键内容/状态（截图或 innerText）",
                severity="warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.BEFORE,
                name="verify-target",
                description="确认交互目标元素存在（visible + enabled）",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
            # AFTER
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="dom-evidence",
                description="操作后截图或提取变化——关键路径（登录/表单提交/页面跳转）必须截图",
                severity="block" if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "warn",
            ),
            MethodologyCheck(
                phase=MethodologyPhase.AFTER,
                name="navigation-lock",
                description="确认页面状态正确（未被重定向到意外域名，URL 仍在预期范围内）",
                severity="block",
            ),
        ]
        
        # 高风险操作的提交确认
        if task.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
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
                action="require_confirmation",
            ),
            MethodologyPolicy(
                name="no-blind-input",
                condition="不允许在不可见/不可交互的元素上执行输入",
                action="deny",
            ),
            MethodologyPolicy(
                name="domain-lock",
                condition="不跳转到非预期域名（防止被钓鱼/重定向/跨域）",
                action="deny",
            ),
        ]


register(BrowserMethodology())
