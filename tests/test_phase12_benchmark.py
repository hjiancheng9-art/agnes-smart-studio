"""Test P12: Capability Benchmark Arena + Release Gate."""

import pytest

from core.benchmark.runner import BenchmarkResult, BenchmarkRunner, TaskResult
from core.benchmark.scorer import (
    BenchmarkHistory,
    BenchmarkScorecard,
    ReleaseDecision,
    ReleaseGate,
    ReleaseGateResult,
)
from core.benchmark.tasks import BenchmarkTask, get_default_suite


@pytest.fixture
def suite():
    return get_default_suite()


@pytest.fixture
def runner():
    return BenchmarkRunner()


# ── BenchmarkTask ───────────────────────────────────────────────────


class TestBenchmarkTask:
    def test_creation(self):
        t = BenchmarkTask(id="test", category="debug", difficulty="easy", prompt="Fix this bug")
        assert t.id == "test"
        assert t.category == "debug"

    def test_to_dict(self):
        t = BenchmarkTask(id="t1", category="code_gen", difficulty="medium", prompt="Write code")
        d = t.to_dict()
        assert d["id"] == "t1"
        assert d["difficulty"] == "medium"


# ── TaskSuite ───────────────────────────────────────────────────────


class TestTaskSuite:
    def test_default_suite_has_tasks(self, suite):
        assert suite.total >= 15  # at least 15 tasks
        assert suite.name == "CRUX Core Capabilities"

    def test_by_category(self, suite):
        code = suite.by_category("code_gen")
        assert len(code) >= 2

    def test_by_difficulty(self, suite):
        easy = suite.by_difficulty("easy")
        assert len(easy) >= 3

    def test_to_dict(self, suite):
        d = suite.to_dict()
        assert d["total"] >= 15


# ── BenchmarkRunner ─────────────────────────────────────────────────


class TestBenchmarkRunner:
    def test_run_task_success(self, runner):
        t = BenchmarkTask(
            id="test_pass",
            category="qa",
            difficulty="easy",
            prompt="What is Python?",
            expected_keywords=["programming", "language"],
            min_response_length=20,
        )
        result = runner.run_task(t, response="Python is a programming language used for web development.")
        assert result.success
        assert result.has_expected_keywords
        assert result.score > 60

    def test_run_task_fail_empty(self, runner):
        t = BenchmarkTask(
            id="test_fail",
            category="qa",
            difficulty="easy",
            prompt="Say something",
            min_response_length=50,
        )
        result = runner.run_task(t, response="")
        assert not result.success
        assert result.score == 0.0

    def test_run_task_missing_keywords(self, runner):
        t = BenchmarkTask(
            id="test_kw",
            category="qa",
            difficulty="easy",
            prompt="Explain git",
            expected_keywords=["commit", "branch", "merge"],
            min_response_length=20,
        )
        result = runner.run_task(t, response="Python is a language.")
        assert not result.has_expected_keywords
        assert result.score < 100  # penalized for missing keywords

    def test_run_task_forbidden_keywords(self, runner):
        t = BenchmarkTask(
            id="test_fk",
            category="qa",
            difficulty="easy",
            prompt="Explain",
            forbidden_keywords=["badword"],
            min_response_length=20,
        )
        result = runner.run_task(t, response="This contains badword and should be penalized")
        assert result.has_forbidden_keywords

    def test_run_task_tool_calls(self, runner):
        t = BenchmarkTask(
            id="test_tools",
            category="tool_use",
            difficulty="medium",
            prompt="Read a file",
            expected_tools=["read_file"],
            min_response_length=20,
        )
        result = runner.run_task(t, response="I read the file", tool_calls=[{"name": "read_file", "arguments": {}}])
        assert result.has_expected_tools
        assert result.tool_call_count == 1

    def test_run_task_too_many_tools(self, runner):
        t = BenchmarkTask(
            id="test_maxtools",
            category="tool_use",
            difficulty="medium",
            prompt="Do stuff",
            max_tool_calls=2,
            min_response_length=20,
        )
        calls = [{"name": f"t{i}", "arguments": {}} for i in range(5)]
        result = runner.run_task(t, response="Done many things", tool_calls=calls)
        assert result.tool_call_count == 5
        assert result.score <= 90  # penalized for too many calls

    def test_task_result_to_dict(self, runner):
        t = BenchmarkTask(id="t1", category="qa", difficulty="easy", prompt="Hi")
        r = runner.run_task(t, response="Hello world")
        d = r.to_dict()
        assert d["task_id"] == "t1"
        assert "score" in d


