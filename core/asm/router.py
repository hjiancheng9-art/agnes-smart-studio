"""ASM Methodology Router — 根据任务画像自动路由到适用方法论

用法：
    from core.asm.router import MethodRouter
    
    router = MethodRouter()
    
    # 方式 1: 显式指定任务画像
    profile = TaskProfile(intent="execute", domain="code", risk="high")
    route = router.route(profile)
    
    # 方式 2: 快捷方式
    route = router.route_for("code", "fix")
    
    # 方式 3: 直接检查
    checks = router.get_checks(profile)
    policies = router.get_policies(profile)
"""

from dataclasses import dataclass, field
from typing import Any

from core.asm import (
    BaseMethodology, MethodologyCheck, MethodologyPolicy,
    TaskProfile, TaskIntent, TaskDomain, RiskLevel,
    MethodologyPhase, get_registry,
)

# ── 域专有方法论的 fallback 配置 ────────────────────────
# 当 Registry 中找到了 ASM.core 但缺少域专有方法论时，使用此映射
DOMAIN_FALLBACK_CHECKS: dict[str, list[dict]] = {
    "comfyui": [
        {"name": "workflow-validate", "phase": "after", "severity": "block",
         "description": "ComfyUI: 校验 workflow 结构（Validator）"},
        {"name": "model-compatible", "phase": "before", "severity": "block",
         "description": "ComfyUI: 确认模型/VAE/ControlNet 兼容"},
        {"name": "lora-lifecycle", "phase": "before", "severity": "warn",
         "description": "ComfyUI: LoRA 版本/参数/加载顺序检查"},
        {"name": "node-graph-valid", "phase": "after", "severity": "block",
         "description": "ComfyUI: 图结构连线有效性检查"},
    ],
}


