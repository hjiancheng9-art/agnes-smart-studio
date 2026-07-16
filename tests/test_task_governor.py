"""Tests for core/task_governor.py — 任务治理引擎"""

import pytest

from core.task_governor import (
    ComplexityAnalyzer,
    ContractRegistry,
    ExecutionStrategy,
    TaskComplexity,
    TaskGovernor,
    TaskPlan,
    TaskPlanner,
)


@pytest.fixture
def registry():
    return ContractRegistry()


class TestComplexityAnalyzer:
    """复杂度分析器测试"""

    def test_analyze_simple(self):
        analyzer = ComplexityAnalyzer()
        complexity, strategy = analyzer.analyze("修复一个拼写错误")
        assert complexity in TaskComplexity
        assert strategy in ExecutionStrategy

    def test_analyze_complex(self):
        analyzer = ComplexityAnalyzer()
        complexity, _strategy = analyzer.analyze("重构整个认证模块，跨 5 个文件")
        assert complexity in TaskComplexity

    def test_analyze_empty(self):
        analyzer = ComplexityAnalyzer()
        complexity, _strategy = analyzer.analyze("")
        assert complexity in TaskComplexity


class TestTaskPlanner:
    """任务规划器测试"""

    def setup_method(self):
        self.registry = ContractRegistry()
        self.planner = TaskPlanner(self.registry)

    def test_plan_basic(self):
        plan = self.planner.plan("写一个函数计算斐波那契数列")
        assert plan is not None
        assert isinstance(plan, TaskPlan)

    def test_plan_empty(self):
        plan = self.planner.plan("")
        assert plan is not None


class TestTaskGovernor:
    """任务治理引擎集成测试"""

    def setup_method(self):
        self.gov = TaskGovernor()

    def test_get_stats(self):
        stats = self.gov.get_stats()
        assert isinstance(stats, dict)

    def test_plan_basic(self):
        plan = self.gov.plan("创建一个 REST API 端点")
        assert plan is not None
        assert isinstance(plan, TaskPlan)

    def test_plan_has_steps(self):
        plan = self.gov.plan("部署服务")
        assert hasattr(plan, "steps")

    def test_plan_has_intent(self):
        plan = self.gov.plan("部署服务")
        assert hasattr(plan, "intent")


class TestTaskComplexity:
    """复杂度枚举测试"""

    def test_all_values(self):
        values = {
            TaskComplexity.TRIVIAL,
            TaskComplexity.SIMPLE,
            TaskComplexity.MODERATE,
            TaskComplexity.COMPLEX,
            TaskComplexity.CRITICAL,
        }
        assert len(values) == 5
