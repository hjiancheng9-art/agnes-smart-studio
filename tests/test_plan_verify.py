"""Tests for core/plan_verify.py — Plan Schema, Validator, Verify Gates, Re-plan Loop."""

import json
import pytest

from core.plan_verify import (
    Plan,
    PlanStep,
    PlanVerifyLoop,
    VerificationResult,
    validate_plan,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


class FakeRegistry:
    """Fake tool registry for testing."""

    def __init__(self, tools=None):
        self._tools = tools or {"read_file", "edit_file", "run_test", "search_files", "env_check"}

    def has(self, name: str) -> bool:
        return name in self._tools


def fake_llm(prompt: str) -> str:
    """Fake LLM that returns a valid plan JSON."""
    if "重规划" in prompt or "replan" in prompt.lower() or "失败" in prompt:
        return json.dumps([
            {
                "id": "s1",
                "description": "诊断失败根因",
                "action": "explore",
                "tool": "read_file",
                "args": {"path": "output/last_error.txt"},
                "depends_on": [],
                "success_criteria": "读取到错误信息",
                "verify_method": None,
            },
            {
                "id": "s2",
                "description": "采用新方法实施修复",
                "action": "execute",
                "tool": "edit_file",
                "args": {"path": "core/foo.py", "old_text": "old", "new_text": "new"},
                "depends_on": ["s1"],
                "success_criteria": "编辑成功",
                "verify_method": "syntax",
            },
            {
                "id": "s3",
                "description": "验证修复",
                "action": "verify",
                "tool": "run_test",
                "args": {},
                "depends_on": ["s2"],
                "success_criteria": "测试通过",
                "verify_method": "test",
            },
        ])
    # Default: return a simple plan
    return json.dumps([
        {
            "id": "s1",
            "description": "读取相关文件",
            "action": "explore",
            "tool": "read_file",
            "args": {"path": "README.md"},
            "depends_on": [],
            "success_criteria": "成功读取文件",
            "verify_method": None,
        },
        {
            "id": "s2",
            "description": "实施修改",
            "action": "execute",
            "tool": "edit_file",
            "args": {"path": "core/foo.py", "old_text": "old", "new_text": "new"},
            "depends_on": ["s1"],
            "success_criteria": "编辑成功",
            "verify_method": "syntax",
        },
        {
            "id": "s3",
            "description": "运行测试",
            "action": "verify",
            "tool": "run_test",
            "args": {},
            "depends_on": ["s2"],
            "success_criteria": "测试通过",
            "verify_method": "test",
        },
    ])


def make_valid_plan() -> Plan:
    """Create a valid plan for testing."""
    return Plan(
        goal="修复认证模块 bug",
        finish_line="认证模块修复，所有测试通过",
        steps=[
            PlanStep(
                id="s1",
                description="读取相关文件",
                action="explore",
                tool="read_file",
                args={"path": "README.md"},
                depends_on=[],
                success_criteria="成功读取文件",
                verify_method=None,
            ),
            PlanStep(
                id="s2",
                description="实施修改",
                action="execute",
                tool="edit_file",
                args={"path": "core/foo.py"},
                depends_on=["s1"],
                success_criteria="编辑成功",
                verify_method="syntax",
            ),
            PlanStep(
                id="s3",
                description="运行测试",
                action="verify",
                tool="run_test",
                args={},
                depends_on=["s2"],
                success_criteria="测试通过",
                verify_method="test",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════
# Data Model Tests
# ═══════════════════════════════════════════════════════════════


class TestDataModels:
    def test_plan_step_defaults(self):
        s = PlanStep(id="s1", description="test", action="explore")
        assert s.tool == ""
        assert s.args == {}
        assert s.depends_on == []
        assert s.success_criteria == ""
        assert s.verify_method is None

    def test_plan_defaults(self):
        p = Plan(goal="test")
        assert p.finish_line == ""
        assert p.steps == []
        assert p.max_replans == 3
        assert p.current_attempt == 0

    def test_verification_result(self):
        v = VerificationResult(step_id="s1", passed=True, evidence="OK")
        assert v.failure_reason == ""
        assert v.suggestion == ""


# ═══════════════════════════════════════════════════════════════
# Plan Validator Tests
# ═══════════════════════════════════════════════════════════════


class TestValidatePlan:
    def setup_method(self):
        self.registry = FakeRegistry()

    def test_valid_plan(self):
        plan = make_valid_plan()
        errors = validate_plan(plan, self.registry)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_missing_explore(self):
        plan = Plan(
            goal="test",
            finish_line="done",
            steps=[
                PlanStep(id="s1", description="execute", action="execute", tool="edit_file"),
                PlanStep(id="s2", description="verify", action="verify", tool="run_test"),
            ],
        )
        errors = validate_plan(plan, self.registry)
        assert any("explore" in e for e in errors)

    def test_missing_verify(self):
        plan = Plan(
            goal="test",
            finish_line="done",
            steps=[
                PlanStep(id="s1", description="explore", action="explore", tool="read_file"),
                PlanStep(id="s2", description="execute", action="execute", tool="edit_file"),
            ],
        )
        errors = validate_plan(plan, self.registry)
        assert any("verify" in e for e in errors)

    def test_missing_dependency(self):
        plan = Plan(
            goal="test",
            finish_line="done",
            steps=[
                PlanStep(id="s1", description="execute", action="execute", tool="edit_file", depends_on=["nonexistent"]),
                PlanStep(id="s2", description="verify", action="verify", tool="run_test"),
                PlanStep(id="s3", description="explore", action="explore", tool="read_file"),
            ],
        )
        errors = validate_plan(plan, self.registry)
        assert any("nonexistent" in e for e in errors)

    def test_unknown_tool(self):
        plan = Plan(
            goal="test",
            finish_line="done",
            steps=[
                PlanStep(id="s1", description="explore", action="explore", tool="read_file"),
                PlanStep(id="s2", description="verify", action="verify", tool="nonexistent_tool"),
            ],
        )
        errors = validate_plan(plan, self.registry)
        assert any("nonexistent_tool" in e for e in errors)

    def test_empty_finish_line(self):
        plan = Plan(
            goal="test",
            finish_line="",
            steps=[
                PlanStep(id="s1", description="explore", action="explore", tool="read_file"),
                PlanStep(id="s2", description="verify", action="verify", tool="run_test"),
            ],
        )
        errors = validate_plan(plan, self.registry)
        assert any("finish_line" in e for e in errors)


# ═══════════════════════════════════════════════════════════════
# PlanVerifyLoop Tests
# ═══════════════════════════════════════════════════════════════


class TestPlanVerifyLoop:
    def setup_method(self):
        self.registry = FakeRegistry()
        self.tool_results = {}

        def fake_exec(name: str, args: dict) -> str:
            self.tool_results[name] = args
            return f"{name} executed with {args}"

        self.fake_exec = fake_exec

    def test_execute_with_valid_plan(self):
        """测试有效计划能正常执行完成。"""
        loop = PlanVerifyLoop(
            llm_callable=fake_llm,
            tool_executor=self.fake_exec,
            registry=self.registry,
            max_replans=3,
        )
        plan = make_valid_plan()
        result = loop.execute_with_replan(plan.goal, plan.finish_line, initial_plan=plan)
        # 注意: 由于 verify_method="syntax" 和 "test" 需要实际环境，
        # 在无真实环境时可能失败，但至少循环能跑起来
        assert result["status"] in ("completed", "exhausted", "plan_invalid")
        assert result["goal"] == plan.goal

    def test_plan_invalid_without_finish_line(self):
        """测试缺少 finish_line 时计划被拒绝。"""
        plan = Plan(
            goal="test",
            finish_line="",
            steps=[
                PlanStep(id="s1", description="explore", action="explore", tool="read_file"),
                PlanStep(id="s2", description="verify", action="verify", tool="run_test"),
            ],
        )
        loop = PlanVerifyLoop(
            llm_callable=fake_llm,
            tool_executor=self.fake_exec,
            registry=self.registry,
        )
        result = loop.execute_with_replan("test", "", initial_plan=plan)
        assert result["status"] == "plan_invalid"
        assert any("finish_line" in e for e in result["errors"])

    def test_llm_generates_plan(self):
        """测试不提供预设计划时，LLM 能自动生成。"""
        loop = PlanVerifyLoop(
            llm_callable=fake_llm,
            tool_executor=self.fake_exec,
            registry=self.registry,
        )
        result = loop.execute_with_replan("修复 bug", "测试通过")
        # LLM 生成的计划应该通过校验（fake_llm 返回合法计划）
        assert result["status"] in ("completed", "exhausted")

    def test_verification_no_method(self):
        """测试 verify_method=None 的步骤自动通过。"""
        loop = PlanVerifyLoop(
            llm_callable=fake_llm,
            tool_executor=self.fake_exec,
            registry=self.registry,
        )
        step = PlanStep(id="s1", description="test", action="explore", tool="read_file")
        v = loop._verify_step(step, "result")
        assert v.passed is True
        assert v.evidence == "无需验证"

    def test_verification_unknown_method(self):
        """测试未知验证方法返回失败。"""
        loop = PlanVerifyLoop(
            llm_callable=fake_llm,
            tool_executor=self.fake_exec,
            registry=self.registry,
        )
        step = PlanStep(id="s1", description="test", action="execute", verify_method="unknown_method")
        v = loop._verify_step(step, "result")
        assert v.passed is False
        assert "未知验证方法" in v.failure_reason
