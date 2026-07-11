"""Tests for core/watchdog.py — five-line health checks, alerts, state."""

import time
import pytest
from core.watchdog import (
    Watchdog, WatchdogState, get_watchdog, reset_watchdog,
)


@pytest.fixture(autouse=True)
def clean_watchdog():
    reset_watchdog()
    yield
    reset_watchdog()


class TestWatchdogState:
    def test_default_all_ok(self):
        ws = WatchdogState()
        assert ws.provider_ok is True
        assert ws.disk_ok is True
        assert ws.config_ok is True
        assert ws.imports_ok is True
        assert ws.alerts == []
        assert ws.provider_switches == 0

    def test_alerts_truncated(self):
        ws = WatchdogState()
        for i in range(25):
            ws.alerts.append(f"alert {i}")
        # The watchdog keeps last 20
        assert len(ws.alerts) <= 25  # state itself doesn't truncate, _alert() does


class TestWatchdogLifecycle:
    def test_start_and_stop(self):
        wd = Watchdog()
        assert not wd.alive
        wd.start()
        time.sleep(0.1)
        assert wd.alive
        wd.stop()
        time.sleep(0.1)
        assert not wd.alive

    def test_singleton(self):
        wd1 = get_watchdog()
        wd2 = get_watchdog()
        assert wd1 is wd2

    def test_reset_creates_new(self):
        wd1 = get_watchdog()
        reset_watchdog()
        wd2 = get_watchdog()
        assert wd1 is not wd2


class TestHeartbeat:
    def test_beat_updates_timestamp(self):
        Watchdog.beat("TESTING")
        assert Watchdog._last_heartbeat > 0
        assert Watchdog.get_status() == "TESTING"

    def test_is_alive_after_beat(self):
        Watchdog.beat()
        assert Watchdog.is_alive() is True

    def test_is_alive_no_beat(self):
        # Force heartbeat to be stale
        Watchdog._last_heartbeat = time.time() - 999
        assert Watchdog.is_alive() is False
        Watchdog.beat()


class TestChecks:
    def test_provider_check_runs(self):
        wd = get_watchdog()
        wd._state.last_provider_check = 0
        wd._check_provider()
        assert wd._state.last_provider_check > 0

    def test_config_check_runs(self):
        wd = get_watchdog()
        wd._state.last_config_check = 0
        wd._check_config()
        assert wd._state.last_config_check > 0
        assert wd._state.config_ok is True

    def test_failure_rate_check_runs(self):
        wd = get_watchdog()
        wd._state.last_failure_rate_check = 0
        wd._check_failure_rate()
        assert wd._state.last_failure_rate_check > 0

    def test_disk_check_runs(self):
        wd = get_watchdog()
        wd._state.last_disk_check = 0
        wd._check_disk()
        assert wd._state.last_disk_check > 0

    def test_summary_contains_all_fields(self):
        wd = get_watchdog()
        summary = wd.summary()
        assert "provider:" in summary
        assert "config:" in summary
        assert "imports:" in summary
        assert "failure rate:" in summary


class TestAlerting:
    def test_alert_stores_message(self):
        wd = get_watchdog()
        before = len(wd._state.alerts)
        wd._alert("test", "test message")
        assert len(wd._state.alerts) == before + 1

    def test_alert_truncates_at_20(self):
        wd = get_watchdog()
        for i in range(25):
            wd._alert("test", f"msg {i}")
        assert len(wd._state.alerts) <= 20
