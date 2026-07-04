"""Plan Mode — 规划审批模式（先计划，后执行）。

移植自 Kimi Code CLI 的 EnterPlanMode / ExitPlanMode 理念：
  1. enter_plan_mode(goal) → 限制为只读工具，调用 SmartPlanner 生成方案
  2. 用户审批方案（可选多方案对比）
  3. exit_plan_mode(approved=True) → 恢复完整工具集，执行计划

状态机:
  idle → planning → waiting_approval → executing / rejected
"""

from __future__ import annotations

import enum
import json
import threading
from dataclasses import asdict, dataclass, field
from typing import Any


class PlanStatus(enum.Enum):
    IDLE = "idle"
    PLANNING = "planning"          # 正在生成计划
    WAITING_APPROVAL = "waiting_approval"  # 等待用户审批
    APPROVED = "approved"          # 审批通过，进入执行
    REJECTED = "rejected"          # 审批拒绝
    EXECUTING = "executing"        # 正在执行


@dataclass
class PlanOption:
    """单个方案选项。"""
    label: str                    # 简短标签（1-8 词）
    description: str = ""          # 方案描述与权衡
    steps: list[dict] = field(default_factory=list)  # 步骤列表
    is_recommended: bool = False   # 是否推荐

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "description": self.description,
            "steps": self.steps,
            "is_recommended": self.is_recommended,
        }


@dataclass
class Plan:
    """一份完整的执行计划。"""

    id: str
    goal: str
    status: PlanStatus = PlanStatus.IDLE
    options: list[PlanOption] = field(default_factory=list)
    selected_option: int = -1  # 用户选择的方案索引
    created_at: str = ""
    approved_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value,
            "options": [o.to_dict() for o in self.options],
            "selected_option": self.selected_option,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
        }


