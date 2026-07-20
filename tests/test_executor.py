"""Tests for core.executor — task execution engine.

Covers: data classes, quick_plan, JSON parsers, TaskExecutor core loop.
"""

import pytest

from core.executor import (
    Goal,
    SemanticVerifier,
    SmartPlanner,
    Step,
    Task,
    TaskExecutor,
    quick_plan,
)
from core.executor_models import AdjustResult


@pytest.fixture(autouse=True)
def _isolate_goal_manager():
    """Ensure clean goal_manager for each test.

    TaskExecutor.run() accesses goal_manager internally. Without this,
    goals from prior tests leak and cause steps to be skipped.
    """
    import core.goal_manager

    core.goal_manager._goal_manager = None


def _ok(name, args):
    return f"OK: {name}({args})"


def _fail(name, args):
    raise RuntimeError(f"FAIL: {name}")


# ═══════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════


class TestStep:
    def test_defaults(self):
        s = Step("s1", "desc", "run_bash")
        assert s.args == {}
        assert s.depends_on == []
        assert s.verify is None
        assert s.status == "pending"

    def test_full(self):
        s = Step("s2", "run", "run_test", {"path": "t/"}, depends_on=["s1"], verify="test")
        assert s.args == {"path": "t/"}
        assert s.depends_on == ["s1"]
        assert s.verify == "test"

    def test_depends_on_not_shared(self):
        s1 = Step("a", "first", "run_bash")
        s2 = Step("b", "second", "run_bash")
        s1.depends_on.append("x")
        assert s2.depends_on == []


class TestTask:
    def test_defaults(self):
        t = Task(id="t1", goal="do stuff")
        assert t.steps == []
        assert t.status == "pending"
        assert t.errors_allowed == 0
        assert t.reflection_enabled is False
        assert t.max_retries_per_step == 2

    def test_with_steps(self):
        steps = [Step("s1", "a", "run_bash"), Step("s2", "b", "run_test")]
        t = Task(id="t2", goal="test", steps=steps, errors_allowed=2, reflection_enabled=True)
        assert len(t.steps) == 2
        assert t.errors_allowed == 2


class TestAdjustResult:
    def test_simple(self):
        r = AdjustResult(action="skip")
        assert r.action == "skip"

    def test_full(self):
        r = AdjustResult(action="retry", tool="run_bash", args={"cmd": "ls"}, reason="timeout")
        assert r.action == "retry"


class TestGoalBudget:
    @staticmethod
    def _g(**kw):
        return Goal(id="g_test", **kw)

    def test_steps_exhausted(self):
        assert self._g(intent="t", max_steps=3, steps_executed=3).is_budget_exhausted()

    def test_steps_not_exhausted(self):
        assert not self._g(intent="t", max_steps=5, steps_executed=3).is_budget_exhausted()

    def test_tool_calls_exhausted(self):
        assert self._g(intent="t", max_tool_calls=1, tool_calls_made=1).is_budget_exhausted()

    def test_neither(self):
        g = self._g(intent="t", max_steps=10, steps_executed=5, max_tool_calls=100, tool_calls_made=50)
        assert not g.is_budget_exhausted()

    def test_roundtrip(self):
        g = self._g(intent="rt", finish_line="ok", max_steps=7)
        g2 = Goal.from_dict(g.to_dict())
        assert g2.intent == g.intent
        assert g2.max_steps == g.max_steps

    def test_from_dict_partial(self):
        g = Goal.from_dict({"id": "g_min", "intent": "minimal"})
        assert g.intent == "minimal"
        assert g.max_steps == 20


# ═══════════════════════════════════════════════════════════════════
# quick_plan
# ═══════════════════════════════════════════════════════════════════


class TestQuickPlan:
    def test_audit(self):
        t = quick_plan("audit the codebase")
        assert len(t.steps) == 2
        assert t.steps[0].tool == "env_check"

    def test_test(self):
        t = quick_plan("run the tests")
        assert len(t.steps) == 1
        assert t.steps[0].verify == "test"

    def test_fix(self):
        t = quick_plan("fix the login bug")
        assert len(t.steps) == 4
        assert t.steps[3].verify == "syntax"

    def test_fallback(self):
        t = quick_plan("analyze architecture")
        assert len(t.steps) == 2

    def test_empty(self):
        t = quick_plan("")
        assert len(t.steps) == 2

    def test_metadata(self):
        t = quick_plan("test something")
        assert t.id.startswith("task_")
        assert t.errors_allowed == 1


