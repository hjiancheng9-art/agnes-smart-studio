"""ASM — Agent Studio Methodology

核心思想：方法论不是一篇大 prompt，而是可路由、可降级、可局部启用的治理层。

架构：
  ASM Core (通用原则 + 评估器)
  ├─ Code Methodology    (先复现后修复 / 测试闭环)
  ├─ Browser Methodology (只读优先 / 提交确认)
  ├─ File Methodology    (checksum / 备份 / diff)
  ├─ CWIM (ComfyUI)     — 外部加载
  └─ Light Methodology   — 低风险任务免检通道

Methodology Router 根据 task intent/domain/risk 自动选择加载。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


# ── 任务分类 ──────────────────────────────────────────────

class TaskIntent(Enum):
    THINK = "think"          # 问答/分析/推理
    GENERATE = "generate"    # 生成（代码/媒体/文案）
    EXECUTE = "execute"      # 执行（文件/浏览器/工具）
    REVIEW = "review"        # 审查（代码/安全/质量）
    SEARCH = "search"        # 搜索（代码/网络/文件）
    HEAL = "heal"            # 自愈
    CREATE = "create"        # 创造（写入/生成/发布）
    FIX = "fix"              # 修复（代码/配置）
    BROWSE = "browse"        # 浏览（浏览器只读）
    WRITE = "write"          # 写入（文件/配置）
    READ = "read"            # 读取（文件/数据）


class TaskDomain(Enum):
    GENERAL = "general"
    CODE = "code"
    BROWSER = "browser"
    FILE = "file"
    COMFYUI = "comfyui"
    SKILL = "skill"
    CREATIVE = "creative"
    SYSTEM = "system"


class RiskLevel(Enum):
    LOW = 0          # 只读 / 无副作用
    MEDIUM = 1       # 有副作用但可回滚
    HIGH = 2         # 不可逆 / 修改系统状态
    CRITICAL = 3     # 生产环境 / 对外发布


@dataclass
class TaskProfile:
    """任务画像 — 方法论选择的依据。"""
    intent: TaskIntent | str
    domain: TaskDomain | str
    risk: RiskLevel | str = RiskLevel.LOW
    has_side_effects: bool = False
    is_reversible: bool = True
    estimated_cost: float = 0.0  # 预估 token 成本


# ── 方法论基础类 ──────────────────────────────────────────

class MethodologyPhase(Enum):
    BEFORE = "before"   # 执行前检查
    AFTER = "after"     # 执行后验证
    WRAP = "wrap"       # 收尾/回滚


@dataclass
class MethodologyCheck:
    """一条方法论检查项。"""
    phase: MethodologyPhase
    name: str
    description: str
    severity: str = "warn"  # "block" | "warn" | "info"


@dataclass
class MethodologyPolicy:
    """方法论策略 — 决定允许/禁止某类动作。"""
    name: str
    condition: str  # 策略描述
    action: Literal["allow", "deny", "require_confirmation", "log_only"]


class BaseMethodology:
    """方法论基类。"""
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    
    # 覆盖的任务画像范围
    intent_filters: set[TaskIntent] = set()
    domain_filters: set[TaskDomain] = set()
    max_risk: RiskLevel = RiskLevel.CRITICAL
    
    def get_checks(self, task: TaskProfile) -> list[MethodologyCheck]:
        """获取适用于该任务的所有检查项。"""
        return []
    
    def get_policies(self) -> list[MethodologyPolicy]:
        """获取策略列表。"""
        return []
    
    def applies_to(self, task: TaskProfile) -> bool:
        """判断此方法论是否适用于该任务。"""
        intent_match = not self.intent_filters or task.intent in self.intent_filters
        domain_match = not self.domain_filters or task.domain in self.domain_filters
        risk_ok = RiskLevel(task.risk).value <= self.max_risk.value
        return intent_match and domain_match and risk_ok


# ── 方法论注册表 ──────────────────────────────────────────

class MethodologyRegistry:
    """方法论注册表 — 全局唯一。"""
    
    def __init__(self):
        self._methodologies: dict[str, BaseMethodology] = {}
    
    def register(self, methodology: BaseMethodology) -> None:
        if methodology.name:
            self._methodologies[methodology.name] = methodology
    
    def get(self, name: str) -> BaseMethodology | None:
        return self._methodologies.get(name)
    
    def all(self) -> list[BaseMethodology]:
        return list(self._methodologies.values())
    
    def select_for(self, task: TaskProfile) -> list[BaseMethodology]:
        """根据任务画像选择适用的方法论（按优先级排序）。"""
        matched = []
        for m in self._methodologies.values():
            if m.applies_to(task):
                matched.append(m)
        return matched


# 全局注册表
_REGISTRY = MethodologyRegistry()


def get_registry() -> MethodologyRegistry:
    return _REGISTRY


def register(methodology: BaseMethodology) -> None:
    _REGISTRY.register(methodology)
