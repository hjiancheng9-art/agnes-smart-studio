"""Capability Orchestra — 多源能力协调层

CRUX 的能力来自三个源头：
  Claude   — 推理、自修正、failover、用户记忆、并行执行
  CodeBuddy — 项目感知、LSP、MCP、浏览器、Git、任务管理
  Zbody    — 业务逻辑、领域规则、自定义工作流

本模块解决：
  1. 能力冲突 — 两个源提供了同名工具/规则时，按优先级选择
  2. 能力组合 — 把不同源的能力编排成管道
  3. 能力发现 — 模型能查到当前可用的所有能力
  4. 动态切换 — 根据任务类型自动激活/停用能力集
"""

import threading
from enum import Enum
from pathlib import Path

__all__ = [
    "Capability",
    "CapabilitySource",
    "Orchestra",
    "Priority",
    "ROOT",
    "get_orchestra",
]

ROOT = Path(__file__).resolve().parent.parent


class CapabilitySource(Enum):
    CLAUDE = "claude"  # 推理、自修正、failover、并行
    CODEBUDDY = "codebuddy"  # LSP、MCP、浏览器、Git、任务
    ZBODY = "zbody"  # 业务规则、自定义工作流
    AGNES = "crux"  # 内置（生图/生视频/视觉）
    USER = "user"  # 用户自定义


class Priority(Enum):
    OVERRIDE = 100  # 强制覆盖（Claude 行为规则）
    HIGH = 80  # 用户自定义
    NORMAL = 50  # 默认
    LOW = 30  # 可被覆盖
    FALLBACK = 10  # 备选


class Capability:
    """一项可被编排的能力"""

    def __init__(
        self,
        name: str,
        source: CapabilitySource,
        priority: Priority = Priority.NORMAL,
        description: str = "",
        conflicts_with: list[str] | None = None,
    ) -> None:
        self.name = name
        self.source = source
        self.priority = priority
        self.description = description
        self.conflicts_with = conflicts_with or []
        self.enabled = True
        self._tags: set[str] = set()

    def add_tag(self, tag: str):
        self._tags.add(tag)

    def matches(self, query: str) -> bool:
        q = query.lower()
        return q in self.name.lower() or q in self.description.lower() or q in self._tags


