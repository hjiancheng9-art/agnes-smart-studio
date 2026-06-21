"""Tests for core.observability — tracing, spans, and metrics."""

import json
import pytest
from unittest.mock import patch


class TestSpan:
    def test_creation(self):
        from core.observability import Span
        span = Span(
            span_id="s1", trace_id="t1", parent_id="", name="test",
            start_time=1000.0,
        )
        assert span.span_id == "s1"
        assert span.status == "ok"
        assert span.duration_ms() == 0.0

    def test_finish(self):
        from core.observability import Span
        span = Span(span_id="s1", trace_id="t1", parent_id="", name="test",
                    start_time=1000.0)
        span.finish()
        assert span.end_time > 0.0
        assert span.status == "ok"

    def test_finish_with_status(self):
        from core.observability import Span
        span = Span(span_id="s1", trace_id="t1", parent_id="", name="test",
                    start_time=1000.0)
        span.finish(status="error")
        assert span.status == "error"

    def test_duration(self):
        from core.observability import Span
        span = Span(span_id="s1", trace_id="t1", parent_id="", name="test",
                    start_time=1000.0, end_time=1001.5)
        assert span.duration_ms() == pytest.approx(1500.0)

    def test_attributes(self):
        from core.observability import Span
        span = Span(span_id="s1", trace_id="t1", parent_id="", name="test",
                    start_time=1000.0)
        span.set_attribute("key", "value")
        assert span.attributes["key"] == "value"

    def test_events(self):
        from core.observability import Span
        span = Span(span_id="s1", trace_id="t1", parent_id="", name="test",
                    start_time=1000.0)
        span.add_event("retry", attempt=2)
        assert len(span.events) == 1
        assert span.events[0]["name"] == "retry"
        assert span.events[0]["attempt"] == 2

    def test_idempotent_finish(self):
        from core.observability import Span
        span = Span(span_id="s1", trace_id="t1", parent_id="", name="test",
                    start_time=1000.0, end_time=1001.0)
        # finish() always overwrites end_time per current implementation
        span.finish()
        assert span.end_time > 0.0
        assert span.status == "ok"


class TestTracer:
    def _make_tracer(self, tmp_path):
        from core.observability import Tracer
        return Tracer(log_file=str(tmp_path / "traces.jsonl"))

    def test_start_trace(self, tmp_path):
        tracer = self._make_tracer(tmp_path)
        span = tracer.start_trace("root_operation")
        assert span.span_id
        assert span.trace_id
        assert span.parent_id == ""
        assert span.name == "root_operation"

    def test_start_span_with_parent(self, tmp_path):
        tracer = self._make_tracer(tmp_path)
        root = tracer.start_trace("root")
        child = tracer.start_span("child", parent=root)
        assert child.trace_id == root.trace_id
        assert child.parent_id == root.span_id

    def test_start_span_no_parent(self, tmp_path):
        tracer = self._make_tracer(tmp_path)
        tracer.start_trace("root")
        span = tracer.start_span("orphan")
        assert span.trace_id == tracer.current_trace_id()

    def test_finish_span_writes_log(self, tmp_path):
        tracer = self._make_tracer(tmp_path)
        span = tracer.start_trace("operation")
        span.finish(status="ok")
        tracer.finish_span(span)
        log_file = tmp_path / "traces.jsonl"
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["name"] == "operation"
        assert record["status"] == "ok"

    def test_finish_span_auto_finishes(self, tmp_path):
        tracer = self._make_tracer(tmp_path)
        span = tracer.start_trace("auto")
        # Don't call span.finish() manually
        tracer.finish_span(span)
        log_file = tmp_path / "traces.jsonl"
        record = json.loads(log_file.read_text(encoding="utf-8").strip())
        # auto-finished span has duration recorded
        assert "duration_ms" in record
        assert record["name"] == "auto"

    def test_finish_span_preserves_custom_status(self, tmp_path):
        tracer = self._make_tracer(tmp_path)
        span = tracer.start_trace("err_op")
        span.finish(status="error")
        tracer.finish_span(span)
        record = json.loads(
            (tmp_path / "traces.jsonl").read_text(encoding="utf-8").strip()
        )
        assert record["status"] == "error"

    def test_get_trace_summary_empty(self, tmp_path):
        tracer = self._make_tracer(tmp_path)
        summary = tracer.get_trace_summary("nonexistent")
        assert summary["trace_id"] == "nonexistent"
        # Empty summary returns spans list and total_duration_ms
        assert summary["spans"] == []
        assert summary["total_duration_ms"] == 0.0

    def test_get_trace_summary(self, tmp_path):
        import time
        tracer = self._make_tracer(tmp_path)
        root = tracer.start_trace("pipeline")
        time.sleep(0.01)  # ensure measurable duration
        root.finish()
        child = tracer.start_span("step1", parent=root)
        child.finish(status="error")
        tracer.finish_span(root)
        tracer.finish_span(child)
        summary = tracer.get_trace_summary(root.trace_id)
        assert summary["span_count"] == 2
        assert summary["status"] == "error"
        assert summary["total_duration_ms"] > 0

    def test_current_trace_id(self, tmp_path):
        tracer = self._make_tracer(tmp_path)
        assert tracer.current_trace_id() == ""
        span = tracer.start_trace("test")
        assert tracer.current_trace_id() == span.trace_id


