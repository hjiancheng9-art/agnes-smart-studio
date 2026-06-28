"""Tests for core/beast_wiring.py — beast wiring, event handlers, summary."""

from core.beast_wiring import get_wiring_summary, wire_all


class TestWireAll:
    def test_returns_true(self):
        result = wire_all()
        assert result is True

    def test_idempotent(self):
        # Calling wire_all twice returns True both times (already wired)
        r1 = wire_all()
        r2 = wire_all()
        assert r1 is True
        assert r2 is True


class TestWiringSummary:
    def test_returns_string(self):
        result = get_wiring_summary()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_daemon_section(self):
        result = get_wiring_summary()
        assert "Daemon" in result

    def test_contains_plugins_section(self):
        result = get_wiring_summary()
        assert "Plugins" in result

    def test_summary_includes_watchdog_status(self):
        result = get_wiring_summary()
        # watchdog section always present (either alive or off)
        assert "watchdog" in result.lower()
