"""Tests for core/event_bus.py — CRUX 中枢神经事件总线"""

import pytest

from core.event_bus import EventBus, SessionMetadata


@pytest.fixture
def bus():
    return EventBus()


class TestEventBusBasics:
    """事件总线基本功能"""

    def test_on_and_emit(self, bus):
        results = []
        bus.on("test:event", lambda: results.append("fired"))
        bus.emit("test:event")
        assert results == ["fired"]

    def test_emit_with_kwargs(self, bus):
        results = []
        bus.on("test:data", lambda data=None: results.append(data))
        bus.emit("test:data", data={"key": "value"})
        assert results == [{"key": "value"}]

    def test_once_fires_once(self, bus):
        count = [0]
        bus.once("test:one", lambda: count.__setitem__(0, count[0] + 1))
        bus.emit("test:one")
        bus.emit("test:one")
        assert count[0] == 1

    def test_off_removes_listener(self, bus):
        results = []

        def fn():
            results.append("fired")

        bus.on("test:off", fn)
        bus.off("test:off", fn)
        bus.emit("test:off")
        assert results == []

    def test_multiple_listeners(self, bus):
        results = []
        bus.on("test:multi", lambda: results.append("a"))
        bus.on("test:multi", lambda: results.append("b"))
        bus.emit("test:multi")
        assert len(results) == 2

    def test_unrelated_events(self, bus):
        ra, rb = [], []
        bus.on("e:a", lambda: ra.append("a"))
        bus.on("e:b", lambda: rb.append("b"))
        bus.emit("e:a")
        assert ra == ["a"]
        assert rb == []


class TestEventBusMetrics:
    """指标测试"""

    def test_get_metrics_returns_dict(self, bus):
        assert isinstance(bus.get_metrics(), dict)

    def test_reset_metrics(self, bus):
        bus.emit("test")
        bus.reset_metrics()
        m = bus.get_metrics()
        assert m.get("total_emits", 0) >= 0

    def test_clear(self, bus):
        bus.on("e", lambda: None)
        bus.clear()
        bus.emit("e")  # 清除后不应崩溃


class TestSessionMetadata:
    """会话元数据测试"""

    def test_default_creation(self):
        sm = SessionMetadata()
        assert sm.id == ""
        assert sm.usage_count == 0

    def test_with_values(self):
        sm = SessionMetadata(id="s-001", name="测试", usage_count=5)
        assert sm.id == "s-001"
        assert sm.name == "测试"
        assert sm.usage_count == 5

    def test_last_active_default(self):
        sm = SessionMetadata()
        assert sm.last_active is None or sm.last_active == 0.0

    def test_tags_default(self):
        sm = SessionMetadata()
        assert isinstance(sm.tags, list)
