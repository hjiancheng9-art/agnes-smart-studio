"""方法论引擎 — 将 AGENTS.md / METHODOLOGY.md 硬约束嵌入 CRUX 运行时。

当前注入方式（rules 文本 → system prompt）是"软建议"，LLM 可以不遵守。
本模块将方法论落地为引擎骨骼——禁区拦截、任务分级、状态追踪、合规检查。

分层：
    L1 禁区（PROTECTED_FILES/PATHS）          — 写操作硬拦截，无关 LLM
    L2 分级（TaskLevel + classify_task）       — 自动判定 A/B/C/D 级
    L3 守卫（methodology_pre_check）           — 工具调用前合规检查
    L4 追踪（MethodologyState + /method 命令） — 可见性与可问责性

用法：
    from core.methodology import MethodologyState, classify_task, methodology_pre_check

    state = MethodologyState()
    state.classify(user_input, [])
    if not methodology_pre_check("write_file", {"path": "core/config.py"}, state):
        raise BlockedError("core/config.py 在保护区")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar


# ═══════════════════════════════════════════════════════════════════
# L1 — 禁区（硬件拦截）
# ═══════════════════════════════════════════════════════════════════

# 绝对禁止区间（来自 rules/self-preservation.rules.md 禁区列表）
PROTECTED_FILES: frozenset[str] = frozenset(
    {
        "core/config.py",
        "core/exceptions.py",
        "core/encoding.py",
        "crux_studio.py",
        "core/methodology.py",
    }
)

# 禁止区间的关键方法/属性
PROTECTED_SYMBOLS: dict[str, frozenset[str]] = {
    "core/config.py": frozenset({"SETTINGS", "save_global_auth"}),
    "core/exceptions.py": frozenset({"CruxError.__init__", "CruxError.__str__"}),
    "core/encoding.py": frozenset({"setup"}),
    "crux_studio.py": frozenset({"_SUBCOMMANDS", "main"}),
}

# 禁止添加未验证包的依赖文件
PROTECTED_DEP_FILES: frozenset[str] = frozenset({"requirements.txt", "pyproject.toml"})


def is_protected_file(path: str) -> bool:
    """判断文件路径是否在禁区列表中。"""
    normalized = path.replace("\\", "/")
    for p in PROTECTED_FILES:
        if normalized.endswith(p.replace("\\", "/")):
            return True
    return False


def is_protected_dep_file(path: str) -> bool:
    """判断是否为保护区内的依赖文件。"""
    return Path(path).name in PROTECTED_DEP_FILES


# ═══════════════════════════════════════════════════════════════════
# L2 — 任务分级
# ═══════════════════════════════════════════════════════════════════


class TaskLevel(Enum):
    """方法论第 0 章 A/B/C/D 任务分级。

    A 微任务  — 单行修复/typo/小调整，跳过 Plan/TDD/Worktree，必须看 diff
    B 普通开发 — 简短计划 + 验证，Bug 修复必须补回归测试
    C 复杂工程 — Plan + 分阶段实现 + 测试 + Review，3+ 文件或架构变动
    D 高风险   — 必须 Spec + 风险评估 + 人工确认 + 隔离 + CI
    """

    A = "micro"
    B = "normal"
    C = "complex"
    D = "critical"


# C/D 级关键词（触发升级）
_CD_KEYWORDS = frozenset(
    {
        "database", "migration", "schema", "auth", "authentication",
        "security", "api", "deploy", "release", "refactor", "architecture",
        "拆分", "重构", "数据库", "安全", "认证", "部署", "架构",
    }
)

# 敏感路径前缀
_SENSITIVE_PATHS = frozenset({"core/config", "core/provider", "core/chat", "core/tools", "models.json"})


def classify_task(intent: str, files_touched: list[str] | None = None) -> TaskLevel:
    """根据用户意图和涉及文件自动判定 A/B/C/D 级。

    规则（优先级递减）：
        D 级 — 意图含安全/认证/部署关键词，或触及 models.json + 多个核心文件
        C 级 — 涉及 3+ 文件或含重构/架构关键词
        B 级 — 涉及 2 个文件或含 bug/fix
        A 级 — 其余（单文件、单行修改）
    """
    files = files_touched or []
    n_files = len(files)
    intent_lower = intent.lower()

    # D 级触发
    d_triggers = {"deploy", "release", "rollback", "migrate", "凭证", "密码", "token"}
    if any(t in intent_lower for t in d_triggers):
        return TaskLevel.D
    if n_files >= 5 and any(p.startswith("core/") for p in files):
        return TaskLevel.D

    # C 级触发
    c_triggers = {"refactor", "architect", "拆", "重构", "架构", "拆分", "模块化"}
    if any(t in intent_lower for t in c_triggers):
        return TaskLevel.C
    if n_files >= 3:
        return TaskLevel.C
    if n_files >= 2 and any(f.startswith("core/") for f in files):
        return TaskLevel.C

    # B 级触发
    b_triggers = {"fix", "bug", "修复", "补", "implement", "实现", "feature", "新增", "add"}
    if any(t in intent_lower for t in b_triggers) or n_files >= 2:
        return TaskLevel.B

    # 默认 A 级
    return TaskLevel.A


# ═══════════════════════════════════════════════════════════════════
# L3 — 工具调用前合规检查
# ═══════════════════════════════════════════════════════════════════


@dataclass
class MethodologyState:
    """当前任务的方法论遵守状态。追踪从任务开始到结束的合规性。"""

    task_level: TaskLevel = TaskLevel.A
    plan_exists: bool = False
    test_baseline_recorded: bool = False
    worktree_created: bool = False
    files_touched: list[str] = field(default_factory=list)
    tdd_phase: str = ""  # red | green | refactor
    step_count: int = 0
    tool_call_count: int = 0

    # C/D 级要求
    @property
    def requires_plan(self) -> bool:
        return self.task_level in (TaskLevel.C, TaskLevel.D)

    @property
    def requires_test_baseline(self) -> bool:
        return self.task_level in (TaskLevel.C, TaskLevel.D)

    @property
    def requires_worktree(self) -> bool:
        return self.task_level == TaskLevel.D

    def classify(self, intent: str, files: list[str]) -> None:
        self.task_level = classify_task(intent, files)

    def record_tool(self, tool_name: str) -> None:
        self.tool_call_count += 1

    def record_step(self) -> None:
        self.step_count += 1

    def summary(self) -> str:
        """生成 /method 展示的摘要。"""
        level_label = {TaskLevel.A: "A 微任务", TaskLevel.B: "B 普通", TaskLevel.C: "C 复杂", TaskLevel.D: "D 高风险"}
        checks = []
        if self.requires_plan:
            checks.append("Plan" if self.plan_exists else "Plan ✗")
        if self.requires_test_baseline:
            checks.append("基线" if self.test_baseline_recorded else "基线 ✗")
        if self.requires_worktree:
            checks.append("Worktree" if self.worktree_created else "Worktree ✗")
        checks.append(f"TDD:{self.tdd_phase or '-'}")
        return (
            f"任务等级: {level_label.get(self.task_level, '?')}  "
            + " | ".join(checks)
            + f"  | 步骤:{self.step_count} 工具:{self.tool_call_count}"
        )


def methodology_pre_check(tool_name: str, args: dict, state: MethodologyState | None = None) -> tuple[bool, str]:
    """工具调用前的方法论合规检查。

    Returns:
        (allowed, reason) — allowed=False 时 reason 说明拦截原因。
    """
    # ── L1 禁区 — 硬拦截（无关任务等级）──
    file_path = args.get("path") or args.get("file_path") or args.get("target") or ""
    if file_path and is_protected_file(file_path):
        # 仅拦截写入/删除操作，读取通过
        if tool_name in ("write_file", "edit_file", "patch_file", "safe_rewrite_file", "delete_files"):
            return False, f"禁区文件不可修改: {file_path}"

    # 依赖文件添加受保护
    if (tool_name == "pip_install" and args.get("package")) or (
        is_protected_dep_file(file_path) and tool_name in ("write_file", "edit_file")
    ):
        return False, f"依赖文件 {file_path} 不可直接修改（需人工审核新包）"

    # ── L2/L3 — 任务等级守卫 ──
    if state is None:
        return True, ""

    level = state.task_level

    # D 级额外约束
    if level == TaskLevel.D:
        if tool_name in ("git_add_commit", "git_push", "git_pr_create", "git_pr_merge") and not state.plan_exists:
            return False, "D 级任务: 需先确认 Plan 再提交/推送"

    return True, ""


# ═══════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════

_current_state: MethodologyState | None = None


def get_methodology_state() -> MethodologyState:
    global _current_state
    if _current_state is None:
        _current_state = MethodologyState()
    return _current_state


def reset_methodology_state() -> None:
    global _current_state
    _current_state = MethodologyState()