class PlanModeManager:
    """管理规划模式生命周期。

    单例，协调只读工具切换 + 方案审批 + 执行衔接。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_plan: Plan | None = None
        self._in_plan_mode: bool = False
        # 原始工具集引用（由 chat.py 注入）
        self._original_tools: Any = None
        # 工具恢复回调: (readonly_tools: list[str]) -> None
        self._on_enter_readonly: Any = None
        self._on_exit_readonly: Any = None

    @property
    def in_plan_mode(self) -> bool:
        return self._in_plan_mode

    @property
    def current_plan(self) -> Plan | None:
        return self._current_plan

    # ── 进入规划模式 ──

    def enter(self, goal: str) -> Plan:
        """进入规划模式。

        Args:
            goal: 用户目标描述

        Returns:
            生成的 Plan 对象（含方案列表）
        """
        import datetime
        import uuid

        from core.constraints import READONLY_TOOLS

        with self._lock:
            plan = Plan(
                id=uuid.uuid4().hex[:8],
                goal=goal,
                status=PlanStatus.PLANNING,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            self._current_plan = plan
            self._in_plan_mode = True

            # 切换到只读工具集
            if self._on_enter_readonly:
                self._on_enter_readonly(READONLY_TOOLS)

        # 生成方案
        plan.options = self._generate_plan_options(goal)
        with self._lock:
            plan.status = PlanStatus.WAITING_APPROVAL

        return plan

    # ── 退出规划模式 ──

    def exit(self, approved: bool = True, selected_option: int = 0) -> Plan | None:
        """退出规划模式。

        Args:
            approved: 是否审批通过
            selected_option: 用户选择的方案索引（0-based）

        Returns:
            更新后的 Plan，或 None（拒绝时）
        """
        import datetime

        with self._lock:
            plan = self._current_plan
            if plan is None:
                return None

            if approved:
                plan.status = PlanStatus.APPROVED
                plan.selected_option = selected_option
                plan.approved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                self._in_plan_mode = False
            else:
                plan.status = PlanStatus.REJECTED
                self._in_plan_mode = False
                self._current_plan = None

            # 恢复完整工具集
            if self._on_exit_readonly:
                self._on_exit_readonly()

            return plan

    # ── 方案生成 ──

    def _generate_plan_options(self, goal: str) -> list[PlanOption]:
        """生成执行方案。

        尝试用 SmartPlanner 生成多个方案；失败时退回 quick_plan。
        """
        try:
            from core.executor import quick_plan, smart_plan

            # 尝试智能规划
            try:
                from core.tools import get_registry
                registry = get_registry()
                tool_names = list(registry._executors.keys())
                steps = smart_plan(goal, context="", tool_names=tool_names)
            except (ImportError, RuntimeError, ValueError):
                steps = quick_plan(goal)

            # Handle both Task object and list
            if hasattr(steps, 'steps'):
                step_list = steps.steps
                steps_count = len(step_list)
                steps_serialized = [asdict(s) if hasattr(s, '__dataclass_fields__') else s for s in step_list]
            elif isinstance(steps, list):
                step_list = steps
                steps_count = len(step_list) if step_list else 1
                steps_serialized = [asdict(s) if hasattr(s, '__dataclass_fields__') else s for s in step_list]
            else:
                steps_count = 1
                steps_serialized = [{"tool": "execute_plan_tool", "args": {"goal": goal}}]

            if not steps_serialized:
                return [PlanOption(
                    label="单步执行",
                    description="直接执行目标",
                    steps=[{"tool": "execute_plan_tool", "args": {"goal": goal}}],
                    is_recommended=True,
                )]

            # 构建推荐方案
            recommended = PlanOption(
                label="推荐方案",
                description=f"自动拆解为 {steps_count} 个步骤",
                steps=steps_serialized,  # pyright: ignore[reportArgumentType]
                is_recommended=True,
            )

            return [recommended]

        except (ImportError, RuntimeError, ValueError):
            return [PlanOption(
                label="直接执行",
                description="无法生成规划方案，直接执行目标",
                steps=[{"tool": "execute_plan_tool", "args": {"goal": goal}}],
                is_recommended=True,
            )]

    # ── 回调注入 ──

    def set_tool_callbacks(self, on_enter, on_exit) -> None:
        """注入工具切换回调（由 chat.py 调用）。

        Args:
            on_enter(readonly_tools): 切换到只读工具集
            on_exit(): 恢复完整工具集
        """
        self._on_enter_readonly = on_enter
        self._on_exit_readonly = on_exit

    def is_tool_allowed(self, tool_name: str) -> bool:
        """检查工具在规划模式下是否允许执行。"""
        if not self._in_plan_mode:
            return True
        from core.constraints import READONLY_TOOLS
        return tool_name in READONLY_TOOLS

    def get_status(self) -> dict:
        """获取当前规划模式状态。"""
        with self._lock:
            return {
                "in_plan_mode": self._in_plan_mode,
                "plan": self._current_plan.to_dict() if self._current_plan else None,
            }


# ── Module-level singleton ──

_plan_mode_manager: PlanModeManager | None = None
_pm_lock = threading.Lock()


def get_plan_mode_manager() -> PlanModeManager:
    global _plan_mode_manager
    if _plan_mode_manager is None:
        with _pm_lock:
            if _plan_mode_manager is None:
                _plan_mode_manager = PlanModeManager()
    return _plan_mode_manager


def reset_plan_mode_manager() -> None:
    global _plan_mode_manager
    _plan_mode_manager = None


# ── Tool definitions ──

PLAN_MODE_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "enter_plan_mode",
            "description": (
                "进入规划模式。系统将限制为只读工具，为给定目标生成执行方案。"
                "方案生成后等待用户审批，审批通过后才可执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "需要规划的目标描述",
                    },
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exit_plan_mode",
            "description": (
                "退出规划模式。approved=true 表示审批通过，将执行选中的方案；"
                "approved=false 表示拒绝方案。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "approved": {
                        "type": "boolean",
                        "description": "是否审批通过，默认 true",
                    },
                    "selected_option": {
                        "type": "integer",
                        "description": "选择的方案索引（0-based），默认 0",
                    },
                },
                "required": ["approved"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_status",
            "description": "查看当前规划模式状态，包括方案列表和审批状态。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ── Executor functions ──


def _exec_enter_plan_mode(**kwargs) -> str:
    pm = get_plan_mode_manager()
    goal = kwargs["goal"]
    plan = pm.enter(goal)
    return json.dumps(
        {
            "message": f"已进入规划模式。生成了 {len(plan.options)} 个方案，等待审批。",
            "plan": plan.to_dict(),
        },
        ensure_ascii=False,
        indent=2,
    )


def _exec_exit_plan_mode(**kwargs) -> str:
    pm = get_plan_mode_manager()
    approved = kwargs.get("approved", True)
    selected = kwargs.get("selected_option", 0)

    plan = pm.exit(approved=approved, selected_option=selected)
    if plan is None:
        return "当前未处于规划模式。"

    if approved:
        option = plan.options[selected] if selected < len(plan.options) else None
        steps_count = len(option.steps) if option else 0
        return json.dumps(
            {
                "message": f"方案已审批通过，进入执行阶段（{steps_count} 个步骤）。",
                "plan": plan.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )
    return "方案已拒绝。规划模式已退出。"


def _exec_plan_status(**kwargs) -> str:
    pm = get_plan_mode_manager()
    return json.dumps(pm.get_status(), ensure_ascii=False, indent=2)


PLAN_MODE_EXECUTOR_MAP = {
    "enter_plan_mode": _exec_enter_plan_mode,
    "exit_plan_mode": _exec_exit_plan_mode,
    "plan_status": _exec_plan_status,
}
