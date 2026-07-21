"""方法论引擎 — 将 METHODOLOGY.md / AGENTS.md / CLAUDE.md 硬约束嵌入 CRUX 运行时。

真源文件：
    METHODOLOGY.md  — 任务分级 A/B/C/D + 升级规则 + 7 步工作流 + 子 Agent 路由
    AGENTS.md       — 七大铁律 + 资源纪律 + 系统架构 + MCP 规范
    CLAUDE.md       — 模型路由 + 环境配置 + Agent 分派规则

当前注入方式（rules 文本 → system prompt）是"软建议"，LLM 可以不遵守。
本模块将方法论落地为引擎骨骼——禁区拦截、任务分级、升级规则、状态追踪、合规检查。

分层：
    L1 禁区（PROTECTED_FILES）        — 写操作硬拦截，无关 LLM
    L2 分级（TaskLevel + classify_task） — 自动判定 A/B/C/D，支持动态升级
    L3 守卫（methodology_pre_check）    — 工具调用前合规检查 + 子 Agent 路由约束
    L4 追踪（MethodologyState + /method）— 7 步工作流状态 + 可见性面板
    L5 升级（escalate_task）            — 按 METHODOLOGY.md §1.5 自动升级

用法：
    from core.methodology import MethodologyState, classify_task, escalate_task

    state = MethodologyState()
    state.classify(user_input, [])
    state.advance_workflow("plan_created")  # 7 步工作流推进
    new_level = escalate_task(state, reason="files>3")  # 升级规则
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

# 绝对禁止区间 — 仅锁方法论引擎自身（它崩了所有门禁全失效）
# 其他核心文件通过 rules/self-preservation.rules.md 软约束保护
PROTECTED_FILES: frozenset[str] = frozenset(
    {
        "core/methodology.py",
    }
)

import json
import logging
import subprocess as _sp

logger = logging.getLogger(__name__)

# 禁止区间的关键方法/属性
PROTECTED_SYMBOLS: dict[str, frozenset[str]] = {
    "core/config.py": frozenset({"SETTINGS", "save_global_auth"}),
    "core/exceptions.py": frozenset({"CruxError.__init__", "CruxError.__str__"}),
    "core/encoding.py": frozenset({"setup"}),
    "crux_studio.py": frozenset({"_SUBCOMMANDS", "main"}),
}

# 禁止添加未验证包的依赖文件
PROTECTED_DEP_FILES: frozenset[str] = frozenset({"requirements.txt", "pyproject.toml"})


_HOMOGLYPH_MAP = {
    0x0131: "i",
    0x0430: "a",
    0x0435: "e",
    0x043E: "o",
    0x0440: "p",
    0x0441: "c",
    0x0443: "y",
    0x0445: "x",
    0x0456: "i",
    0x04BB: "h",
}


def _sanitize_path(path: str) -> str:
    """Strip zero-width chars, null bytes, and homoglyph confusables."""
    import re

    path = path.replace("\x00", "")
    path = re.sub(r"[\u200b-\u200f\u2028-\u202e\ufeff]", "", path)
    return path.translate(_HOMOGLYPH_MAP)


def is_protected_file(path: str) -> bool:
    """Path protection with Unicode + case normalization."""
    import os

    s = _sanitize_path(path)
    n = os.path.normpath(s).replace("\\", "/").lower()
    return any(n.endswith(os.path.normpath(_sanitize_path(p)).replace("\\", "/").lower()) for p in PROTECTED_FILES)


def is_protected_dep_file(path: str) -> bool:
    """判断是否为保护区内的依赖文件。"""
    return Path(path).name in PROTECTED_DEP_FILES


# ═══════════════════════════════════════════════════════════════════
# L2 — 任务分级
# ═══════════════════════════════════════════════════════════════════


class TaskLevel(Enum):
    """方法论第 0 章 A/B/C/D 任务分级。

    A 微任务  — 单行修复/typo/小调整，跳过 Plan/TDD/Worktree，必须看 diff
    B 普通开发 — 简短计划 + 验证，Bug 修复必须遵循 检查/优化闭环 (METHODOLOGY.md §5)
    C 复杂工程 — Plan + 分阶段实现 + 测试 + Review，3+ 文件或架构变动
    D 高风险   — 必须 Spec + 风险评估 + 人工确认 + 隔离 + CI
    """

    A = "micro"
    B = "normal"
    C = "complex"
    D = "critical"


def classify_task(intent: str, files_touched: list[str] | None = None) -> TaskLevel:
    """Classify task into A/B/C/D using unified keyword analysis.

    Delegates to task_complexity.py's rich keyword engine (6-tier patterns
    in both Chinese and English), then maps to the A/B/C/D system.
    Falls back to execution_policy routing if task_complexity is unavailable.
    """
    # ── Primary: rich keyword classification ──
    try:
        from core.task_complexity import TaskComplexity
        from core.task_complexity import classify_task as _tc

        result = _tc(intent)
        # Map 5-tier TaskComplexity → 4-tier TaskLevel
        _map = {
            TaskComplexity.TRIVIAL: TaskLevel.A,
            TaskComplexity.SIMPLE: TaskLevel.A,
            TaskComplexity.MODERATE: TaskLevel.B,
            TaskComplexity.COMPLEX: TaskLevel.C,
            TaskComplexity.CRITICAL: TaskLevel.D,
        }
        return _map.get(result.complexity, TaskLevel.B)
    except ImportError:
        pass

    # ── Fallback: execution_policy routing ──
    try:
        from core.execution_policy import ExecutionMode, choose_policy

        policy = choose_policy(intent)
        if policy.mode == ExecutionMode.SWARM:
            return TaskLevel.D
        elif policy.mode == ExecutionMode.ORCHESTRATE:
            return TaskLevel.C
        return TaskLevel.B if len(intent) > 50 else TaskLevel.A
    except ImportError:
        return TaskLevel.A


# ═══════════════════════════════════════════════════════════════════
# L3 — 工具调用前合规检查
# ═══════════════════════════════════════════════════════════════════


@dataclass
class MethodologyState:
    """当前任务的方法论遵守状态。追踪从任务开始到结束的合规性。

    7 步工作流 (METHODOLOGY.md §3):
        1.明确目标 → 2.收集上下文 → 3.判断级别 → 4.写Plan → 5.补测试 → 6.验证diff → 7.清理资源
    """

    task_level: TaskLevel = TaskLevel.A
    plan_exists: bool = False
    test_baseline_recorded: bool = False
    worktree_created: bool = False
    files_touched: list[str] = field(default_factory=list)
    tdd_phase: str = ""  # red | green | refactor
    step_count: int = 0
    tool_call_count: int = 0

    # 7 步工作流状态 (METHODOLOGY.md §3)
    workflow_step: int = 1  # 1-7, 0=未开始

    # ── Persistence ──

    def to_dict(self) -> dict:
        return {
            "task_level": self.task_level.value,
            "plan_exists": self.plan_exists,
            "test_baseline_recorded": self.test_baseline_recorded,
            "worktree_created": self.worktree_created,
            "files_touched": list(self.files_touched),
            # tdd_phase intentionally NOT persisted — TDD sessions are ephemeral
            # and should not survive restarts (would block all writes)
            "step_count": self.step_count,
            "tool_call_count": self.tool_call_count,
            "workflow_step": self.workflow_step,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MethodologyState:
        return cls(
            task_level=TaskLevel(data.get("task_level", "micro")),
            plan_exists=data.get("plan_exists", False),
            test_baseline_recorded=data.get("test_baseline_recorded", False),
            worktree_created=data.get("worktree_created", False),
            files_touched=data.get("files_touched", []),
            tdd_phase="",  # NEVER restore TDD phase — ephemeral by design
            step_count=data.get("step_count", 0),
            tool_call_count=data.get("tool_call_count", 0),
            workflow_step=data.get("workflow_step", 1),
        )

    workflow_steps: ClassVar[dict[int, str]] = {
        1: "明确目标",
        2: "收集上下文",
        3: "判断任务级别",
        4: "写 Plan",
        5: "补测试",
        6: "验证 + diff 审查",
        7: "清理资源",
    }

    # 任务升级历史 (METHODOLOGY.md §1.5)
    escalation_history: list[tuple[str, str]] = field(default_factory=list)  # [(from_level, reason)]

    # ── 任务等级要求 (METHODOLOGY.md §3) ──

    @property
    def requires_plan(self) -> bool:
        """C/D 级需要先写 Plan。"""
        return self.task_level in (TaskLevel.C, TaskLevel.D)

    @property
    def requires_test_baseline(self) -> bool:
        """C/D 级必须先记录测试基线。"""
        return self.task_level in (TaskLevel.C, TaskLevel.D)

    @property
    def requires_worktree(self) -> bool:
        """D 级必须在隔离 worktree 中操作。"""
        return self.task_level == TaskLevel.D

    @property
    def test_requirement(self) -> str:
        """返回当前等级的最低测试要求 (METHODOLOGY.md §3 表格)。"""
        reqs = {
            TaskLevel.A: "跑相关 smoke / typecheck 即可",
            TaskLevel.B: "行为变更补测试证据；Bug 修复补回归测试",
            TaskLevel.C: "完整 TDD: 失败测试 → 最小实现 → 重构",
            TaskLevel.D: "TDD + 安全审查 + 人工 Review",
        }
        return reqs.get(self.task_level, "未知")

    # ── 方法 ──

    def classify(self, intent: str, files: list[str]) -> None:
        """分析意图并设定任务等级，推进到判断阶段。"""
        self.task_level = classify_task(intent, files)
        self.workflow_step = 3  # 进入"判断级别"

    def record_tool(self, tool_name: str) -> None:
        """记录本次会话中使用的工具名。"""
        self.tool_call_count += 1

    def record_step(self) -> None:
        """递增步骤计数器。"""
        self.step_count += 1

    def advance_workflow(self, event: str) -> None:
        """推进 7 步工作流 (METHODOLOGY.md §3).

        event: 'context_collected' | 'plan_created' | 'test_written' | 'verified' | 'cleaned'
        """
        transitions = {
            "context_collected": 2,
            "level_classified": 3,  # set by classify() directly
            "plan_created": 4,
            "test_written": 5,
            "verified": 6,
            "cleaned": 7,
        }
        target = transitions.get(event)
        if target is not None and target > self.workflow_step:
            self.workflow_step = target

    def escalate(self, reason: str) -> TaskLevel:
        """按 METHODOLOGY.md §1.5 升级任务等级。返回新等级。"""
        new_level = escalate_task(self.task_level, reason)
        if new_level != self.task_level:
            self.escalation_history.append((self.task_level.name, reason))
            self.task_level = new_level
        return new_level

    # ── 状态标记方法（供 plan_mode / verification / git_worktree 等调用）──

    def mark_plan_confirmed(self) -> None:
        """标记 Plan 已确认（PlanModeManager.exit(approved=True) 或 /plan 审批通过时调用）。"""
        self.plan_exists = True
        self.advance_workflow("plan_created")

    def mark_test_baseline_recorded(self) -> None:
        """标记测试基线已记录（验证通过或测试基线建立时调用）。"""
        self.test_baseline_recorded = True

    def mark_worktree_created(self) -> None:
        """标记隔离 Worktree 已创建（git worktree add 成功时调用）。"""
        self.worktree_created = True

    def summary(self) -> str:
        """生成 /method 展示的摘要。"""
        level_label = {TaskLevel.A: "A 微任务", TaskLevel.B: "B 普通", TaskLevel.C: "C 复杂", TaskLevel.D: "D 高风险"}
        parts = [f"任务等级: {level_label.get(self.task_level, '?')}"]
        # 7 步工作流
        step_name = self.workflow_steps.get(self.workflow_step, "?")
        parts.append(f"步骤 {self.workflow_step}/7 {step_name}")
        if self.requires_plan:
            parts.append("Plan ✓" if self.plan_exists else "Plan ✗")
        if self.requires_test_baseline:
            parts.append("基线 ✓" if self.test_baseline_recorded else "基线 ✗")
        if self.requires_worktree:
            parts.append("Worktree ✓" if self.worktree_created else "Worktree ✗")
        parts.append(f"TDD:{self.tdd_phase or '-'}")
        parts.append(f"工具:{self.tool_call_count}")
        # 升级历史
        if self.escalation_history:
            last = self.escalation_history[-1]
            parts.append(f"↑{last[0]}→{self.task_level.name}({last[1]})")
        return " | ".join(parts)


def escalate_task(level: TaskLevel, reason: str) -> TaskLevel:
    """按 METHODOLOGY.md §1.5 升级规则返回新任务等级。

    规则（优先级递减）：
        → D: auth/payment/db/deploy/凭证/密码/token 关键词
        → D: 原 C 级 + 影响其他模块
        → C: 文件超3个 / 公共API修改 / 新增依赖 / 测试连续失败 / 子Agent失败
        → B: A 级 + 文件超1个
    """
    reason_lower = reason.lower()

    # → D 级触发器
    d_immediate = {"auth", "payment", "db", "deploy", "database", "凭证", "密码", "token", "secret"}
    if any(t in reason_lower for t in d_immediate):
        return TaskLevel.D
    if level == TaskLevel.C and "影响" in reason:
        return TaskLevel.D

    # → C 级触发器
    if level in (TaskLevel.A, TaskLevel.B):
        c_triggers = {
            "files>3",
            ">3",
            "超过3",
            "public_api",
            "api变动",
            "新增依赖",
            "依赖",
            "test_failure",
            "失败",
            "子agent",
        }
        if any(t in reason_lower for t in c_triggers):
            return TaskLevel.C

    # → B 级触发器
    if level == TaskLevel.A and ("files>1" in reason_lower or ">1" in reason_lower):
        return TaskLevel.B

    return level  # 无需升级


# ═══════════════════════════════════════════════════════════════════
# 子 Agent 路由约束 (METHODOLOGY.md §2 + CLAUDE.md)
# ═══════════════════════════════════════════════════════════════════

SUB_AGENT_CONSTRAINTS: dict[str, str] = {
    "architecture": "主对话(pro) — 不派 flash 做架构决策",
    "grep": "Explore Agent(flash) — 不派 pro 做 grep",
    "multi_file_refactor": "主对话(pro) — 架构设计、多文件重构走 pro",
    "simple_edit": "general-purpose(flash) — 简单修改不派 Pro",
    "complex_debug": "主对话(pro) — 复杂调试根因分析",
    "no_retry_same": "子 Agent 失败不重试同一类型，换通路",
    "parallel_independent": "独立子任务一次并行发出，不串行等",
}


def check_agent_route(task_type: str, agent_model: str) -> tuple[bool, str]:
    """检查子 Agent 路由是否违反方法论约束。"""
    if task_type in ("architecture", "multi_file_refactor", "complex_debug") and "flash" in agent_model:
        return False, f"禁止: {SUB_AGENT_CONSTRAINTS.get(task_type, 'flash 不应用于此任务')}"
    return True, ""


# ═══════════════════════════════════════════════════════════════════
# 工具调用前合规检查
# ═══════════════════════════════════════════════════════════════════


def _get_active_tdd_phase() -> str:
    """查询当前活跃 TDD 会话的阶段（red/green/refactor），无活跃会话返回空字符串。"""
    try:
        import json
        from pathlib import Path

        tdd_dir = Path(__file__).resolve().parent.parent / "output" / "tdd"
        if not tdd_dir.exists():
            return ""
        sessions = sorted(tdd_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not sessions:
            return ""
        # Skip completed sessions — only active (unfinished) sessions enforce the gate
        for session_path in sessions:
            try:
                data = json.loads(session_path.read_text("utf-8"))
                if not data.get("completed", False):
                    return data.get("phase", "")
            except (json.JSONDecodeError, KeyError):
                continue
        return ""
    except (OSError, json.JSONDecodeError, KeyError):
        return ""


def _is_test_file(file_path: str) -> bool:
    """判断文件路径是否为测试文件。"""
    import os

    fname = os.path.basename(file_path).lower()
    return fname.startswith("test_") or fname.endswith("_test.py") or "tests" in file_path.replace("\\", "/").split("/")


def methodology_pre_check(tool_name: str, args: dict, state: MethodologyState | None = None) -> tuple[bool, str]:
    """工具调用前的方法论合规检查。

    Returns:
        (allowed, reason) — allowed=False 时 reason 说明拦截原因。
    """
    # ── L1 禁区 — 硬拦截（无关任务等级）──
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, ValueError):
            args = {}
    if not isinstance(args, dict):
        args = {}
    file_path = args.get("path") or args.get("file_path") or args.get("target") or ""
    if (
        file_path
        and is_protected_file(file_path)
        and tool_name in ("write_file", "edit_file", "patch_file", "safe_rewrite_file", "delete_files")
    ):
        return False, f"禁区文件不可修改: {file_path}"

    # 依赖文件添加受保护
    if (tool_name == "pip_install" and args.get("package")) or (
        is_protected_dep_file(file_path) and tool_name in ("write_file", "edit_file")
    ):
        return False, f"依赖文件 {file_path} 不可直接修改（需人工审核新包）"

    # ── TDD 门控: 红灯阶段禁止写实现代码 ──
    if tool_name in ("write_file", "edit_file", "patch_file", "safe_rewrite_file"):
        tdd_phase = _get_active_tdd_phase()
        if tdd_phase == "red" and not _is_test_file(file_path):
            return False, (
                "TDD 红灯阶段: 禁止写实现代码。请先写测试文件（*test*.py），"
                "运行 tdd_run_tests 确认失败（RED），再写实现。"
            )

    # ── L2/L3 — 任务等级守卫 ──
    if state is None:
        return True, ""

    level = state.task_level

    # C/D 级: 写操作 + git 操作必须确认 Plan
    if level in (TaskLevel.C, TaskLevel.D):
        is_write = tool_name in (
            "write_file",
            "edit_file",
            "patch_file",
            "safe_rewrite_file",
            "delete_files",
            "git_add_commit",
            "git_push",
            "git_pr_create",
            "git_pr_merge",
            "git_tag",
        )
        if is_write and not state.plan_exists:
            level_name = "C" if level == TaskLevel.C else "D"
            return False, f"{level_name} 级任务: 需先确认 Plan 再执行 {tool_name}（使用 /plan 或规划模式）"

    # D 级额外约束: 测试基线 + Worktree
    if level == TaskLevel.D:
        if (
            tool_name in ("git_add_commit", "git_push", "git_pr_create", "git_pr_merge")
            and not state.test_baseline_recorded
        ):
            return False, "D 级任务: 需先记录测试基线再提交/推送（使用 /done 验证）"
        if tool_name.startswith("git_") and not state.worktree_created:
            return False, "D 级任务: 需在隔离 Worktree 中操作（使用 git worktree add）"

    return True, ""


# ═══════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════

_current_state: MethodologyState | None = None


def get_methodology_state() -> MethodologyState:
    """返回全局方法论状态单例。第一次调用时自动创建。"""
    global _current_state
    if _current_state is None:
        _current_state = MethodologyState()
    return _current_state


def reset_methodology_state() -> None:
    """重置全局方法论状态（新会话时调用，丢弃旧状态）。"""
    global _current_state
    _current_state = MethodologyState()


def save_methodology_state(filepath: str | None = None) -> bool:
    """Save methodology state to disk for session persistence.

    Args:
        filepath: Target path. Defaults to output/sessions/methodology.json.
    Returns:
        True if saved successfully.
    """
    import json
    from pathlib import Path

    try:
        if filepath is None:
            root = Path(__file__).resolve().parent.parent
            filepath = str(root / "output" / "sessions" / "methodology.json")
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        state = get_methodology_state()
        p.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except (OSError, ValueError) as e:
        logging.getLogger(__name__).debug("save failed: %s", e)
        return False


def restore_methodology_state(filepath: str | None = None) -> bool:
    """Restore methodology state from disk.

    Args:
        filepath: Source path. Defaults to output/sessions/methodology.json.
    Returns:
        True if restored successfully, False if file not found or corrupt.
    """
    import json
    from pathlib import Path

    try:
        if filepath is None:
            root = Path(__file__).resolve().parent.parent
            filepath = str(root / "output" / "sessions" / "methodology.json")
        p = Path(filepath)
        if not p.exists():
            return False
        data = json.loads(p.read_text(encoding="utf-8"))
        global _current_state
        restored = MethodologyState.from_dict(data)
        _current_state = restored
        logging.getLogger(__name__).info(
            "Restored methodology: level=%s step=%d/%d",
            restored.task_level.value,
            restored.workflow_step,
            7,
        )
        return True
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as e:
        logging.getLogger(__name__).debug("restore failed: %s", e)
        return False


# ═══════════════════════════════════════════════════════════════════
# 红旗警示 (AGENTS.md — 七大铁律)
# ═══════════════════════════════════════════════════════════════════

RED_FLAGS: dict[str, str] = {
    # Chinese — overconfidence
    "这很简单": "红旗: '这很简单' → 也需要验证",
    "很简单": "红旗: '很简单' → 也需要验证",
    "应该好了": "红旗: '应该好了' → 禁止主观判断，跑测试确认",
    "应该没问题": "红旗: '应该没问题' → 跑验证命令",
    "看起来可以": "红旗: '看起来可以' → 眼见为实，跑测试",
    "理论上没问题": "红旗: '理论上没问题' → 理论≠证据，跑命令",
    # Chinese — scope creep
    "我先改一下": "红旗: '我先改一下' → 先收集上下文再改",
    "顺便重构": "红旗: '顺便重构' → 不扩大范围",
    "顺便改": "红旗: '顺便改' → 不扩大范围",
    "顺手": "红旗: '顺手' → 不扩大范围，专注当前任务",
    # Chinese — blind trust
    "子代理说完成了": "红旗: '子代理说完成了' → 报告不是证据，自己验证",
    "不需要测试": "红旗: '不需要测试' → D任务必须验证",
    "跳过测试": "红旗: '跳过测试' → 必须验证后确认",
    # Chinese — hallucinations
    "配置已经改好了": "红旗: '配置已经改好了' → 确认是否真的执行了修改",
    "已经完成了": "红旗: '已经完成了' → 确认实际产物",
    # English
    "looks good": "Red flag: 'looks good' → verify with evidence",
    "should be fine": "Red flag: 'should be fine' → run tests",
    "theoretically": "Red flag: 'theoretically' → theory ≠ evidence",
    "probably works": "Red flag: 'probably works' → verify",
    "no need to test": "Red flag: 'no need to test' → always verify",
    "trust me": "Red flag: 'trust me' → verify independently",
    # Technical anti-patterns
    "-n auto": "红旗: 'pytest -n auto' → 全量测试必须限并发(-n 4)，禁止 -n auto",
    "git push -f": "红旗: 'git push -f' → 禁止强制推送",
    "rm -rf": "红旗: 'rm -rf' → 禁止递归删除",
    "DROP TABLE": "红旗: 'DROP TABLE' → 禁止删表操作",
}


def detect_red_flags(text: str) -> list[str]:
    """检查文本中是否含反模式关键词（METHODOLOGY.md §8）。

    返回匹配项清单，空列表 = 无风险。
    """
    found = []
    lower = text.lower()
    for pattern, warning in RED_FLAGS.items():
        if pattern.lower() in lower:
            found.append(warning)
    return found


# ═══════════════════════════════════════════════════════════════════
# 子 Agent 失败路由 (METHODOLOGY.md §2.1)
# ═══════════════════════════════════════════════════════════════════

SUB_AGENT_FAILURE_MAP: dict[str, tuple[str, str]] = {
    "context length": ("上下文不足", "补上下文后重试"),
    "not enough context": ("上下文不足", "补上下文后重试"),
    "permission denied": ("权限不足", "缩小范围，换只读Agent"),
    "not found": ("上下文不足", "补文件路径后重试"),
    "no such file": ("上下文不足", "补文件路径后重试"),
    "import error": ("上下文不足", "补模块路径后重试"),
    "module not found": ("上下文不足", "补模块路径后重试"),
    "test fail": ("测试失败", "派debugger分析失败原因"),
    "assertion error": ("测试失败", "派debugger分析失败原因"),
    "timeout": ("工具失败", "换等效工具或减小范围"),
    "connection": ("工具失败", "检查网络后换等效工具"),
    "rate limit": ("工具失败", "等待冷却后重试"),
}

MAX_CONSECUTIVE_FAILURES = 2


def classify_failure(error_text: str) -> tuple[str, str]:
    """按 METHODOLOGY.md §2.1 对子 Agent 错误进行分类。

    Returns:
        (failure_type, recommended_action)
    """
    lower = error_text.lower()
    for pattern, (ftype, action) in SUB_AGENT_FAILURE_MAP.items():
        if pattern.lower() in lower:
            return ftype, action
    return "未知", "主对话分析错误后重试"


# ═══════════════════════════════════════════════════════════════════
# /done 命令 — 完成前验证 (AGENTS.md)
# ═══════════════════════════════════════════════════════════════════


VERIFICATION_CHECKS: dict[str, str] = {
    "pytest": "python -m pytest tests/ --tb=short -q",
    "ruff": "python -m ruff check core/ ui/ engines/ --config=pyproject.toml",
    "pyright": "python -m pyright",
    "git_diff": "git diff --stat HEAD",
    "residue": (
        'python -c "import subprocess,sys; '
        'cmd=["tasklist","/FI","IMAGENAME eq python.exe"] if sys.platform=="win32" '
        'else ["pgrep","-a","python"]; '
        'r=subprocess.run(cmd,capture_output=True,text=True,timeout=5,shell=sys.platform=="win32"); '
        'lines=[l for l in r.stdout.split(chr(10)) if l.strip() and "grep" not in l]; '
        'print(f"{len(lines)} python processes") if lines else print("clean")"'
    ),
}

DONE_TRIGGERS: frozenset[str] = frozenset(
    {
        "完成了",
        "done",
        "完成!",
        "finished",
        "搞定",
        "all done",
        "task complete",
        "任务完成",
        "已修复",
    }
)


def run_verification() -> dict[str, tuple[bool, str]]:
    """执行 METHODOLOGY.md §5.3 定义的验证检查清单。

    Returns:
        {check_name: (passed, output)}——全部通过则所有值为 (True, "")
    副作用: 全部通过时自动标记 test_baseline_recorded。
    """
    results = {}
    root = Path(__file__).resolve().parent.parent
    for name, cmd in VERIFICATION_CHECKS.items():
        try:
            r = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=120, cwd=str(root))  # nosec B602
            ok = r.returncode == 0
            summary = (r.stdout + r.stderr)[:300].strip() or "(no output)"
            results[name] = (ok, summary)
        except _sp.TimeoutExpired:
            results[name] = (False, "超时")
        except Exception as e:
            results[name] = (False, str(e))

    # 全部通过 → 自动标记测试基线
    if all(v[0] for v in results.values()):
        try:
            _current = get_methodology_state()
            _current.mark_test_baseline_recorded()
        except Exception:
            logger.debug("Exception in methodology", exc_info=True)

    return results
