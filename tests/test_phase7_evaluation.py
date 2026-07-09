"""Test P7: Evaluation & Replay System."""

import os
import time

import pytest

from core.evaluation import (
    BehavioralGrader,
    DeterministicGrader,
    EvalEngine,
    EvalResult,
    EvalWorkspace,
    RegressionDiff,
    RegressionGuard,
    Scorecard,
    SessionTrace,
)


@pytest.fixture
def sample_trace():
    t = SessionTrace(session_id="test-session-1", start_time=time.time() - 60)
    t.record("session_start")
    t.record("user_message", data={"content": "Read auth.py"})
    t.record("tool_call", data={"tool": "read_file", "args": {"path": "auth.py"}})
    t.record("validation", duration_ms=5.0, data={"result": "pass"})
    t.record("tool_result", data={"tool": "read_file", "success": True})
    t.record("assistant_message", data={"content": "Here is auth.py:\n\ndef login(): pass"})
    t.record("reviewer_run", duration_ms=50.0, data={"issues": 0})
    t.record("user_message", data={"content": "Fix the bug"})
    t.record("tool_call", data={"tool": "edit_file", "args": {}})
    t.record("validation_block", data={"reason": "missing param"})
    t.record("assistant_message", data={"content": "Fixed"})
    t.close()
    return t


@pytest.fixture
def trace_with_errors():
    t = SessionTrace(session_id="test-session-2", start_time=time.time() - 30)
    t.record("session_start")
    t.record("user_message", data={"content": "Do something"})
    t.record("validation_block", data={"reason": "unknown tool"})
    t.record("validation_block", data={"reason": "bad params"})
    t.record("assistant_message", data={"content": ""})  # empty response
    t.record("consistency_issue", data={"description": "tool fail not mentioned"})
    t.close()
    return t


# ── SessionTrace ────────────────────────────────────────────────────


class TestSessionTrace:
    def test_record_event(self, sample_trace):
        assert sample_trace.event_count >= 10

    def test_duration(self, sample_trace):
        assert sample_trace.duration > 0

    def test_save_load(self, sample_trace, tmp_path):
        path = str(tmp_path / "trace.json")
        sample_trace.save(path)
        assert os.path.exists(path)
        loaded = SessionTrace.load(path)
        assert loaded.session_id == "test-session-1"
        assert loaded.event_count == sample_trace.event_count

    def test_to_dict(self, sample_trace):
        d = sample_trace.to_dict()
        assert d["session_id"] == "test-session-1"
        assert "events" in d
        assert d["event_count"] >= 10

    def test_close(self):
        t = SessionTrace(session_id="test", start_time=time.time())
        t.close()
        assert t.end_time > 0

    def test_record_with_data(self):
        t = SessionTrace(session_id="test")
        t.record("custom_event", duration_ms=12.5, data={"key": "value"})
        assert t.events[0].type == "custom_event"
        assert t.events[0].duration_ms == 12.5


# ── DeterministicGrader ─────────────────────────────────────────────


class TestDeterministicGrader:
    def test_grade_tool_calls(self, sample_trace):
        dg = DeterministicGrader()
        r = dg.grade_tool_calls(sample_trace)
        assert r["total_calls"] >= 2
        assert r["valid_rate"] > 0

    def test_grade_tool_calls_with_blocks(self, trace_with_errors):
        dg = DeterministicGrader()
        r = dg.grade_tool_calls(trace_with_errors)
        assert r["blocked_calls"] >= 2
        assert r["valid_rate"] <= 0

    def test_grade_response_empty_detected(self, trace_with_errors):
        dg = DeterministicGrader()
        r = dg.grade_response_quality(trace_with_errors)
        assert r["empty_messages"] >= 1

    def test_grade_response_normal(self, sample_trace):
        dg = DeterministicGrader()
        r = dg.grade_response_quality(sample_trace)
        assert r["total_messages"] >= 1
        assert "Here is" in str(r) or r["avg_response_length"] > 0

    def test_grade_full(self, sample_trace):
        dg = DeterministicGrader()
        r = dg.grade(sample_trace)
        assert "valid_rate" in r
        assert "total_messages" in r


# ── BehavioralGrader ────────────────────────────────────────────────


class TestBehavioralGrader:
    def test_self_correction_recovery(self, sample_trace):
        bg = BehavioralGrader()
        r = bg.grade_self_correction(sample_trace)
        # validation_block exists, followed by valid tool_call
        assert isinstance(r["recovery_rate"], float)

    def test_consistency_issues(self, trace_with_errors):
        bg = BehavioralGrader()
        r = bg.grade_consistency(trace_with_errors)
        assert r["consistency_issues"] >= 1

    def test_efficiency(self, sample_trace):
        bg = BehavioralGrader()
        r = bg.grade_efficiency(sample_trace)
        assert r["total_tool_calls"] >= 2

    def test_grade_full(self, sample_trace):
        bg = BehavioralGrader()
        r = bg.grade(sample_trace)
        assert "recovery_rate" in r
        assert "consistency_issues" in r
        assert "tool_calls_per_turn" in r


# ── Scorecard ───────────────────────────────────────────────────────