class Orchestra:
    """多源能力协调器。

    单一入口：Orchestra.resolve(tool_name) → 最佳实现
    单一出口：Orchestra.active_profile(task_type) → 激活的能力集
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._profiles: dict[str, list[str]] = {}
        self._rules: list[dict] = []
        self._init_builtins()

    # ════════════════════════════════════════════════
    # 注册
    # ════════════════════════════════════════════════

    def register(self, cap: Capability):
        """注册一项能力。同名按优先级决定保留哪个。"""
        existing = self._capabilities.get(cap.name)
        if existing and existing.priority.value >= cap.priority.value:
            return  # 已有更高优先级的能力
        self._capabilities[cap.name] = cap

    def register_many(self, caps: list[Capability]):
        for c in caps:
            self.register(c)

    # ════════════════════════════════════════════════
    # 冲突解决
    # ════════════════════════════════════════════════

    def resolve(self, name: str) -> Capability | None:
        """解析能力名 → 最佳实现（已解决冲突）"""
        cap = self._capabilities.get(name)
        if not cap:
            return None
        # 检查冲突：如果某冲突能力已注册且优先级更高，禁用当前
        for conflict_name in cap.conflicts_with:
            other = self._capabilities.get(conflict_name)
            if other and other.priority.value > cap.priority.value:
                cap.enabled = False
        return cap if cap.enabled else None

    def resolve_all(self, names: list[str]) -> list[Capability]:
        return [c for name in names if (c := self.resolve(name))]

    # ════════════════════════════════════════════════
    # 场景配置
    # ════════════════════════════════════════════════

    def define_profile(self, name: str, capabilities: list[str], description: str = ""):
        """定义一个能力配置集（按任务类型激活）"""
        self._profiles[name] = capabilities

    def active_profile(self, task_type: str = "coding") -> list[Capability]:
        """返回当前任务类型应激活的能力列表"""
        names = self._profiles.get(task_type, self._profiles.get("coding", []))
        return self.resolve_all(names)

    def add_rule(self, condition: str, action: str, source: CapabilitySource):
        """添加协调规则（condition → 激活某能力）"""
        self._rules.append(
            {
                "condition": condition,
                "action": action,
                "source": source.value,
            }
        )

    # ════════════════════════════════════════════════
    # 查询
    # ════════════════════════════════════════════════

    def list_by_source(self, source: CapabilitySource) -> list[Capability]:
        return [c for c in self._capabilities.values() if c.source == source and c.enabled]

    def search(self, query: str) -> list[Capability]:
        return [c for c in self._capabilities.values() if c.matches(query) and c.enabled]

    def summary(self) -> str:
        """生成能力总览，注入系统提示词"""
        by_source = {}
        for cap in self._capabilities.values():
            if cap.enabled:
                by_source.setdefault(cap.source.value, []).append(cap.name)

        lines = ["## 能力来源"]
        for src, names in sorted(by_source.items()):
            lines.append(f"- {src}: {', '.join(sorted(names)[:10])}")
        return "\n".join(lines)

    def evaluate_rules(self, event="", tool_name="", error_count=0, provider=""):
        triggered = []
        for rule in self._rules:
            cond, action = rule["condition"], rule["action"]
            if (
                cond.startswith("tool_failed_twice:")
                and event == "tool_error"
                and tool_name == cond.split(":", 1)[1]
                and error_count >= 2
                or cond == "tool_failed_twice"
                and event == "tool_error"
                and error_count >= 2
                or cond.startswith("provider_down:")
                and event == "provider_down"
                and provider == cond.split(":", 1)[1]
                or cond.startswith("error_count:>=")
                and error_count >= int(cond.split(">=", 1)[1])
            ):
                triggered.append(action)
        return triggered

    def execute_actions(self, actions):
        results = {}
        for action in actions:
            if action.startswith("activate:"):
                cap_name = action.split(":", 1)[1]
                cap = self.resolve(cap_name)
                if cap:
                    cap.enabled = True
                    results[action] = f"activated {cap_name}"
            elif action.startswith("notify:"):
                results[action] = action.split(":", 1)[1]
            else:
                results[action] = "unknown action"
        return results

    # ════════════════════════════════════════════════
    # 内置能力
    # ════════════════════════════════════════════════

    def _init_builtins(self):
        """初始化三源能力树"""
        # ── Claude 源：推理与自愈 ──
        self.register(Capability("self_verification", CapabilitySource.CLAUDE, Priority.OVERRIDE, "写完代码自动验证"))
        self.register(Capability("provider_failover", CapabilitySource.CLAUDE, Priority.OVERRIDE, "供应商故障自动切换"))
        self.register(Capability("error_recovery", CapabilitySource.CLAUDE, Priority.OVERRIDE, "工具失败自动恢复"))
        self.register(Capability("user_memory", CapabilitySource.CLAUDE, Priority.HIGH, "跨会话用户记忆"))
        self.register(Capability("parallel_tools", CapabilitySource.CLAUDE, Priority.HIGH, "并行工具调用"))
        self.register(Capability("pre_action_intent", CapabilitySource.CLAUDE, Priority.HIGH, "动手前先声明意图"))
        self.register(Capability("destructive_confirm", CapabilitySource.CLAUDE, Priority.OVERRIDE, "破坏性操作确认"))
        # 结构化补丁引擎：跨文件批量修改 + 自动备份 + 语法校验 + 失败回滚
        self.register(
            Capability(
                "patch_engine",
                CapabilitySource.CLAUDE,
                Priority.HIGH,
                "结构化补丁（多文件批量改 / 自动备份 / 失败回滚）",
            )
        )
        # 自主任务执行器：plan→execute→verify 闭环，LLM 一次传计划即可
        self.register(
            Capability(
                "task_executor",
                CapabilitySource.CLAUDE,
                Priority.HIGH,
                "自主多步任务执行（依赖排序 / 验证门 / 错误恢复）",
            )
        )

        # ── CodeBuddy 源：平台工具 ──
        self.register(Capability("lsp_intel", CapabilitySource.CODEBUDDY, Priority.NORMAL, "LSP 代码智能分析"))
        self.register(Capability("mcp_protocol", CapabilitySource.CODEBUDDY, Priority.NORMAL, "MCP 外部工具协议"))
        self.register(
            Capability("browser_automation", CapabilitySource.CODEBUDDY, Priority.NORMAL, "Playwright 浏览器自动化")
        )
        self.register(Capability("git_workflow", CapabilitySource.CODEBUDDY, Priority.NORMAL, "Git 完整工作流"))
        self.register(Capability("task_manager", CapabilitySource.CODEBUDDY, Priority.NORMAL, "任务持久化与依赖追踪"))
        self.register(Capability("project_awareness", CapabilitySource.CODEBUDDY, Priority.NORMAL, "项目结构感知"))

        # ── Zbody 源：业务规则 ──
        self.register(Capability("domain_rules", CapabilitySource.ZBODY, Priority.HIGH, "领域规则引擎"))
        self.register(Capability("custom_workflows", CapabilitySource.ZBODY, Priority.HIGH, "自定义工作流"))

        # ── CRUX 源：原生 ──
        self.register(Capability("image_gen", CapabilitySource.AGNES, Priority.NORMAL, "AI 生图"))
        self.register(Capability("video_gen", CapabilitySource.AGNES, Priority.NORMAL, "AI 生视频"))
        self.register(Capability("vision_analysis", CapabilitySource.AGNES, Priority.NORMAL, "多模态视觉分析"))

        # ── 场景配置 ──
        self.define_profile(
            "coding",
            [
                "self_verification",
                "error_recovery",
                "parallel_tools",
                "pre_action_intent",
                "destructive_confirm",
                "lsp_intel",
                "git_workflow",
                "project_awareness",
                "task_manager",
                "patch_engine",
                "task_executor",
            ],
            "编程任务",
        )

        self.define_profile(
            "video",
            [
                "video_gen",
                "image_gen",
                "vision_analysis",
                "parallel_tools",
            ],
            "视频制片",
        )

        self.define_profile(
            "research",
            [
                "browser_automation",
                "mcp_protocol",
                "self_verification",
                "user_memory",
            ],
            "调研探索",
        )

        self.define_profile(
            "full",
            [
                "self_verification",
                "provider_failover",
                "error_recovery",
                "user_memory",
                "parallel_tools",
                "pre_action_intent",
                "destructive_confirm",
                "lsp_intel",
                "mcp_protocol",
                "browser_automation",
                "git_workflow",
                "task_manager",
                "project_awareness",
                "domain_rules",
                "custom_workflows",
                "image_gen",
                "video_gen",
                "vision_analysis",
                "patch_engine",
                "task_executor",
            ],
            "全能力",
        )

        # ── 协调规则 ──
        self.add_rule("tool_failed_twice", "activate:error_recovery", CapabilitySource.CLAUDE)
        self.add_rule("provider_503", "activate:provider_failover", CapabilitySource.CLAUDE)
        self.add_rule("destructive_tool", "activate:destructive_confirm", CapabilitySource.CLAUDE)
        self.add_rule("multi_file_edit", "activate:pre_action_intent", CapabilitySource.CLAUDE)


# 单例（线程安全双重检查锁）
_orchestra: Orchestra | None = None
_orchestra_lock = threading.Lock()


def get_orchestra() -> Orchestra:
    global _orchestra
    if _orchestra is None:
        with _orchestra_lock:
            if _orchestra is None:
                _orchestra = Orchestra()
    return _orchestra


def reset_orchestra() -> None:
    """Tear down the orchestra singleton (test isolation / hot reload).

    Orchestra is pure in-memory (capability/rule/profile dicts, no threads or
    OS resources), so nulling the reference is sufficient.
    """
    global _orchestra
    with _orchestra_lock:
        _orchestra = None
