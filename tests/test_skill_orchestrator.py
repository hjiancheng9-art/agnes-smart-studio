"""Tests for core/skill_orchestrator.py — search, plan, execute, learn."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.skill_orchestrator import SkillMatch, Plan, PlanStep, SkillOrchestrator, get_orchestrator


class TestSearch:
    def test_search_returns_list(self):
        orch = SkillOrchestrator()
        results = orch.search("code review", top_k=3)
        assert isinstance(results, list)
        assert all(isinstance(r, SkillMatch) for r in results)

    def test_search_relevance_ordering(self):
        orch = SkillOrchestrator()
        results = orch.search("fix bugs in python", top_k=3)
        # Should score skills with matching names higher
        if len(results) >= 2:
            assert results[0].score >= results[1].score

    def test_search_empty_query(self):
        orch = SkillOrchestrator()
        results = orch.search("")
        assert isinstance(results, list)

    def test_search_unknown_topic(self):
        orch = SkillOrchestrator()
        results = orch.search("xyzzy_nonexistent_topic_12345")
        # May return results (token overlap) but all scores should be low
        assert all(r.score < 0.3 for r in results) if results else True


class TestPlan:
    def test_plan_returns_plan(self):
        orch = SkillOrchestrator()
        plan = orch.plan("code review")
        assert isinstance(plan, Plan)
        assert plan.goal == "code review"
        assert isinstance(plan.steps, list)

    def test_plan_empty_goal(self):
        orch = SkillOrchestrator()
        plan = orch.plan("")
        assert plan.steps == []

    def test_plan_mode_semi(self):
        orch = SkillOrchestrator()
        plan = orch.plan("deploy to production", mode="semi")
        assert plan.mode == "semi"

    def test_plan_mode_default_auto(self):
        orch = SkillOrchestrator()
        plan = orch.plan("fix bugs")
        assert plan.mode == "auto"


class TestPlanStep:
    def test_step_needs_approval(self):
        auto = PlanStep(skill_name="test", goal="x", risk="auto")
        assert not auto.needs_approval
        confirm = PlanStep(skill_name="test", goal="x", risk="confirm")
        assert confirm.needs_approval
        manual = PlanStep(skill_name="test", goal="x", risk="manual")
        assert manual.needs_approval

    def test_step_verify_field(self):
        step = PlanStep(skill_name="test", goal="x", verify="pytest")
        assert step.verify == "pytest"

    def test_step_depends_on(self):
        step = PlanStep(skill_name="b", goal="x", depends_on=["a"])
        assert step.depends_on == ["a"]


class TestPlanDataModel:
    def test_plan_to_dict(self):
        plan = Plan(goal="test", steps=[PlanStep(skill_name="s", goal="g")], mode="semi", retry="skip")
        d = plan.to_dict()
        assert d["goal"] == "test"
        assert d["mode"] == "semi"
        assert d["retry"] == "skip"
        assert len(d["steps"]) == 1

    def test_plan_defaults(self):
        plan = Plan(goal="test")
        assert plan.mode == "auto"
        assert plan.retry == "stop"
        assert plan.steps == []


class TestExecute:
    def test_execute_empty_plan(self):
        orch = SkillOrchestrator()
        plan = Plan(goal="test")
        result = orch.execute(plan)
        assert result["ok"] is True
        assert result["steps"] == 0
        assert result["passed"] == 0

    def test_execute_empty_plan_ok(self):
        orch = SkillOrchestrator()
        plan = Plan(goal="test")
        result = orch.execute(plan)
        assert result["ok"] is True
        assert result["passed"] == 0

    def test_execute_semi_mode_high_risk_blocks(self):
        orch = SkillOrchestrator()
        step = PlanStep(skill_name="deploy", goal="deploy", risk="confirm")
        plan = Plan(goal="test", steps=[step], mode="semi")
        result = orch.execute(plan, confirm_fn=lambda name, risk: False)
        assert result["ok"] is False
        assert "approval denied" in str(result["results"][0].get("error", ""))


class TestSingleton:
    def test_get_orchestrator_returns_same(self):
        a = get_orchestrator()
        b = get_orchestrator()
        assert a is b


class TestRiskClassification:
    def test_deploy_is_high_risk(self):
        orch = SkillOrchestrator()
        risk = orch._classify_risk("any-skill", "deploy to production")
        assert risk in ("confirm", "manual")

    def test_normal_task_is_auto(self):
        orch = SkillOrchestrator()
        risk = orch._classify_risk("code-review", "review this code")
        assert risk == "auto"
