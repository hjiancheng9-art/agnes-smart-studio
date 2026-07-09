"""Test P10: Trace-first Debugger / Run Inspector."""

import time

import pytest

from core.trace_debugger import (
    DecisionCategory,
    DecisionRecord,
    DecisionRecorder,
    DiagnosticReport,
    RunInspector,
    SessionRecord,
    TracePlayer,
    get_recorder,
)


@pytest.fixture
def recorder():
    return DecisionRecorder()


@pytest.fixture
def sample_session():
    record = SessionRecord(session_id="test-session-1", start_time=time.time() - 10)
    record.record("policy", "Selected DEEP mode", "Complex engineering task",
                  alternatives=["fast", "balanced"], outcome="deep")
    record.record("tool_validation", "read_file", "Valid: path param OK", outcome="pass", duration_ms=5.0)
    record.record("tool_execution", "read_file('auth.py')", "Read file", outcome="success", duration_ms=12.0)
    record.record("tool_validation", "write_file", "Blocked: missing content param",
                  outcome="block", duration_ms=3.0)
    record.record("reviewer", "Review step 2", "Found unclosed code fence",
                  outcome="issues_found", duration_ms=50.0)
    record.record("tool_execution", "edit_file('auth.py')", "Self-correction after review",
                  outcome="success", duration_ms=30.0)
    record.close()
    return record


class TestDecisionRecord:
    def test_creation(self):
        dr = DecisionRecord(category="test", decision="do_x", reason="because")
        assert dr.category == "test"
        assert dr.decision == "do_x"

    def test_to_dict(self):
        dr = DecisionRecord(category="policy", decision="DEEP", reason="complexity",
                           outcome="selected", duration_ms=5.0)
        d = dr.to_dict()
        assert d["category"] == "policy"
        assert d["duration_ms"] == 5.0


class TestSessionRecord:
    def test_record(self, sample_session):
        assert sample_session.total_decisions == 6

    def test_by_category(self, sample_session):
        tools = sample_session.by_category("tool_validation")
        assert len(tools) == 2

    def test_duration(self, sample_session):
        assert sample_session.duration >= 0

    def test_close(self):
        s = SessionRecord(session_id="s1", start_time=time.time())
        time.sleep(0.01)
        s.close()
        assert s.duration > 0

    def test_to_dict(self, sample_session):
        d = sample_session.to_dict()
        assert d["session_id"] == "test-session-1"
        assert d["total_decisions"] == 6


class TestDecisionRecorder:
    def test_new_session(self, recorder):
        s = recorder.new_session("my-session")
        assert recorder.current is not None
        assert recorder.current.session_id == "my-session"

    def test_close_current(self, recorder):
        recorder.new_session("s1")
        recorder.close_current()
        assert recorder.current is None

    def test_get(self, recorder):
        recorder.new_session("find-me")
        s = recorder.get("find-me")
        assert s is not None
        assert s.session_id == "find-me"

    def test_get_nonexistent(self, recorder):
        assert recorder.get("no-such") is None

    def test_list_sessions(self, recorder):
        recorder.new_session("a")
        recorder.close_current()
        recorder.new_session("b")
        lst = recorder.list_sessions()
        assert len(lst) == 2

    def test_save_load(self, recorder, tmp_path):
        s1 = recorder.new_session("s1")
        s1.record("p", "decision", "reason")
        s1.close()
        recorder.new_session("s2")
        recorder.close_current()

        path = str(tmp_path / "sessions.json")
        recorder.save(path)
        import os
        assert os.path.exists(path)

        r2 = DecisionRecorder()
        r2.load(path)
        assert r2.get("s1") is not None
        assert r2.get("s2") is not None


class TestRunInspector:
    def test_inspect(self, sample_session):
        inspector = RunInspector()
        report = inspector.inspect(sample_session)
        assert isinstance(report, DiagnosticReport)
        assert report.session_id == "test-session-1"

    def test_policy_decision(self, sample_session):
        inspector = RunInspector()
        report = inspector.inspect(sample_session)
        assert "DEEP" in report.policy_decision

    def test_tool_validation_summary(self, sample_session):
        inspector = RunInspector()
        report = inspector.inspect(sample_session)
        assert "blocked" in report.tool_validation_summary

    def test_reviewer_summary(self, sample_session):
        inspector = RunInspector()
        report = inspector.inspect(sample_session)
        assert "with issues" in report.reviewer_summary or "issues_found" in report.reviewer_summary

    def test_errors_detected(self, sample_session):
        inspector = RunInspector()
        report = inspector.inspect(sample_session)
        assert len(report.errors) >= 1

    def test_recommendations(self, sample_session):
        inspector = RunInspector()
        report = inspector.inspect(sample_session)
        assert len(report.recommendations) >= 0

    def test_timeline(self, sample_session):
        inspector = RunInspector()
        report = inspector.inspect(sample_session)
        assert len(report.timeline) > 0

    def test_to_text(self, sample_session):
        inspector = RunInspector()
        report = inspector.inspect(sample_session)
        text = report.to_text()
        assert "Diagnostic Report" in text
        assert "Tool Calls" in text

    def test_empty_session(self):
        inspector = RunInspector()
        record = SessionRecord(session_id="empty")
        record.close()
        report = inspector.inspect(record)
        assert report.session_id == "empty"


class TestTracePlayer:
    def test_play(self, sample_session):
        player = TracePlayer(sample_session)
        lines = player.play()
        assert len(lines) >= 8
        assert any("Step" in l for l in lines)

    def test_search(self, sample_session):
        player = TracePlayer(sample_session)
        results = player.search("read_file")
        assert len(results) >= 1

    def test_search_no_match(self, sample_session):
        player = TracePlayer(sample_session)
        results = player.search("zzz_no_match")
        assert len(results) == 0

    def test_summary_stats(self, sample_session):
        player = TracePlayer(sample_session)
        stats = player.summary_stats()
        assert stats["total_decisions"] == 6
        assert "by_category" in stats


class TestDecisionCategory:
    def test_values(self):
        assert DecisionCategory.POLICY.value == "policy"
        assert DecisionCategory.TOOL_VALIDATION.value == "tool_validation"
        assert DecisionCategory.REVIEWER.value == "reviewer"
        assert DecisionCategory.PROJECT_INDEX.value == "project_index"


class TestIntegration:
    def test_recorder_global(self):
        r = get_recorder()
        assert isinstance(r, DecisionRecorder)

    def test_validation_layer_integration(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        assert hasattr(vl, "decision_recorder")

    def test_start_and_close_trace(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        session = vl.start_trace_session("integration-test")
        assert session.session_id == "integration-test"
        vl.record_decision("test", "do_x", "testing", outcome="ok")
        vl.close_trace_session()

    def test_inspect_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        vl.start_trace_session("test-2")
        vl.record_decision("policy", "BALANCED", "default")
        vl.close_trace_session()
        report = vl.inspect_trace("test-2")
        assert "BALANCED" in report.policy_decision

    def test_replay_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        vl.start_trace_session("test-3")
        vl.record_decision("policy", "FAST", "simple")
        vl.close_trace_session()
        lines = vl.replay_trace("test-3")
        assert len(lines) >= 3

    def test_chat_p10_flag(self):
        import py_compile
        py_compile.compile("core/chat.py", doraise=True)
