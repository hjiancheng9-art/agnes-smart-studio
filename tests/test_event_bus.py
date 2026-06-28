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
