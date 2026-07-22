"""Tests for core/error_sink.py — unified exception recording."""

from __future__ import annotations

from core.error_sink import ErrorRecord, ErrorSink, catch, err, print_error_summary


class TestErrorRecord:
    """ErrorRecord dataclass construction."""

    def test_create_with_default_severity(self):
        record = ErrorRecord(
            timestamp="2024-01-01T00:00:00",
            module="test_module",
            operation="test_op",
            error_type="ValueError",
            message="something broke",
            traceback="",
            context={},
        )
        assert record.severity == "warning"
        assert record.module == "test_module"
        assert record.error_type == "ValueError"

    def test_create_with_custom_severity(self):
        record = ErrorRecord(
            timestamp="2024-01-01T00:00:00",
            module="test_module",
            operation="test_op",
            error_type="KeyError",
            message="missing key",
            traceback="",
            context={"key": "value"},
            severity="error",
        )
        assert record.severity == "error"
        assert record.context == {"key": "value"}


class TestErrorSinkRecord:
    """ErrorSink.record() — core recording logic."""

    def test_record_exception(self):
        sink = ErrorSink()
        try:
            raise ValueError("test error")
        except ValueError as e:
            record = sink.record("mod", "op", e)

        assert record.module == "mod"
        assert record.operation == "op"
        assert record.error_type == "ValueError"
        assert "test error" in record.message
        assert record.severity == "warning"
        assert len(sink) == 1

    def test_record_string_error(self):
        sink = ErrorSink()
        record = sink.record("mod", "op", "connection refused")
        assert record.error_type == "string"
        assert record.message == "connection refused"
        assert record.traceback == ""

    def test_record_with_context_and_severity(self):
        sink = ErrorSink()
        record = sink.record(
            "mod",
            "op",
            ValueError("bad"),
            context={"user": "alice"},
            severity="critical",
        )
        assert record.context == {"user": "alice"}
        assert record.severity == "critical"

    def test_record_none_error_still_saves(self):
        """record() doesn't filter None, only catch() does."""
        sink = ErrorSink()
        record = sink.record("mod", "op", None)  # type: ignore[arg-type]
        assert record.error_type == "string"
        assert record.message == "None"


class TestErrorSinkQuery:
    """ErrorSink query methods."""

    def test_recent_returns_in_insertion_order(self):
        sink = ErrorSink()
        sink.record("m", "op1", "first")
        sink.record("m", "op2", "second")
        recent = sink.recent(2)
        assert recent[0].operation == "op1"
        assert recent[1].operation == "op2"

    def test_recent_limits_count(self):
        sink = ErrorSink()
        for i in range(20):
            sink.record("m", f"op{i}", f"err{i}")
        assert len(sink.recent(5)) == 5

    def test_recent_filter_by_severity(self):
        sink = ErrorSink()
        sink.record("m", "op1", "debug", severity="debug")
        sink.record("m", "op2", "error", severity="error")
        result = sink.recent(10, severity="error")
        assert len(result) == 1
        assert result[0].severity == "error"

    def test_by_module(self):
        sink = ErrorSink()
        sink.record("mod_a", "op1", "err1")
        sink.record("mod_b", "op2", "err2")
        sink.record("mod_a", "op3", "err3")
        result = sink.by_module("mod_a")
        assert len(result) == 2

    def test_by_module_empty(self):
        sink = ErrorSink()
        assert sink.by_module("nonexistent") == []

    def test_stats_structure(self):
        sink = ErrorSink()
        sink.record("m", "op", ValueError("bad"), severity="error")
        sink.record("m", "op", TypeError("type"), severity="warning")
        stats = sink.stats()
        assert "total" in stats
        assert "by_severity" in stats
        assert "by_error_type" in stats
        assert "by_module" in stats
        assert stats["total"] == 2
        assert stats["by_severity"]["error"] == 1
        assert stats["by_severity"]["warning"] == 1

    def test_clear(self):
        sink = ErrorSink()
        sink.record("m", "op", "err")
        assert len(sink) == 1
        sink.clear()
        assert len(sink) == 0

    def test_len(self):
        sink = ErrorSink()
        assert len(sink) == 0
        sink.record("m", "op", "e1")
        sink.record("m", "op", "e2")
        assert len(sink) == 2


class TestCatchFunction:
    """catch() — drop-in replacement for bare except."""

    def test_catch_with_exception(self):
        """Records the exception and returns fallback."""
        err.clear()
        try:
            raise RuntimeError("boom")
        except RuntimeError as e:
            result = catch(e, "test_module", "test_op", fallback=42)
        assert result == 42
        assert len(err) >= 1

    def test_catch_with_none(self):
        """When error is None, do nothing."""
        err.clear()
        result = catch(None, "m", "op", fallback="default")
        assert result == "default"
        assert len(err) == 0

    def test_catch_with_severity(self):
        err.clear()
        try:
            raise ValueError("critical fail")
        except ValueError as e:
            result = catch(e, "m", "op", severity="critical", fallback=False)
        assert result is False
        recent = err.recent(1)
        assert recent[0].severity == "critical"


class TestPrintErrorSummary:
    """print_error_summary() smoke test."""

    def test_smoke(self, capsys):
        err.clear()
        err.record("m", "op", "test msg")
        print_error_summary()
        captured = capsys.readouterr()
        assert "ErrorSink" in captured.out
        assert "test msg" in captured.out
