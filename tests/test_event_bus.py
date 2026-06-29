"""Tests for core/event_bus.py — pub/sub central nervous system."""

import pytest
from core.event_bus import EventBus, bus


class TestEventBus:
    def test_on_and_emit(self):
        eb = EventBus()
        received = []

        eb.on("test.event", lambda **kw: received.append(kw))
        eb.emit("test.event", data=42)

        assert len(received) == 1
        assert received[0] == {"data": 42}

    def test_multiple_handlers_same_event(self):
        eb = EventBus()
        results = []

        eb.on("e", lambda **kw: results.append(1))
        eb.on("e", lambda **kw: results.append(2))
        eb.emit("e")

        assert results == [1, 2]

    def test_once_handler_auto_removed(self):
        eb = EventBus()
        calls = []

        eb.once("e", lambda **kw: calls.append("once"))
        eb.emit("e")
        assert len(calls) == 1

        eb.emit("e")
        assert len(calls) == 1  # not called again

    def test_once_and_on_coexist(self):
        eb = EventBus()
        calls = []

        eb.on("e", lambda **kw: calls.append("on"))
        eb.once("e", lambda **kw: calls.append("once"))
        eb.emit("e")

        assert calls == ["on", "once"]

    def test_off_removes_on_handler(self):
        eb = EventBus()
        calls = []

        def h(**kw):
            calls.append(1)

        eb.on("e", h)
        eb.off("e", h)
        eb.emit("e")

        assert calls == []

    def test_off_removes_once_handler(self):
        eb = EventBus()
        calls = []

        def h(**kw):
            calls.append(1)

        eb.once("e", h)
        eb.off("e", h)
        eb.emit("e")

        assert calls == []

    def test_emit_unknown_event_noop(self):
        eb = EventBus()
        eb.emit("nonexistent", x=1)  # should not raise

    def test_handler_exception_does_not_block_others(self):
        eb = EventBus()
        results = []

        def bad(**kw):
            raise ValueError("boom")

        def good(**kw):
            results.append("ok")

        eb.on("e", bad)
        eb.on("e", good)
        eb.emit("e")  # should not raise

        assert results == ["ok"]

    def test_clear_removes_all(self):
        eb = EventBus()
        calls = []

        eb.on("a", lambda **kw: calls.append("a"))
        eb.once("b", lambda **kw: calls.append("b"))
        eb.clear()

        eb.emit("a")
        eb.emit("b")

        assert calls == []

    def test_off_nonexistent_handler_noop(self):
        eb = EventBus()

        def h(**kw):
            pass

        eb.off("e", h)  # should not raise

    def test_multiple_events_independent(self):
        eb = EventBus()
        a_calls, b_calls = [], []

        eb.on("a", lambda **kw: a_calls.append(1))
        eb.on("b", lambda **kw: b_calls.append(1))
        eb.emit("a")
        eb.emit("b")

        assert len(a_calls) == 1
        assert len(b_calls) == 1

    def test_kwargs_passed_to_handler(self):
        eb = EventBus()
        captured = {}

        def h(**kw):
            captured.update(kw)

        eb.on("e", h)
        eb.emit("e", tool_name="write_file", args={"path": "/tmp/x"})

        assert captured.get("tool_name") == "write_file"
        assert captured["args"] == {"path": "/tmp/x"}


class TestGlobalBus:
    def test_global_bus_is_event_bus(self):
        assert isinstance(bus, EventBus)

    def test_global_bus_reusable(self):
        bus.clear()
        calls = []
        bus.on("test", lambda **kw: calls.append(1))
        bus.emit("test")
        assert calls == [1]
        bus.clear()


class TestZCodeEventConstants:
    """ZCode Protocol v1 事件常量完整性。"""

    def test_session_events_exist(self):
        from core.event_bus import SESSION_CREATED, SESSION_RESUMED, SESSION_UPDATED, SESSION_CLOSED
        assert SESSION_CREATED == "session:created"
        assert SESSION_RESUMED == "session:resumed"
        assert SESSION_UPDATED == "session:updated"
        assert SESSION_CLOSED == "session:closed"

    def test_turn_events_exist(self):
        from core.event_bus import TURN_STARTED, TURN_COMPLETED, TURN_FAILED
        assert TURN_STARTED == "turn:started"
        assert TURN_COMPLETED == "turn:completed"
        assert TURN_FAILED == "turn:failed"

    def test_message_events_exist(self):
        from core.event_bus import MESSAGE_UPSERTED, MESSAGE_REMOVED
        assert MESSAGE_UPSERTED == "message:upserted"
        assert MESSAGE_REMOVED == "message:removed"

    def test_part_events_exist(self):
        from core.event_bus import PART_STARTED, PART_DELTA, PART_UPSERTED, PART_REMOVED
        assert PART_STARTED == "part:started"
        assert PART_DELTA == "part:delta"
        assert PART_UPSERTED == "part:upserted"
        assert PART_REMOVED == "part:removed"

    def test_model_tool_events_exist(self):
        from core.event_bus import MODEL_STREAMING, TOOL_BEFORE, TOOL_AFTER, TOOL_UPDATED
        assert MODEL_STREAMING == "model:streaming"
        assert TOOL_BEFORE == "tool:before"
        assert TOOL_AFTER == "tool:after"
        assert TOOL_UPDATED == "tool:updated"

    def test_resource_events_exist(self):
        from core.event_bus import PERMISSION_REQUESTED, PERMISSION_RESOLVED
        from core.event_bus import USER_INPUT_REQUESTED, USER_INPUT_RESOLVED
        assert PERMISSION_REQUESTED == "permission:requested"

    def test_crux_extension_events_exist(self):
        from core.event_bus import FILE_CHANGED, ERROR, SESSION_START, SESSION_END, SESSION_METRICS
        assert FILE_CHANGED == "file:changed"
        assert ERROR == "error"


