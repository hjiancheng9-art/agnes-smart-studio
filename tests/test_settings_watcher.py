"""Tests for core/settings_watcher.py"""

from core.settings_watcher import start_watcher, stop_watcher


class TestSettingsWatcher:
    def test_start_stop(self):
        start_watcher()
        stop_watcher()
        assert True

    def test_stop_twice(self):
        stop_watcher()
        stop_watcher()
        assert True
