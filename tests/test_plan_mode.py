"""Tests for core/plan_mode.py — 规划审批模式"""

import pytest

from core.plan_mode import Plan, PlanModeManager, PlanOption, PlanStatus


@pytest.fixture
def pmm():
    """创建不带 LLM 调用的 PlanModeManager（仅测试数据结构部分）"""
    return PlanModeManager()


class TestPlanModeManagerIdle:
    """空闲状态测试（不触发 LLM）"""

    def test_initially_idle(self, pmm):
        assert not pmm.in_plan_mode
        assert pmm.get_status() == PlanStatus.IDLE

    def test_current_plan_none_when_idle(self, pmm):
        assert pmm.current_plan is None

    def test_get_status_idle(self, pmm):
        assert pmm.get_status() == PlanStatus.IDLE

    def test_tool_all_allowed_when_idle(self, pmm):
        for tool in ["write_file", "run_bash", "edit_file", "read_file"]:
            assert pmm.is_tool_allowed(tool)


class TestPlanModeManagerEnter:
    """enter 测试（会调用 SmartPlanner，约 5s）"""

    def test_enter_sets_in_plan_mode(self, pmm):
        pmm.enter("简单测试")
        assert pmm.in_plan_mode

    def test_enter_returns_dict(self, pmm):
        result = pmm.enter("任务")
        assert isinstance(result, dict)
        assert "plan" in result

    def test_enter_plan_has_goal(self, pmm):
        pmm.enter("重构认证模块")
        plan = pmm.current_plan
        assert plan is not None
        assert plan.goal == "重构认证模块"

    def test_enter_plan_has_id(self, pmm):
        pmm.enter("任务")
        plan = pmm.current_plan
        assert plan.id is not None

    def test_enter_plan_has_options(self, pmm):
        pmm.enter("任务")
        plan = pmm.current_plan
        assert plan.options is not None
        assert len(plan.options) > 0

    def test_enter_status_waiting_approval(self, pmm):
        pmm.enter("任务")
        status = pmm.get_status()
        assert status in (PlanStatus.WAITING_APPROVAL, PlanStatus.PLANNING)

    def test_enter_empty_goal(self, pmm):
        pmm.enter("")
        assert pmm.in_plan_mode

    def test_enter_twice(self, pmm):
        pmm.enter("任务A")
        pmm.enter("任务B")
        plan = pmm.current_plan
        assert plan.goal == "任务B"


class TestPlanModeManagerExit:
    """exit 测试"""

    def test_exit_clears_plan_mode(self, pmm):
        pmm.enter("任务")
        pmm.exit(approved=True)
        assert not pmm.in_plan_mode

    def test_exit_twice_no_crash(self, pmm):
        pmm.enter("任务")
        pmm.exit(approved=True)
        pmm.exit(approved=True)
        assert not pmm.in_plan_mode

    def test_exit_rejected(self, pmm):
        pmm.enter("任务")
        pmm.exit(approved=False)
        assert not pmm.in_plan_mode


class TestPlanModeReadonly:
    """只读限制测试"""

    def test_read_tools_allowed(self, pmm):
        pmm.enter("只读检查")
        for tool in ["read_file", "search_files", "glob_files"]:
            assert pmm.is_tool_allowed(tool)

    def test_write_tools_blocked(self, pmm):
        pmm.enter("只读检查")
        for tool in ["write_file", "run_bash", "edit_file"]:
            assert not pmm.is_tool_allowed(tool)


class TestPlanDataClasses:
    """数据类测试（不触发 LLM）"""

    def test_plan_creation(self):
        p = Plan(id="p-001", goal="测试", status=PlanStatus.IDLE, options=[])
        assert p.id == "p-001"
        assert p.goal == "测试"

    def test_plan_option_creation(self):
        opt = PlanOption(
            label="方案A",
            description="使用缓存优化",
            steps=[],
            is_recommended=True,
        )
        assert opt.is_recommended is True

    def test_plan_option_default(self):
        opt = PlanOption(label="方案B", description="测试", steps=[])
        assert opt.is_recommended is False


class TestPlanStatusEnum:
    """状态枚举测试"""

    def test_all_statuses(self):
        statuses = {
            PlanStatus.IDLE,
            PlanStatus.PLANNING,
            PlanStatus.WAITING_APPROVAL,
            PlanStatus.APPROVED,
            PlanStatus.REJECTED,
            PlanStatus.EXECUTING,
        }
        assert len(statuses) == 6

    def test_values(self):
        assert PlanStatus.IDLE.value == "idle"
        assert PlanStatus.APPROVED.value == "approved"
