"""Tests for core/event_bus — event system."""

from __future__ import annotations

import pytest
from core.event_bus import EventBus
from core.event_log_bridge import TOOL_CALL_COMPLETE, TOOL_CALL_FAILED, TOOL_CALL_START


class TestEventBus:
    def test_events_exist(self):
        assert TOOL_CALL_COMPLETE == "tool_call:complete"
        assert TOOL_CALL_FAILED == "tool_call:failed"
        assert TOOL_CALL_START == "tool_call:start"

    def test_event_bus_singleton(self):
        eb = EventBus()
        assert eb is not None

    def test_on_and_emit(self):
        eb = EventBus()
        received = []

        def handler(**kwargs):
            received.append(kwargs)

        eb.on("test:event", handler)
        eb.emit("test:event", data=42)
        assert len(received) > 0
        assert received[0].get("data") == 42
