"""
TDD tests for CRUX TUI v2 — Protocol (core/protocol.py)
"""
from __future__ import annotations

import json

from core.protocol import (
    Event,
    EventBus,
    EventType,
    SessionState,
    emit,
    emit_state,
    get_bus,
)


class TestEventBus:
    """EventBus pub/sub core."""

    def test_basic_pub_sub(self):
        bus = EventBus()
        received = []
        bus.subscribe("message.*", lambda e: received.append(e))
        bus.publish(Event(EventType.MESSAGE_SENT.value, {"text": "hello"}))
        assert len(received) == 1
        assert received[0].type == EventType.MESSAGE_SENT.value
        assert received[0].data == {"text": "hello"}

    def test_wildcard_matching(self):
        bus = EventBus()
        count = []
        bus.subscribe("*", lambda e: count.append(1))
        bus.publish(Event(EventType.TOOL_CALLED.value, {}))
        bus.publish(Event(EventType.AGENT_STARTED.value, {}))
        assert len(count) == 2

    def test_named_matching(self):
        bus = EventBus()
        tool_events = []
        bus.subscribe("tool.*", lambda e: tool_events.append(e))
        bus.publish(Event(EventType.TOOL_CALLED.value, {}))
        bus.publish(Event(EventType.MESSAGE_SENT.value, {}))
        assert len(tool_events) == 1
        assert tool_events[0].type == EventType.TOOL_CALLED.value

    def test_history_cap(self):
        bus = EventBus()
        bus._history_max = 10
        for i in range(15):
            bus.publish(Event(EventType.MESSAGE_SENT.value, {"i": i}))
        assert len(bus._history) == 10
        assert bus._history[-1].data["i"] == 14

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        def cb(e):
            received.append(e)
        bus.subscribe("tool.*", cb)
        bus.publish(Event(EventType.TOOL_CALLED.value, {}))
        assert len(received) == 1
        bus.unsubscribe("tool.*", cb)
        bus.publish(Event(EventType.TOOL_CALLED.value, {}))
        assert len(received) == 1  # unsubscribe worked, no new events


class TestSessionState:
    """State snapshot serialization."""

    def test_default_state(self):
        s = SessionState()
        d = s.to_dict()
        assert d["model"] == ""
        assert not d["streaming"]

    def test_populated_state(self):
        s = SessionState(
            model="deepseek-v4", context_pct=75.5,
            streaming=True, active_agents=2, tool_status="executing"
        )
        d = s.to_dict()
        assert d["model"] == "deepseek-v4"
        assert d["context_pct"] == 75.5
        assert d["active_agents"] == 2

    def test_json_roundtrip(self):
        s = SessionState(model="test", context_pct=42.0)
        raw = s.to_json()
        parsed = json.loads(raw)
        assert parsed["model"] == "test"
        assert parsed["context_pct"] == 42.0


class TestGlobalBus:
    """Singleton and convenience helpers."""

    def test_singleton(self):
        bus1 = get_bus()
        bus2 = get_bus()
        assert bus1 is bus2

    def test_emit_state(self):
        emit_state(model="gpt-4", thinking=True)
        state = get_bus().latest_state
        assert state is not None
        assert state.model == "gpt-4"
        assert state.thinking

    def test_emit(self):
        emit(EventType.MODEL_CHANGED, {"model": "claude"})
        history = get_bus().get_history(limit=1)
        assert history[0].type == EventType.MODEL_CHANGED.value
