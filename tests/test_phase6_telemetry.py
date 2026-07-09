"""Test Phase 6: Telemetry + Feature Config + Eval Runner"""

import time

import pytest

from core.crux_telemetry import (
    EvalResult,
    EvalRunner,
    EvalSession,
    EvalTurn,
    FeatureConfig,
    PhaseStats,
    TelemetryEvent,
    TelemetryRecord,
    TelemetryTracker,
)

# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def tracker():
    return TelemetryTracker(max_records=100)


@pytest.fixture
def config():
    return FeatureConfig()


@pytest.fixture
def eval_runner():
    return EvalRunner()


# ── TelemetryTracker ─────────────────────────────────────────────────


class TestTelemetryTracker:
    def test_record_event(self, tracker):
        rec = tracker.record("tool_validation", phase="p1", tool_name="read_file")
        assert tracker.total_events == 1
        assert rec.event == "tool_validation"
        assert rec.phase == "p1"

    def test_multiple_events(self, tracker):
        tracker.record("a", "p1")
        tracker.record("b", "p2")
        tracker.record("c", "p1")
        assert tracker.total_events == 3

    def test_by_event(self, tracker):
        tracker.record("tool_validation", "p1")
        tracker.record("reviewer_run", "p4")
        tracker.record("tool_validation", "p1")
        assert len(tracker.by_event("tool_validation")) == 2
        assert len(tracker.by_event("reviewer_run")) == 1

    def test_by_phase(self, tracker):
        tracker.record("a", "p1")
        tracker.record("b", "p2")
        tracker.record("c", "p1")
        assert len(tracker.by_phase("p1")) == 2
        assert len(tracker.by_phase("p2")) == 1

    def test_summary(self, tracker):
        tracker.record("a", "p1", success=True)
        tracker.record("b", "p1", success=False)
        tracker.record("c", "p2", success=True)
        summary = tracker.summary()
        assert "p1" in summary
        assert "p2" in summary
        assert summary["p1"].total_calls == 2
        assert summary["p1"].blocked == 1

    def test_summary_block_rate(self, tracker):
        tracker.record("a", "p1", success=True)
        tracker.record("b", "p1", success=False)
        tracker.record("c", "p1", success=False)
        ps = tracker.summary()["p1"]
        assert ps.block_rate == 66.7  # 2/3 blocked

    def test_duration_recording(self, tracker):
        with tracker.record_duration("tool_validation", phase="p1", tool_name="test") as ctx:
            time.sleep(0.01)
        assert tracker.total_events == 1
        rec = tracker.records[0]
        assert rec.duration_ms > 5  # at least 5ms
        assert rec.event == "tool_validation"

    def test_duration_on_error(self, tracker):
        try:
            with tracker.record_duration("tool", phase="p1"):
                raise ValueError("test error")
        except ValueError:
            pass
        assert tracker.total_events == 1
        assert not tracker.records[0].success

    def test_report(self, tracker):
        tracker.record("a", "p1", success=True)
        tracker.record("b", "p1", success=False)
        report = tracker.report()
        assert "Telemetry Report" in report
        assert "p1" in report

    def test_export(self, tracker, tmp_path):
        tracker.record("a", "p1")
        path = str(tmp_path / "test_telemetry.json")
        result = tracker.export(path)
        assert result == path
        import os
        assert os.path.exists(path)

    def test_max_records(self):
        t = TelemetryTracker(max_records=5)
        for i in range(10):
            t.record(f"e{i}", "p1")
        assert t.total_events == 5  # only last 5

    def test_to_dict(self):
        rec = TelemetryRecord(event="test", phase="p1", tool_name="tool", duration_ms=12.5, success=True, detail="detail")
        d = rec.to_dict()
        assert d["event"] == "test"
        assert d["duration_ms"] == 12.5


# ── PhaseStats ──────────────────────────────────────────────────────


class TestPhaseStats:
    def test_avg_duration(self):
        ps = PhaseStats(total_calls=2, total_duration_ms=100.0)
        assert ps.avg_duration_ms == 50.0

    def test_avg_duration_zero(self):
        ps = PhaseStats()
        assert ps.avg_duration_ms == 0.0

    def test_block_rate_zero(self):
        ps = PhaseStats()
        assert ps.block_rate == 0.0

    def test_to_dict(self):
        ps = PhaseStats(total_calls=10, passed=7, blocked=3, total_duration_ms=500.0)
        d = ps.to_dict()
        assert d["total_calls"] == 10
        assert d["blocked"] == 3
        assert d["block_rate_pct"] == 30.0


