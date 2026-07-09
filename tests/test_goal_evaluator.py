"""Tests for core/goal_evaluator.py — 目标完成度独立评估器"""

import pytest

from core.goal_evaluator import GoalEvaluator, GoalVerdict
from core.goal_manager import GoalManager


@pytest.fixture
def evaluator():
    return GoalEvaluator()


@pytest.fixture
def sample_goal(tmp_path):
    gm = GoalManager(path=tmp_path / "goals.json")
    return gm.create("测试目标", "所有用例通过")


class TestGoalEvaluator:
    """目标评估器全链路测试"""

    def test_evaluate_pass(self, evaluator, sample_goal):
        result = evaluator.evaluate(sample_goal)
        assert result is not None
        assert result.goal_id == sample_goal.id
        assert result.verdict in (GoalVerdict.PASS, GoalVerdict.FAIL, GoalVerdict.NEEDS_FIX)

    def test_evaluate_with_artifacts(self, evaluator, sample_goal):
        result = evaluator.evaluate(sample_goal, artifacts=["test_file.py"])
        assert result is not None
        assert result.goal_id == sample_goal.id

    def test_evaluate_without_artifacts(self, evaluator, sample_goal):
        result = evaluator.evaluate(sample_goal)
        assert result is not None

    def test_evaluate_without_llm(self, evaluator, sample_goal):
        """不含 LLM 评估不崩溃"""
        result = evaluator.evaluate(sample_goal, use_llm=False)
        assert result is not None

    def test_result_has_confidence(self, evaluator, sample_goal):
        result = evaluator.evaluate(sample_goal)
        assert hasattr(result, "confidence")
        assert 0.0 <= result.confidence <= 1.0

    def test_result_has_evidence(self, evaluator, sample_goal):
        result = evaluator.evaluate(sample_goal)
        assert hasattr(result, "evidence")

    def test_result_has_issues(self, evaluator, sample_goal):
        result = evaluator.evaluate(sample_goal)
        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)

    def test_result_has_suggestions(self, evaluator, sample_goal):
        result = evaluator.evaluate(sample_goal)
        assert hasattr(result, "suggestions")
        assert isinstance(result.suggestions, list)

    def test_empty_finish_line_goal(self, tmp_path):
        evaluator = GoalEvaluator()
        gm = GoalManager(path=tmp_path / "g.json")
        goal = gm.create("test", "")
        result = evaluator.evaluate(goal)
        assert result is not None

    def test_none_artifacts(self, evaluator, sample_goal):
        result = evaluator.evaluate(sample_goal, artifacts=None)
        assert result is not None

    def test_large_artifact_list(self, evaluator, sample_goal):
        artifacts = [f"file_{i}.py" for i in range(500)]
        result = evaluator.evaluate(sample_goal, artifacts=artifacts)
        assert result is not None


class TestGoalVerdict:
    """裁决枚举测试"""

    def test_pass_value(self):
        assert GoalVerdict.PASS.value == "pass"

    def test_fail_value(self):
        assert GoalVerdict.FAIL.value == "fail"

    def test_needs_fix_value(self):
        assert GoalVerdict.NEEDS_FIX.value == "needs_fix"
