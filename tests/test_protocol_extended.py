"""Tests for core/protocol — EventBus and Event system."""

from __future__ import annotations

from core.protocol import Event, EventBus, get_bus


class TestEvent:
    def test_event_creation(self):
        e = Event(type="session_created", data={"session_id": "test-123"})
        assert e.type == "session_created"
        assert e.data["session_id"] == "test-123"

    def test_event_default_source(self):
        e = Event(type="test_event", data={})
        assert e.source == "engine"


class TestEventBus:
    def test_singleton(self):
        bus = get_bus()
        assert bus is not None

    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe("test:event", handler)
        bus.publish(Event(type="test:event", data={"key": "value"}))
        assert len(received) > 0
        assert received[0].data["key"] == "value"

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        def handler(event):
            received.append(True)

        bus.subscribe("test:off", handler)
        bus.unsubscribe("test:off", handler)
        bus.publish(Event(type="test:off", data={}))
        assert len(received) == 0