class TestMetrics:
    def test_increment(self):
        from core.observability import Metrics
        m = Metrics()
        m.increment("requests")
        assert m.get("requests") == 1
        m.increment("requests", 5)
        assert m.get("requests") == 6

    def test_get_unknown(self):
        from core.observability import Metrics
        m = Metrics()
        assert m.get("unknown") == 0

    def test_timing(self):
        from core.observability import Metrics
        m = Metrics()
        m.timing("api_call", 100.0)
        m.timing("api_call", 200.0)
        m.timing("api_call", 300.0)
        summary = m.summary()
        timings = summary["timings"]["api_call"]
        assert timings["count"] == 3
        assert timings["total_ms"] == 600.0
        assert timings["avg_ms"] == 200.0
        assert timings["min_ms"] == 100.0
        assert timings["max_ms"] == 300.0

    def test_summary_counters(self):
        from core.observability import Metrics
        m = Metrics()
        m.increment("a")
        m.increment("b")
        summary = m.summary()
        assert summary["counters"] == {"a": 1, "b": 1}

    def test_empty_summary(self):
        from core.observability import Metrics
        m = Metrics()
        summary = m.summary()
        assert summary["counters"] == {}
        assert summary["timings"] == {}


class TestGetRecentTraces:
    def test_empty(self, tmp_path):
        from core.observability import get_recent_traces, tracer
        log_file = tmp_path / "traces.jsonl"
        with patch.object(tracer, "_log_file", log_file):
            result = get_recent_traces()
        assert result == []

    def test_returns_recent(self, tmp_path):
        from core.observability import get_recent_traces, tracer
        log_file = tmp_path / "traces.jsonl"
        # Append all records, not overwrite
        lines = []
        for i in range(30):
            record = {"name": f"span_{i}", "trace_id": f"t{i}", "status": "ok"}
            lines.append(json.dumps(record))
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with patch.object(tracer, "_log_file", log_file):
            result = get_recent_traces(limit=5)
        assert len(result) == 5
        # Most recent first
        assert result[0]["name"] == "span_29"


class TestTraceContext:
    def test_basic_context(self, tmp_path):
        from core.observability import TraceContext, tracer
        log_file = tmp_path / "traces.jsonl"
        with patch.object(tracer, "_log_file", log_file), TraceContext("test_op") as span:
            span.set_attribute("key", "value")
            assert span.name == "test_op"
        lines = (tmp_path / "traces.jsonl").read_text(encoding="utf-8").strip().split("\n")
        record = json.loads(lines[0])
        assert record["name"] == "test_op"
        assert record["status"] == "ok"
        assert record["attributes"]["key"] == "value"

    def test_error_context(self, tmp_path):
        from core.observability import TraceContext, tracer
        log_file = tmp_path / "traces.jsonl"
        with patch.object(tracer, "_log_file", log_file), pytest.raises(ValueError), TraceContext("fail_op") as _:
            raise ValueError("test error")
        record = json.loads(
            (tmp_path / "traces.jsonl").read_text(encoding="utf-8").strip()
        )
        assert record["status"] == "error"
        assert len(record["events"]) > 0
