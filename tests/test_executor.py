"""Tests for core.executor — 自主任务执行器，含依赖追踪、错误恢复、验证门。

TaskExecutor 把自然语言任务分解为 Step 序列，按依赖顺序执行，
支持 verify="syntax" 和 verify="test" 两个验证门。
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.executor import Step, Task, TaskExecutor, quick_plan


# ── 测试隔离：每个测试前重置 goal 状态，避免测试间污染 ──────────
@pytest.fixture(autouse=True)
def _reset_goal_state():
    """确保每个测试从干净 goal 状态开始。"""
    try:
        from core.goal_manager import get_goal_manager
        mgr = get_goal_manager()
        mgr._goals.clear()
        mgr._active_goal_id = ""
        mgr._next_id = 1
    except Exception:
        pass


# ── quick_plan（纯函数，零 mock）──────────────────────────────────


class TestQuickPlan:
    """quick_plan 基于关键词生成不同 Step 列表。"""

    def test_fix_bug_pattern(self):
        task = quick_plan("fix the login bug")
        assert task.goal == "fix the login bug"
        assert len(task.steps) == 4
        assert task.errors_allowed == 1
        assert task.steps[0].tool == "read_file"
        assert task.steps[2].tool == "edit_file"
        assert task.steps[3].verify == "syntax"

    def test_repair_pattern(self):
        task = quick_plan("repair the broken module")
        assert len(task.steps) == 4
        assert task.steps[0].id == "1_read_error"

    def test_audit_pattern(self):
        task = quick_plan("audit the codebase")
        assert len(task.steps) == 2
        assert task.steps[0].tool == "env_check"
        assert task.steps[1].tool == "run_test"
        assert task.steps[1].verify == "test"

    def test_check_pattern(self):
        task = quick_plan("check for lint errors")
        assert len(task.steps) == 2

    def test_scan_pattern(self):
        task = quick_plan("scan the dependencies")
        assert len(task.steps) == 2

    def test_test_pattern(self):
        task = quick_plan("run the test suite")
        assert len(task.steps) == 1
        assert task.steps[0].tool == "run_test"
        assert task.steps[0].verify == "test"

    def test_test_overrides_audit(self):
        # 三个 if 非 elif，后覆盖前："audit and test" → test 分支覆盖 audit
        task = quick_plan("audit and test the suite")
        assert len(task.steps) == 1
        assert task.steps[0].id == "1_test"

    def test_fix_and_test_coexist(self):
        # "fix" 先命中设置 4 步，然后 "test" 覆盖为 1 步
        task = quick_plan("fix and test everything")
        assert len(task.steps) == 1

    def test_default_pattern_no_keywords(self):
        task = quick_plan("hello world")
        assert len(task.steps) == 2
        assert task.steps[0].tool == "read_file"
        assert task.steps[0].args["path"] == "README.md"
        assert task.steps[1].tool == "env_check"

    def test_task_id_prefix(self):
        task = quick_plan("something")
        assert task.id.startswith("task_")

    def test_step_dependencies_fix_pattern(self):
        task = quick_plan("fix crash")
        s1 = task.steps[0]  # 1_read_error, no deps
        _s2 = task.steps[1]  # 2_search_code, no deps
        s3 = task.steps[2]  # 3_fix, depends on 2_search_code
        s4 = task.steps[3]  # 4_verify, depends on 3_fix
        assert s1.depends_on == []
        assert s3.depends_on == ["2_search_code"]
        assert s4.depends_on == ["3_fix"]

    def test_fix_pattern_uses_last_word_as_search_pattern(self):
        task = quick_plan("fix the login bug")
        # goal.split()[-1] = "bug" → pattern
        assert task.steps[1].args["pattern"] == "bug"
        # "fix only" → only one word, pattern = "fix"
        task2 = quick_plan("fix")
        assert task2.steps[1].args["pattern"] == "fix"


# ── TaskExecutor.run（传 mock tool_executor）────────────────────────


class TestTaskExecutorRun:
    """run 方法的依赖追踪、错误恢复、报告结构。"""

    def _make_executor(self, tool_fn):
        return TaskExecutor(tool_fn, root=ROOT)

    def test_linear_chain_all_success(self):
        mock_fn = MagicMock(return_value="ok")
        task = Task(
            id="t1",
            goal="test goal",
            steps=[
                Step("s1", "Step 1", "read_file", {"path": "x.py"}),
                Step("s2", "Step 2", "env_check", {}),
                Step("s3", "Step 3", "read_file", {"path": "y.py"}),
            ],
            errors_allowed=0,
        )
        report = self._make_executor(mock_fn).run(task)
        assert report["status"] == "done"
        assert report["steps_done"] == 3
        assert report["steps_failed"] == 0
        assert report["steps_skipped"] == 0
        assert mock_fn.call_count == 3
        assert all(s.status == "done" for s in task.steps)

    def test_dependency_failed_downstream_skipped(self):
        def tool_fn(name, args):
            if name == "read_file":
                return "content"
            raise ValueError("tool error")

        task = Task(
            id="t2",
            goal="dep test",
            steps=[
                Step("s1", "Read", "read_file", {"path": "a.py"}),
                Step("s2", "Fix", "edit_file", {"path": "a.py"}, depends_on=["s1"]),
            ],
            errors_allowed=1,
        )
        self._make_executor(tool_fn).run(task)
        # s1 done, s2 failed (tool error), but no downstream to skip
        assert task.steps[0].status == "done"
        assert task.steps[1].status == "failed"

    def test_dependency_not_met_skipped(self):
        task = Task(
            id="t3",
            goal="skip test",
            steps=[
                Step("s1", "Read", "read_file", {}),
                Step("s2", "Depends on s3", "edit_file", {}, depends_on=["s3"]),  # s3 doesn't exist
                Step("s3", "Independent", "env_check", {}),
            ],
            errors_allowed=0,
        )
        mock_fn = MagicMock(return_value="ok")
        self._make_executor(mock_fn).run(task)
        assert task.steps[0].status == "done"
        assert task.steps[1].status == "skipped"
        assert "Dependencies not met" in task.steps[1].error
        # s3 仍正常执行（顺序遍历，不因 s2 被 skip 而中止）
        assert task.steps[2].status == "done"

    def test_error_budget_zero_breaks_immediately(self):
        call_count = [0]

        def tool_fn(name, args):
            call_count[0] += 1
            raise RuntimeError("boom")

        task = Task(
            id="t4",
            goal="budget test",
            steps=[
                Step("s1", "Fail 1", "env_check", {}),
                Step("s2", "Never runs", "read_file", {}),
            ],
            errors_allowed=0,
        )
        report = self._make_executor(tool_fn).run(task)
        assert report["status"] == "failed"
        assert call_count[0] == 1  # 第一步就 break，第二步不执行

    def test_error_budget_one_continues(self):
        call_count = [0]

        def tool_fn(name, args):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("transient")
            return "ok"

        task = Task(
            id="t5",
            goal="budget test",
            steps=[
                Step("s1", "Fail first", "env_check", {}),
                Step("s2", "Succeed", "read_file", {}),
            ],
            errors_allowed=1,
        )
        self._make_executor(tool_fn).run(task)
        assert call_count[0] == 2  # 两个都执行了
        assert task.steps[0].status == "failed"
        assert task.steps[1].status == "done"

    def test_only_catches_specific_exceptions(self):
        # executor 只 catch OSError/ValueError/RuntimeError，KeyError 会逃逸
        def tool_fn(name, args):
            raise KeyError("not caught")

        task = Task(
            id="t6",
            goal="key error test",
            steps=[Step("s1", "Boom", "env_check", {})],
            errors_allowed=1,
        )
        with pytest.raises(KeyError):
            self._make_executor(tool_fn).run(task)

    def test_report_structure(self):
        mock_fn = MagicMock(return_value="ok")
        task = Task(
            id="t7",
            goal="report test",
            steps=[
                Step("s1", "Done", "read_file", {}),
                Step("s2", "Also done", "env_check", {}),
            ],
            errors_allowed=0,
        )
        report = self._make_executor(mock_fn).run(task)
        # 必有字段
        for key in (
            "goal",
            "status",
            "elapsed",
            "steps_total",
            "steps_done",
            "steps_failed",
            "steps_skipped",
            "details",
            "log",
        ):
            assert key in report
        # details 只含非 done 步骤 → 全 done 时 details 为空
        assert len(report["details"]) == 0
        # log 截断到最后 10 条
        assert len(report["log"]) <= 10


# ── verify=syntax（tmp_path 上 ast.parse 守卫）──────────────────


class TestVerifySyntax:
    """verify="syntax" 分支扫描 root 下 .py 文件做 ast.parse。"""

    def test_syntax_ok(self, tmp_path):
        (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
        step = Step("s1", "Verify", "env_check", {}, verify="syntax")
        task = Task(id="t", goal="v", steps=[step], errors_allowed=0)
        TaskExecutor(lambda n, a: "ok", root=tmp_path).run(task)
        assert step.status == "done"

    def test_syntax_error_fails(self, tmp_path):
        (tmp_path / "bad.py").write_text("def(\n", encoding="utf-8")
        step = Step("s1", "Verify", "env_check", {}, verify="syntax")
        task = Task(id="t", goal="v", steps=[step], errors_allowed=0)
        report = TaskExecutor(lambda n, a: "ok", root=tmp_path).run(task)
        assert step.status == "failed"
        assert "Syntax check failed" in step.error
        assert report["status"] == "failed"


# ── verify=test（patch run_pytest_safe 避免真 spawn）──────────────


class TestVerifyTest:
    """verify="test" 分支走 pytest_runner，在 pytest 内自动短路。"""

    def test_no_failures_passes(self):
        # run_pytest_safe 在 pytest 内短路返回 returncode=0 + "skipped"
        # "failed" 不在 stdout → 验证通过
        step = Step("s1", "Test", "run_test", {}, verify="test")
        task = Task(id="t", goal="v", steps=[step], errors_allowed=0)
        TaskExecutor(lambda n, a: "ok", root=ROOT).run(task)
        assert step.status == "done"

    def test_test_failures_detected(self, monkeypatch):
        # 强制 run_pytest_safe 返回有 failed 的输出
        fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="1 failed, 2 passed", stderr="")
        monkeypatch.setattr("core.pytest_runner.run_pytest_safe", lambda **kw: fake)
        step = Step("s1", "Test", "run_test", {}, verify="test")
        task = Task(id="t", goal="v", steps=[step], errors_allowed=0)
        report = TaskExecutor(lambda n, a: "ok", root=ROOT).run(task)
        assert step.status == "failed"
        assert "Tests failed" in step.error
        assert report["status"] == "failed"

    def test_zero_failed_ok(self, monkeypatch):
        # "0 failed" 在 stdout → 不触发失败（边界条件）
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="0 failed, 5 passed", stderr="")
        monkeypatch.setattr("core.pytest_runner.run_pytest_safe", lambda **kw: fake)
        step = Step("s1", "Test", "run_test", {}, verify="test")
        task = Task(id="t", goal="v", steps=[step], errors_allowed=0)
        TaskExecutor(lambda n, a: "ok", root=ROOT).run(task)
        assert step.status == "done"

    def test_empty_output_passes(self, monkeypatch):
        # 空 stdout → "failed" not in "" → 验证通过
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        monkeypatch.setattr("core.pytest_runner.run_pytest_safe", lambda **kw: fake)
        step = Step("s1", "Test", "run_test", {}, verify="test")
        task = Task(id="t", goal="v", steps=[step], errors_allowed=0)
        TaskExecutor(lambda n, a: "ok", root=ROOT).run(task)
        assert step.status == "done"