class TestScorecard:
    def test_compute_overall_default(self):
        sc = Scorecard(total_sessions=1)
        score = sc.compute_overall()
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_compute_overall_high(self):
        sc = Scorecard(
            task_success_rate=0.95,
            tool_call_valid_rate=0.95,
            self_correction_recovery_rate=0.8,
            total_sessions=5,
        )
        score = sc.compute_overall()
        assert score > 50

    def test_compute_overall_low(self):
        sc = Scorecard(
            task_success_rate=0.1,
            tool_call_valid_rate=0.1,
            total_sessions=5,
        )
        score = sc.compute_overall()
        assert score < 50

    def test_to_dict(self):
        sc = Scorecard(total_sessions=3)
        d = sc.to_dict()
        assert "overall_score" in d
        assert d["total_sessions"] == 3

    def test_summary(self):
        sc = Scorecard(total_sessions=2, task_success_rate=0.85)
        sc.compute_overall()
        s = sc.summary()
        assert "Scorecard" in s
        assert "85" in s.replace("%", "")


# ── EvalEngine ──────────────────────────────────────────────────────


class TestEvalEngine:
    def test_evaluate_session(self, sample_trace):
        engine = EvalEngine()
        result = engine.evaluate_session(sample_trace)
        assert isinstance(result, EvalResult)
        assert result.session_id == "test-session-1"
        assert result.score > 0

    def test_evaluate_multiple(self, sample_trace, trace_with_errors):
        engine = EvalEngine()
        sc = engine.evaluate([sample_trace, trace_with_errors])
        assert sc.total_sessions == 2
        assert sc.overall_score > 0

    def test_results_summary(self, sample_trace, trace_with_errors):
        engine = EvalEngine()
        engine.evaluate([sample_trace, trace_with_errors])
        s = engine.results_summary()
        assert "Session Results" in s

    def test_aggregation(self, sample_trace, trace_with_errors):
        engine = EvalEngine()
        sc = engine.evaluate([sample_trace, trace_with_errors])
        assert sc.tool_call_valid_rate >= 0
        assert sc.avg_tool_calls_per_task >= 0
        assert sc.avg_retries_per_task >= 0


# ── RegressionGuard ─────────────────────────────────────────────────


class TestRegressionGuard:
    def test_no_change(self):
        sc = Scorecard(total_sessions=1, task_success_rate=0.8)
        sc.compute_overall()
        guard = RegressionGuard()
        diff = guard.compare(sc, sc, threshold=0.01)
        assert diff.score_diff == 0.0

    def test_regression_detected(self):
        before = Scorecard(total_sessions=1, task_success_rate=0.9, tool_call_valid_rate=0.9)
        before.compute_overall()
        after = Scorecard(total_sessions=1, task_success_rate=0.5, tool_call_valid_rate=0.9)
        after.compute_overall()
        guard = RegressionGuard()
        diff = guard.compare(before, after, threshold=0.05)
        assert len(diff.regressions) >= 1

    def test_improvement_detected(self):
        before = Scorecard(total_sessions=1, task_success_rate=0.5)
        before.compute_overall()
        after = Scorecard(total_sessions=1, task_success_rate=0.9)
        after.compute_overall()
        guard = RegressionGuard()
        diff = guard.compare(before, after, threshold=0.05)
        assert len(diff.improvements) >= 1

    def test_summary(self):
        diff = RegressionDiff(score_diff=-5.2, regressions=["tool_call_valid_rate: 0.9 → 0.7 (-0.20)"])
        s = diff.summary()
        assert "Regression Guard" in s
        assert "🔻" in s


# ── EvalWorkspace ───────────────────────────────────────────────────


class TestEvalWorkspace:
    def test_save_and_list(self, sample_trace, tmp_path):
        ws = EvalWorkspace(traces_dir=str(tmp_path / "traces"))
        path = ws.save_trace(sample_trace)
        assert os.path.exists(path)
        traces = ws.list_traces()
        assert len(traces) >= 1
        assert traces[0]["id"] == "test-session-1"

    def test_load(self, sample_trace, tmp_path):
        ws = EvalWorkspace(traces_dir=str(tmp_path / "traces2"))
        ws.save_trace(sample_trace)
        loaded = ws.load_trace("test-session-1")
        assert loaded is not None
        assert loaded.session_id == "test-session-1"

    def test_load_nonexistent(self):
        ws = EvalWorkspace(traces_dir="/nonexistent/path")
        loaded = ws.load_trace("no-such-trace")
        assert loaded is None

    def test_run_eval(self, sample_trace, trace_with_errors, tmp_path):
        ws = EvalWorkspace(traces_dir=str(tmp_path / "traces3"))
        ws.save_trace(sample_trace)
        ws.save_trace(trace_with_errors)
        sc = ws.run_eval()
        assert sc.total_sessions == 2
        assert sc.overall_score > 0


# ── Integration ──────────────────────────────────────────────────────


class TestIntegration:
    def test_full_pipeline(self, sample_trace, trace_with_errors):
        """Full pipeline: record → evaluate → scorecard → regression guard."""
        engine = EvalEngine()
        sc = engine.evaluate([sample_trace, trace_with_errors])
        assert sc.total_sessions == 2
        assert sc.overall_score > 0

        # Regression guard
        guard = RegressionGuard()
        diff = guard.compare(sc, sc)
        assert diff.score_diff == 0.0

        # Summary
        summary = sc.summary()
        assert "Scorecard" in summary

    def test_workspace_to_eval(self, sample_trace, tmp_path):
        ws = EvalWorkspace(traces_dir=str(tmp_path / "traces4"))
        ws.save_trace(sample_trace)
        sc = ws.run_eval()
        assert sc.total_sessions >= 1