@dataclass
class MethodologyRoute:
    """路由结果 — 任务应该遵循哪些方法论。"""
    task: TaskProfile
    methodologies: list[BaseMethodology]
    names: list[str] = field(default_factory=list)
    checks: list[MethodologyCheck] = field(default_factory=list)
    policies: list[MethodologyPolicy] = field(default_factory=list)
    blocking_checks: list[MethodologyCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    def __post_init__(self):
        self.names = [m.name for m in self.methodologies]
        self.checks = []
        self.blocking_checks = []
        for m in self.methodologies:
            for c in m.get_checks(self.task):
                self.checks.append(c)
                if c.severity == "block":
                    self.blocking_checks.append(c)
        self.policies = []
        for m in self.methodologies:
            self.policies.extend(m.get_policies())
    
    @property
    def is_blocked(self) -> bool:
        """是否有阻断性检查未通过。"""
        return len(self.blocking_checks) > 0
    
    def summary(self) -> dict:
        """获取路由摘要（供日志/驾驶舱展示）。"""
        return {
            "task": {
                "intent": str(self.task.intent),
                "domain": str(self.task.domain),
                "risk": str(self.task.risk),
                "side_effects": self.task.has_side_effects,
                "reversible": self.task.is_reversible,
            },
            "methodologies": self.names,
            "checks": [
                {"phase": c.phase.value, "name": c.name, "severity": c.severity}
                for c in self.checks
            ],
            "blocking": [c.name for c in self.blocking_checks],
            "policies": [p.name for p in self.policies],
        }


class MethodRouter:
    """方法论路由器 — 根据任务画像选择合适的方论。"""
    
    # 意图到域的默认映射
    _INTENT_DOMAIN_MAP: dict[str, str] = {
        "fix": "code",
        "heal": "code",
        "browse": "browser",
        "navigate": "browser",
        "write": "file",
        "read": "general",
        "search": "general",
        "think": "general",
        "generate": "creative",
    }
    
    # 风险推定
    _INTENT_RISK_MAP: dict[str, str] = {
        "think": "low",
        "search": "low",
        "read": "low",
        "browse": "low",
        "generate": "medium",
        "write": "medium",
        "fix": "medium",
        "navigate": "medium",
        "heal": "high",
        "deploy": "critical",
        "release": "critical",
    }
    
    def _infer_risk(self, intent: str, domain: str) -> RiskLevel:
        """根据意图和领域推断风险等级。"""
        risk_str = self._INTENT_RISK_MAP.get(intent, "medium")
        
        domain_risk_boost = {
            "system": 1,
            "code": 0,
            "file": 0,
            "browser": 1,
            "comfyui": 1,
            "skill": 2,
        }
        boost = domain_risk_boost.get(domain, 0)
        
        risk_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        idx = risk_map.get(risk_str, 1)
        idx = min(idx + boost, 3)
        return RiskLevel(idx)
    
    def route(self, task: TaskProfile | None = None, **kwargs) -> MethodologyRoute:
        """路由：选择适用的方法论。
        
        接受 TaskProfile 对象，或关键字参数构建：
            intent, domain, risk, has_side_effects, is_reversible
        """
        if task is None:
            intent = kwargs.get("intent", "think")
            domain = kwargs.get("domain", "general")
            risk_input = kwargs.get("risk")
            if risk_input is None:
                risk_input = self._infer_risk(intent, domain)
            # 处理 risk 输入：支持 "high" → RiskLevel(2)
            if isinstance(risk_input, str):
                _risk_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}
                risk_input = RiskLevel(_risk_map.get(risk_input, 1))
            task = TaskProfile(
                intent=TaskIntent(intent) if isinstance(intent, str) else intent,
                domain=TaskDomain(domain) if isinstance(domain, str) else domain,
                risk=risk_input if isinstance(risk_input, RiskLevel) else RiskLevel(risk_input),
                has_side_effects=kwargs.get("has_side_effects", False),
                is_reversible=kwargs.get("is_reversible", True),
            )
        
        registry = get_registry()
        methodologies = registry.select_for(task)
        
        # 如果没匹配到方法论，回退到 light
        if not methodologies:
            light = registry.get("ASM.light")
            if light:
                methodologies = [light]
        
        route = MethodologyRoute(task=task, methodologies=methodologies)
        
        # ── 注入域专有 fallback checks ──
        domain_str = str(task.domain.value) if hasattr(task.domain, 'value') else str(task.domain)
        if domain_str in DOMAIN_FALLBACK_CHECKS:
            for spec in DOMAIN_FALLBACK_CHECKS[domain_str]:
                existing = any(c.name == spec["name"] for c in route.checks)
                if not existing:
                    check = MethodologyCheck(
                        phase=MethodologyPhase(spec["phase"]),
                        name=spec["name"],
                        description=spec["description"],
                        severity=spec["severity"],
                    )
                    route.checks.append(check)
                    if check.severity == "block":
                        route.blocking_checks.append(check)
        
        return route
        
        return route
    
    def route_for(self, domain: str, intent: str = "think") -> MethodologyRoute:
        """快捷路由：domain + intent 自动推断其余属性。"""
        return self.route(
            intent=intent,
            domain=domain,
            risk=self._infer_risk(intent, domain),
        )
    
    def get_checks(self, task: TaskProfile | None = None, **kwargs) -> list[MethodologyCheck]:
        """获取给定任务的所有方法论检查项。"""
        return self.route(task, **kwargs).checks
    
    def get_policies(self, task: TaskProfile | None = None, **kwargs) -> list[MethodologyPolicy]:
        """获取给定任务的所有方法论策略。"""
        return self.route(task, **kwargs).policies
    
    def get_blocking_checks(self, task: TaskProfile | None = None, **kwargs) -> list[MethodologyCheck]:
        """获取阻断性检查项。"""
        return self.route(task, **kwargs).blocking_checks
    
    def should_block(self, task: TaskProfile | None = None, **kwargs) -> bool:
        """检查是否应阻断该任务。"""
        return self.route(task, **kwargs).is_blocked


# ── 全局实例 ──────────────────────────────────────────────
_default_router: MethodRouter | None = None


def get_router() -> MethodRouter:
    global _default_router
    if _default_router is None:
        _default_router = MethodRouter()
    return _default_router


def route(task: TaskProfile | None = None, **kwargs) -> MethodologyRoute:
    """快捷路由。"""
    return get_router().route(task, **kwargs)