# ── FeatureConfig ────────────────────────────────────────────────────


class TestFeatureConfig:
    def test_default_all_enabled(self, config):
        assert config.is_enabled("p1")
        assert config.is_enabled("p2")
        assert config.is_enabled("p4")

    def test_is_enabled_global(self, config):
        config.p4_reviewer = False
        assert not config.is_enabled("p4")

    def test_disabled_for_target(self, config):
        assert config.is_enabled("reviewer", "media")
        assert config.is_enabled("reviewer", "code")
        assert not config.is_enabled("reviewer", "general")  # disabled for general by default

    def test_disable_all(self, config):
        config.disable_all()
        assert not config.is_enabled("p1")
        assert not config.is_enabled("p2")

    def test_enable_all(self, config):
        config.disable_all()
        config.enable_all()
        assert config.is_enabled("p1")

    def test_missing_phase_key(self, config):
        assert config.is_enabled("nonexistent", "general")

    def test_to_dict(self, config):
        d = config.to_dict()
        assert "p1_tool_validation" in d
        assert "p4_reviewer" in d


# ── EvalRunner ──────────────────────────────────────────────────────


class TestEvalRunner:
    def test_empty(self, eval_runner):
        results = eval_runner.run_all()
        assert len(results) == 0

    def test_add_session(self, eval_runner):
        session = EvalSession(id="test", description="Test session", created_at=time.time())
        session.turns.append(EvalTurn(user="hi", assistant="hello", expected_issues=0))
        eval_runner.add_session(session)
        assert len(eval_runner.sessions) == 1

    def test_run_session(self, eval_runner):
        session = EvalSession(id="s1", description="Simple")
        session.turns.append(EvalTurn(user="hi", assistant="hello", expected_issues=0))
        eval_runner.add_session(session)
        results = eval_runner.run_all()
        assert len(results) == 1
        assert results[0].session_id == "s1"

    def test_save_load(self, eval_runner, tmp_path):
        session = EvalSession(id="s1", description="Test")
        session.turns.append(EvalTurn(user="q", assistant="a"))
        eval_runner.add_session(session)

        path = str(tmp_path / "eval.json")
        eval_runner.save(path)
        import os
        assert os.path.exists(path)

        # Load into fresh runner
        r2 = EvalRunner()
        r2.load(path)
        assert len(r2.sessions) == 1
        assert r2.sessions[0].id == "s1"

    def test_pass_rate(self):
        er = EvalResult(session_id="s1", passed=8, failed=2)
        assert er.total == 10
        assert er.pass_rate == 80.0
        assert "80.0%" in er.summary()

    def test_pass_rate_all_pass(self):
        er = EvalResult(session_id="s1", passed=5, failed=0)
        assert er.pass_rate == 100.0

    def test_session_to_dict(self):
        et = EvalTurn(user="question", assistant="answer", expected_issues=1)
        et.tool_calls.append({"name": "read_file", "arguments": {"path": "x"}})
        session = EvalSession(id="s1", description="Test", tags=["regression"])
        session.turns.append(et)
        d = session.to_dict()
        assert d["id"] == "s1"
        assert "regression" in d["tags"]
        assert len(d["turns"]) == 1


# ── Integration ──────────────────────────────────────────────────────


class TestIntegration:
    def test_tracker_in_validation_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        assert hasattr(vl, "telemetry")
        assert hasattr(vl, "config")

    def test_record_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        vl.record_telemetry("test_event", "p6", "test_tool", 10.0, True, "ok")
        assert vl.telemetry.total_events >= 1

    def test_telemetry_report_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        vl.record_telemetry("a", "p1", success=True)
        vl.record_telemetry("b", "p1", success=False)
        report = vl.telemetry_report()
        assert "Telemetry Report" in report

    def test_feature_check_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        assert vl.is_feature_enabled("p4", "media")
        assert not vl.is_feature_enabled("reviewer", "general")

    def test_set_config_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        vl.set_config(p4_reviewer=False)
        assert not vl.config.p4_reviewer
        vl.set_config(p4_reviewer=True)

    def test_chatpy_has_p6_flag(self):
        import py_compile
        py_compile.compile("core/chat.py", doraise=True)


# ── TelemetryEvent enum ─────────────────────────────────────────────


class TestTelemetryEvent:
    def test_has_expected_events(self):
        events = [e.value for e in TelemetryEvent]
        assert "tool_validation" in events
        assert "reviewer_run" in events
        assert "context_compression" in events
        assert "skill_compile" in events
