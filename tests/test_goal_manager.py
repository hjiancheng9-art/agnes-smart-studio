"""Tests for core/goal_manager.py — 目标管理模式"""

import pytest

from core.goal_manager import Goal, GoalManager


@pytest.fixture
def gm(tmp_path):
    """每个测试独立临时文件隔离"""
    return GoalManager(path=tmp_path / "goals.json")


class TestGoalCreate:
    """目标创建测试"""

    def test_create_basic(self, gm):
        goal = gm.create("重构用户模块", "所有测试通过")
        assert goal is not None
        assert goal.id is not None
        assert goal.intent == "重构用户模块"
        assert goal.finish_line == "所有测试通过"
        assert goal.status == "active"

    def test_create_with_boundaries(self, gm):
        goal = gm.create("优化查询", "耗时降50%", boundaries="不改表结构")
        assert goal.boundaries == "不改表结构"

    def test_create_unique_ids(self, gm):
        ids = {gm.create(f"任务{i}", f"完成{i}").id for i in range(10)}
        assert len(ids) == 10

    def test_create_default_max_steps(self, gm):
        goal = gm.create("任务", "完成")
        assert goal.max_steps == 20

    def test_create_custom_max_steps(self, gm):
        goal = gm.create("任务", "完成", max_steps=10)
        assert goal.max_steps == 10

    def test_create_empty_intent(self, gm):
        goal = gm.create("", "完成")
        assert goal is not None


class TestGoalGet:
    """获取目标测试"""

    def test_get_by_id(self, gm):
        created = gm.create("任务", "完成")
        fetched = gm.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_missing(self, gm):
        assert gm.get("no_such_id") is None

    def test_get_active(self, gm):
        gm.create("任务", "完成")
        active = gm.get()
        assert active is not None

    def test_get_active_none_when_empty(self, tmp_path):
        gm = GoalManager(path=tmp_path / "empty.json")
        assert gm.get() is None

    def test_get_returns_something_after_create(self, gm):
        g1 = gm.create("任务1", "完成1")
        g2 = gm.create("任务2", "完成2")
        active = gm.get()
        assert active is not None
        assert active.id in (g1.id, g2.id)


class TestStepRecording:
    """步骤记录测试"""

    def test_record_step(self, gm):
        goal = gm.create("任务", "完成")
        gm.record_step()
        assert gm.get(goal.id).steps_executed == 1

    def test_record_step_multiple(self, gm):
        goal = gm.create("任务", "完成")
        for _ in range(3):
            gm.record_step()
        assert gm.get(goal.id).steps_executed == 3

    def test_record_step_returns_bool(self, gm):
        gm.create("任务", "完成")
        assert isinstance(gm.record_step(), bool)


class TestToolCallRecording:
    """工具调用记录测试"""

    def test_record_tool_call(self, gm):
        goal = gm.create("任务", "完成")
        gm.record_tool_call()
        assert gm.get(goal.id).tool_calls_made == 1

    def test_record_tool_call_multiple(self, gm):
        goal = gm.create("任务", "完成")
        for _ in range(5):
            gm.record_tool_call()
        assert gm.get(goal.id).tool_calls_made == 5

    def test_record_tool_call_returns_bool(self, gm):
        gm.create("任务", "完成")
        assert isinstance(gm.record_tool_call(), bool)


class TestBudget:
    """预算控制测试"""

    def test_budget_not_exhausted_initially(self, gm):
        goal = gm.create("任务", "完成")
        assert not goal.is_budget_exhausted()

    def test_budget_exhausted_by_steps(self, gm):
        goal = gm.create("任务", "完成", max_steps=2)
        gm.record_step()
        gm.record_step()
        assert gm.get(goal.id).is_budget_exhausted()

    def test_budget_not_exhausted_below_limit(self, gm):
        goal = gm.create("任务", "完成", max_steps=5)
        gm.record_step()
        assert not gm.get(goal.id).is_budget_exhausted()


class TestSerialization:
    """序列化测试"""

    def test_to_dict(self, gm):
        goal = gm.create("任务", "完成")
        d = goal.to_dict()
        assert d["intent"] == "任务"
        assert d["finish_line"] == "完成"

    def test_from_dict(self):
        goal = Goal.from_dict(
            {
                "id": "test-001",
                "intent": "测试",
                "finish_line": "完成",
            }
        )
        assert goal.id == "test-001"
        assert goal.intent == "测试"
        assert goal.finish_line == "完成"
        assert goal.status == "active"


class TestIndependence:
    """多目标独立性测试"""

    def test_independent_step_counts(self, gm):
        g1 = gm.create("任务1", "完成1")
        gm.record_step()
        assert gm.get(g1.id).steps_executed == 1
        g2 = gm.create("任务2", "完成2")
        assert gm.get(g1.id).steps_executed == 1  # 不变
        assert gm.get(g2.id).steps_executed == 0


class TestLongText:
    """边界：长文本"""

    def test_long_intent(self, gm):
        goal = gm.create("A" * 10000, "完成")
        assert len(goal.intent) == 10000

    def test_long_finish_line(self, gm):
        goal = gm.create("任务", "B" * 10000)
        assert len(goal.finish_line) == 10000