# ── BenchmarkResult ────────────────────────────────────────────────


class TestBenchmarkResult:
    def test_pass_rate(self):
        br = BenchmarkResult(suite_name="test", total_tasks=10, passed=7, failed=3)
        assert br.pass_rate == 70.0
        assert br.average_score == 0.0

    def test_by_category(self, runner):
        t1 = BenchmarkTask(id="a1", category="code_gen", difficulty="easy", prompt="Do X", min_response_length=10)
        t2 = BenchmarkTask(id="a2", category="debug", difficulty="easy", prompt="Do Y", min_response_length=10)
        r1 = runner.run_task(t1, response="result a")
        r2 = runner.run_task(t2, response="result b")
        br = BenchmarkResult(suite_name="test", total_tasks=2, passed=2, failed=0, task_results=[r1, r2])
        cats = br.by_category()
        assert "code_gen" in cats
        assert "debug" in cats

    def test_summary(self, runner):
        t = BenchmarkTask(id="s1", category="qa", difficulty="easy", prompt="Hi", min_response_length=5)
        r = runner.run_task(t, response="Hello")
        br = BenchmarkResult(suite_name="test", total_tasks=1, passed=1, failed=0, task_results=[r])
        s = br.summary()
        assert "Benchmark" in s

    def test_to_dict(self, runner):
        t = BenchmarkTask(id="d1", category="qa", difficulty="easy", prompt="Hi", min_response_length=5)
        r = runner.run_task(t, response="Hello")
        br = BenchmarkResult(suite_name="test", total_tasks=1, passed=1, failed=0, task_results=[r])
        d = br.to_dict()
        assert d["pass_rate"] == 100.0


# ── BenchmarkScorecard ──────────────────────────────────────────────


class TestBenchmarkScorecard:
    def test_compute(self, runner):
        t1 = BenchmarkTask(
            id="c1",
            category="code_gen",
            difficulty="easy",
            prompt="X",
            expected_keywords=["def"],
            min_response_length=10,
        )
        t2 = BenchmarkTask(id="c2", category="debug", difficulty="easy", prompt="Y", min_response_length=10)
        r1 = runner.run_task(t1, response="def foo(): pass")
        r2 = runner.run_task(t2, response="bug fixed")
        br = BenchmarkResult(suite_name="test", total_tasks=2, passed=2, failed=0, task_results=[r1, r2])

        sc = BenchmarkScorecard()
        sc.compute(br)
        assert sc.overall_score > 0
        assert len(sc.dimensions) >= 2

    def test_compute_with_previous(self, runner):
        t = BenchmarkTask(id="p1", category="qa", difficulty="easy", prompt="Hi", min_response_length=5)
        r = runner.run_task(t, response="Hello")
        br = BenchmarkResult(suite_name="test", total_tasks=1, passed=1, failed=0, task_results=[r])

        sc = BenchmarkScorecard(previous_score=80.0)
        sc.compute(br)
        assert sc.score_delta != 0

    def test_summary(self):
        sc = BenchmarkScorecard(suite_name="test", overall_score=85.0, pass_rate=80.0)
        s = sc.summary()
        assert "Scorecard" in s
        assert "85" in s

    def test_trends(self):
        h = [
            BenchmarkScorecard(suite_name="t", overall_score=70.0, pass_rate=60.0),
            BenchmarkScorecard(suite_name="t", overall_score=80.0, pass_rate=75.0),
            BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0),
        ]
        s = h[-1].trends(h)
        assert "🔺" in s
        assert "70" in s