# ═══════════════════════════════════════════════════════════════════
# JSON Parsers
# ═══════════════════════════════════════════════════════════════════


class TestExtractJson:
    def test_direct(self):
        assert SmartPlanner._extract_json('[{"id":"1"}]') == '[{"id":"1"}]'

    def test_markdown(self):
        assert SmartPlanner._extract_json('```json\n[{"id":"1"}]\n```') == '[{"id":"1"}]'

    def test_brackets(self):
        assert SmartPlanner._extract_json('text [{"id":"1"}] tail') == '[{"id":"1"}]'

    def test_empty(self):
        assert SmartPlanner._extract_json("") == ""

    def test_none(self):
        assert SmartPlanner._extract_json(None) == ""

    def test_no_brackets(self):
        assert SmartPlanner._extract_json("plain text") == ""


class TestParseVerifyJson:
    def test_achieved_false(self):
        r = SemanticVerifier._parse_verify_json('{"achieved":false,"gap":"fail"}')
        assert r["achieved"] is False

    def test_achieved_true(self):
        r = SemanticVerifier._parse_verify_json('{"achieved":true}')
        assert r["achieved"] is True

    def test_markdown(self):
        r = SemanticVerifier._parse_verify_json('```json\n{"achieved":true}\n```')
        assert r["achieved"] is True

    def test_invalid(self):
        r = SemanticVerifier._parse_verify_json("garbage")
        assert r["achieved"] is True


# ═══════════════════════════════════════════════════════════════════
# TaskExecutor.run — core loop
# ═══════════════════════════════════════════════════════════════════


class TestTaskExecutorRun:
    @staticmethod
    def _task(steps, **kw):
        return Task(
            id="t_test",
            goal="test",
            steps=steps,
            errors_allowed=kw.get("errors_allowed", 0),
        )

    def test_all_succeed(self):
        steps = [Step("s1", "a", "run_bash"), Step("s2", "b", "run_test"), Step("s3", "c", "env_check")]
        task = self._task(steps)
        report = TaskExecutor(_ok).run(task)
        assert report["steps_done"] == 3
        assert report["steps_failed"] == 0

    def test_single_failure_within_budget(self):
        calls = [0]

        def flaky(name, args):
            calls[0] += 1
            if name == "run_test":
                raise RuntimeError("flake")
            return "OK"

        steps = [Step("s1", "a", "run_bash"), Step("s2", "b", "run_test"), Step("s3", "c", "env_check")]
        task = self._task(steps, errors_allowed=1)
        report = TaskExecutor(flaky).run(task)
        assert report["steps_done"] == 2
        assert report["steps_failed"] == 1

    def test_failures_exceed_budget_breaks(self):
        steps = [Step("s1", "a", "run_bash"), Step("s2", "b", "run_test"), Step("s3", "c", "env_check")]
        task = self._task(steps, errors_allowed=0)
        report = TaskExecutor(_fail).run(task)
        assert report["steps_failed"] >= 1
        assert task.steps[2].status == "pending"

    def test_dependency_unmet_skips(self):
        steps = [
            Step("s1", "fail", "run_bash"),
            Step("s2", "dep", "run_test", depends_on=["s1"]),
            Step("s3", "dep2", "env_check", depends_on=["s2"]),
        ]
        task = self._task(steps, errors_allowed=5)
        TaskExecutor(_fail).run(task)
        assert task.steps[0].status == "failed"
        assert task.steps[1].status == "skipped"
        assert task.steps[2].status == "skipped"

    def test_dependency_met(self):
        steps = [Step("s1", "a", "run_bash"), Step("s2", "b", "run_test", depends_on=["s1"])]
        task = self._task(steps)
        TaskExecutor(_ok).run(task)
        assert task.steps[1].status == "done"

    def test_result_truncation(self):
        steps = [Step("s1", "big", "run_bash")]
        task = self._task(steps)
        TaskExecutor(lambda n, a: "x" * 1000).run(task)
        assert len(task.steps[0].result) == 500

    def test_report_keys(self):
        steps = [Step("s1", "a", "run_bash")]
        task = self._task(steps)
        report = TaskExecutor(_ok).run(task)
        for k in ("steps_done", "steps_failed", "steps_skipped", "elapsed", "log"):
            assert k in report
