"""Unit tests for core.tool_outcome — ToolOutcome and related types."""

from __future__ import annotations

from core.tool_outcome import RecoveryAction, ToolOutcome, ToolStatus


class TestToolOutcome:
    def test_success(self):
        o = ToolOutcome.success("done", tool_name="t1")
        assert o.status == ToolStatus.SUCCEEDED
        assert o.value == "done"
        assert o.tool_name == "t1"
        assert o.failure is None

    def test_success_default_tool_name(self):
        o = ToolOutcome.success("ok")
        assert o.tool_name == ""

    def test_failure_of(self):
        o = ToolOutcome.failure_of("ERR", "something wrong", tool_name="t2")
        assert o.status == ToolStatus.FAILED
        assert o.failure.code == "ERR"
        assert o.failure.message == "something wrong"
        assert o.tool_name == "t2"

    def test_failure_with_recovery(self):
        o = ToolOutcome.failure_of("TIMEOUT", "timeout", recovery=RecoveryAction.RETRY_AFTER_DELAY)
        assert o.failure.recovery == RecoveryAction.RETRY_AFTER_DELAY

    def test_timeout(self):
        o = ToolOutcome.timeout(tool_name="slow", message="too slow")
        assert o.status == ToolStatus.TIMED_OUT
        assert o.failure.code == "tool.timeout"

    def test_cancelled(self):
        o = ToolOutcome.cancelled("t3")
        assert o.status == ToolStatus.CANCELLED

    def test_unknown_side_effect(self):
        o = ToolOutcome.unknown_side_effect("t4", "might have happened")
        assert o.status == ToolStatus.UNKNOWN
        assert o.failure.side_effect_certain is False

    def test_duration_is_recorded(self):
        o = ToolOutcome.success("x")
        assert o.duration_ms >= 0

    def test_attempt_default_one(self):
        o = ToolOutcome.success("x")
        assert o.attempt == 1