# ── ReleaseGate ─────────────────────────────────────────────────────


class TestReleaseGate:
    def test_pass(self):
        sc = BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0)
        gate = ReleaseGate(min_overall_score=70.0)
        result = gate.evaluate(sc)
        assert result.decision == ReleaseDecision.PASS
        assert result.can_release

    def test_block_low_score(self):
        sc = BenchmarkScorecard(suite_name="t", overall_score=50.0, pass_rate=40.0)
        gate = ReleaseGate(min_overall_score=70.0)
        result = gate.evaluate(sc)
        assert result.decision == ReleaseDecision.BLOCK
        assert not result.can_release

    def test_block_regression(self):
        h = [BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0)]
        sc = BenchmarkScorecard(suite_name="t", overall_score=60.0, pass_rate=55.0)
        gate = ReleaseGate(min_overall_score=50.0, max_regression_delta=-5.0)
        result = gate.evaluate(sc, h)
        assert result.decision == ReleaseDecision.BLOCK

    def test_warn_slight_drop(self):
        h = [BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0)]
        sc = BenchmarkScorecard(suite_name="t", overall_score=82.0, pass_rate=78.0)
        gate = ReleaseGate(min_overall_score=70.0, max_regression_delta=-5.0)
        result = gate.evaluate(sc, h)
        assert result.decision == ReleaseDecision.WARN

    def test_summary(self):
        sc = BenchmarkScorecard(suite_name="t", overall_score=85.0)
        result = ReleaseGateResult(decision=ReleaseDecision.PASS, scorecard=sc, reasons=["All good"])
        s = result.summary()
        assert "PASS" in s


# ── BenchmarkHistory ────────────────────────────────────────────────


class TestBenchmarkHistory:
    def test_save_and_load(self, tmp_path):
        sc = BenchmarkScorecard(suite_name="test", overall_score=85.0, pass_rate=80.0, timestamp=1000.0)
        bh = BenchmarkHistory(history_dir=str(tmp_path / "hist"))
        bh.save(sc)
        loaded = bh.load_all("test")
        assert len(loaded) >= 1

    def test_last(self, tmp_path):
        sc1 = BenchmarkScorecard(suite_name="test", overall_score=80.0, pass_rate=75.0, timestamp=1000.0)
        sc2 = BenchmarkScorecard(suite_name="test", overall_score=90.0, pass_rate=85.0, timestamp=2000.0)
        bh = BenchmarkHistory(history_dir=str(tmp_path / "hist2"))
        bh.save(sc1)
        bh.save(sc2)
        last = bh.last("test")
        assert last is not None
        assert last.overall_score == 90.0


# ── Integration ─────────────────────────────────────────────────────


class TestIntegration:
    def test_validation_layer_has_benchmark(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        assert hasattr(vl, "_bench_suite")
        assert hasattr(vl, "_bench_runner")

    def test_run_benchmark_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        # Run a single task
        result = vl.run_benchmark(task_ids=["qa_explain"])
        assert result.total_tasks >= 1

    def test_evaluate_task_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        tr = vl.evaluate_task("qa_explain", response="Python is a language")
        assert tr.task_id == "qa_explain"

    def test_evaluate_task_not_found(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        tr = vl.evaluate_task("nonexistent", response="")
        assert not tr.success

    def test_score_benchmark_through_layer(self):
        from core.benchmark.runner import BenchmarkResult
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        tr = TaskResult(task_id="t1", category="qa", difficulty="easy", success=True, response="hello", score=90.0)
        br = BenchmarkResult(suite_name="test", total_tasks=1, passed=1, failed=0, task_results=[tr])
        sc = vl.score_benchmark(br)
        assert sc.overall_score > 0

    def test_release_evaluation_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        # Run a real task to get a proper result
        result = vl.run_benchmark(task_ids=["qa_explain"])
        gate_result = vl.evaluate_release(result)
        assert gate_result.decision in ("pass", "warn", "block")

    def test_chat_p12_flag(self):
        import py_compile

        py_compile.compile("core/chat.py", doraise=True)
