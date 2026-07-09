"""Tests for core/event_log — EventLog 可观测性地基."""

from __future__ import annotations

from core.event_log import EventLog, EventRecord


class TestEventRecord:
    def test_create_record(self):
        rec = EventRecord(intent="tool_call", tool="gen", session_id="test-001", status="success")
        assert rec.intent == "tool_call"
        assert rec.session_id == "test-001"
        assert rec.status == "success"

    def test_record_defaults(self):
        rec = EventRecord()
        assert rec.session_id == ""
        assert rec.intent == ""
        assert rec.duration_ms == 0

    def test_record_with_error(self):
        rec = EventRecord(intent="gen", status="failed", error_type="timeout", duration_ms=30000)
        assert rec.status == "failed"
        assert rec.error_type == "timeout"

    def test_record_with_metadata(self):
        rec = EventRecord(intent="test", metadata={"key": "value"})
        assert rec.metadata["key"] == "value"


class TestEventLog:
    def test_create_log(self):
        log = EventLog()
        assert log is not None

    def test_record_event(self):
        log = EventLog()
        log.record(intent="test_event", tool="test")
        assert log.buffer_size >= 1

    def test_multiple_records(self):
        log = EventLog()
        for i in range(5):
            log.record(intent=f"event_{i}", tool="test")
        assert log.buffer_size == 5

    def test_query_events_all(self):
        log = EventLog()
        log.record(intent="tool_call", tool="a")
        log.record(intent="model_call", tool="b")
        results = log.query_events()
        assert len(results) >= 2

    def test_query_events_with_intent(self):
        log = EventLog()
        log.record(intent="find_me", tool="x")
        log.record(intent="other", tool="y")
        results = log.query_events(intent="find_me")
        assert len(results) >= 1

    def test_query_events_limit(self):
        log = EventLog()
        for i in range(20):
            log.record(intent="ev", tool=str(i))
        results = log.query_events(limit=5)
        assert len(results) == 5

    def test_recent_failures_api(self):
        log = EventLog()
        failures = log.recent_failures(hours=48)
        assert isinstance(failures, list)
        log.record(intent="test_fail", tool="x", status="failed", error_type="err")
        assert isinstance(log.recent_failures(hours=48), list)

    def test_query_metrics(self):
        log = EventLog()
        log.record(intent="gen", tool="comfyui", status="success", duration_ms=500)
        assert log.query_metrics() is not None

    def test_force_flush(self):
        log = EventLog()
        log.record(intent="flush_test", tool="x")
        log.force_flush()

    def test_shutdown(self):
        log = EventLog()
        log.record(intent="shutdown_test", tool="x")
        log.shutdown()
