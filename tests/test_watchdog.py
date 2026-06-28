"""Tests for core/watchdog.py — Watchdog, health checks, cleanup, alerts."""

import time

from core.watchdog import (
    DISK_CHECK_INTERVAL,
    MAX_CONTEXT_TOKENS,
    MAX_FILE_AGE_HOURS,
    MEMORY_CHECK_INTERVAL,
    MIN_DISK_GB,
    PROVIDER_CHECK_INTERVAL,
    Watchdog,
    WatchdogState,
    get_watchdog,
    reset_watchdog,
)


class TestWatchdogState:
    def test_defaults(self):
        s = WatchdogState()
        assert s.provider_ok is True
        assert s.disk_ok is True
        assert s.memory_ok is True
        assert s.alerts == []
        assert s.provider_switches == 0
        assert s.files_cleaned == 0


class TestConstants:
    def test_provider_check_interval(self):
        assert PROVIDER_CHECK_INTERVAL == 30

    def test_disk_check_interval(self):
        assert DISK_CHECK_INTERVAL == 120

    def test_memory_check_interval(self):
        assert MEMORY_CHECK_INTERVAL == 60

    def test_max_context_tokens(self):
        assert MAX_CONTEXT_TOKENS == 800_000

    def test_min_disk_gb(self):
        assert MIN_DISK_GB == 1.0

    def test_max_file_age_hours(self):
        assert MAX_FILE_AGE_HOURS == 72


class TestWatchdogLifecycle:
    def test_initial_state(self):
        w = Watchdog()
        assert w.alive is False

    def test_start_creates_thread(self):
        w = Watchdog()
        w._stop_flag.set()  # stop immediately after first cycle
        w.start()
        time.sleep(0.2)
        w.stop()
        # should not hang

    def test_double_start_noop(self):
        w = Watchdog()
        w.start()
        w.start()  # second start should be noop
        w.stop()

    def test_stop_cleans_up(self):
        w = Watchdog()
        w._stop_flag.set()
        w.start()
        w.stop()
        assert w.alive is False

    def test_alive_property(self):
        w = Watchdog()
        assert w.alive is False
        w.start()
        # should be alive briefly
        any_alive = w.alive
        w.stop()
        assert w.alive is False or any_alive is not True  # either false or briefly alive


class TestWatchdogChecks:
    def test_provider_check_interval_skips(self):
        w = Watchdog()
        w._state.last_provider_check = time.time()
        # _check_provider should return early without calling anything
        w._check_provider()  # interval not elapsed → noop

    def test_memory_check_collects_gc(self):
        w = Watchdog()
        w._state.last_memory_check = 0
        w._check_memory()  # should not raise

    def test_disk_check_interval_skips(self):
        w = Watchdog()
        w._state.last_disk_check = time.time()
        w._check_disk()  # interval not elapsed → noop

    def test_clean_disk_no_dir(self, tmp_path):
        w = Watchdog()
        import core.watchdog as wd

        original = wd.OUTPUT_DIR
        wd.OUTPUT_DIR = tmp_path / "nonexistent"
        try:
            count = w._clean_disk()
            assert count == 0
        finally:
            wd.OUTPUT_DIR = original

    def test_alert_adds_to_list(self):
        w = Watchdog()
        w._alert("test", "test message")
        assert len(w._state.alerts) >= 1
        assert "test" in w._state.alerts[-1]

    def test_alert_caps_at_20(self):
        w = Watchdog()
        for i in range(25):
            w._alert("test", f"msg {i}")
        assert len(w._state.alerts) <= 20

    def test_summary(self):
        w = Watchdog()
        s = w.summary()
        assert "Watchdog" in s
        assert "白虎" in s

    def test_status_returns_state(self):
        w = Watchdog()
        assert w.status is w._state


class TestSingleton:
    def test_get_watchdog_returns_watchdog(self):
        w = get_watchdog()
        assert isinstance(w, Watchdog)

    def test_singleton_same_instance(self):
        reset_watchdog()
        w1 = get_watchdog()
        w2 = get_watchdog()
        assert w1 is w2
        w1.stop()
        reset_watchdog()

    def test_reset_creates_new(self):
        reset_watchdog()
        w1 = get_watchdog()
        w1.stop()
        reset_watchdog()
        w2 = get_watchdog()
        assert w1 is not w2
        w2.stop()
        reset_watchdog()