class TestZCodeSessionLifecycle:
    """ZCode Session 生命周期事件流。"""

    def test_session_created_emitted(self):
        bus.clear()
        captured = []
        bus.on("session:created", lambda **kw: captured.append(kw))
        bus.emit("session:created", workspace="/test", model="deepseek-v4-flash")
        assert len(captured) == 1
        assert captured[0]["workspace"] == "/test"

    def test_turn_lifecycle(self):
        bus.clear()
        events = []
        bus.on("turn:started", lambda **kw: events.append("started"))
        bus.on("turn:completed", lambda **kw: events.append("completed"))
        bus.emit("turn:started", message="hi")
        bus.emit("turn:completed", tokens=42)
        assert events == ["started", "completed"]

    def test_turn_failed_event(self):
        bus.clear()
        captured = []
        bus.on("turn:failed", lambda **kw: captured.append(kw))
        bus.emit("turn:failed", error="rate_limit", retry_after=5)
        assert len(captured) == 1
        assert captured[0]["error"] == "rate_limit"


class TestZCodeMetrics:
    """ZCode Agent 指标自动追踪。"""

    def setup_method(self):
        bus.reset_metrics()

    def test_session_created_increments_metric(self):
        bus.emit("session:created", workspace="/a")
        m = bus.get_metrics()
        assert m["total_sessions"] == 1

    def test_session_resumed_increments_metric(self):
        bus.emit("session:resumed", session_id="abc")
        m = bus.get_metrics()
        assert m["total_sessions"] == 1

    def test_turn_started_increments_metric(self):
        bus.emit("turn:started")
        bus.emit("turn:started")
        m = bus.get_metrics()
        assert m["total_turns"] == 2

    def test_tool_updated_increments_metric(self):
        bus.emit("tool:updated", tool_name="write_file")
        m = bus.get_metrics()
        assert m["tool_call_count"] == 1

    def test_metrics_dict_has_all_keys(self):
        m = bus.get_metrics()
        expected_keys = {
            "total_sessions", "total_turns", "tool_call_count",
            "tool_error_rate", "model_error_rate",
            "cache_hit_rate", "cache_read_tokens",
            "avg_time_to_first_token_ms", "avg_turn_duration_ms",
            "active_days",
        }
        assert expected_keys.issubset(m.keys())

    def test_reset_metrics_returns_to_zero(self):
        bus.emit("session:created")
        bus.emit("session:created")
        bus.emit("turn:started")
        bus.reset_metrics()
        m = bus.get_metrics()
        assert m["total_sessions"] == 0
        assert m["total_turns"] == 0
        assert m["tool_call_count"] == 0
        assert m["tool_error_rate"] == 0.0

    def test_metrics_is_copy_not_reference(self):
        m1 = bus.get_metrics()
        m2 = bus.get_metrics()
        m1["total_sessions"] = 999
        assert m2["total_sessions"] != 999


class TestZCodePartEvents:
    """Part 层级流式事件。"""

    def test_part_streaming_lifecycle(self):
        bus.clear()
        parts = []

        bus.on("part:started", lambda **kw: parts.append(("started", kw)))
        bus.on("part:delta", lambda **kw: parts.append(("delta", kw)))
        bus.on("part:upserted", lambda **kw: parts.append(("upserted", kw)))

        bus.emit("part:started", part_id=1, kind="text")
        bus.emit("part:delta", part_id=1, text="Hel")
        bus.emit("part:delta", part_id=1, text="lo")
        bus.emit("part:upserted", part_id=1, text="Hello")

        assert len(parts) == 4
        assert parts[0][0] == "started"
        assert parts[1][0] == "delta"
        assert parts[-1][0] == "upserted"

    def test_part_removed_event(self):
        bus.clear()
        captured = []
        bus.on("part:removed", lambda **kw: captured.append(kw))
        bus.emit("part:removed", part_id=1, reason="edited")
        assert len(captured) == 1
        assert captured[0]["reason"] == "edited"
