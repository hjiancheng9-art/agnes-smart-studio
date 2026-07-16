"""Tests for activity log (_log_append, _log_update_last, etc.) in TuiAppV2."""

import threading

import pytest


class TestActivityLog:
    @pytest.fixture
    def app(self):
        """Create a minimal TuiAppV2 instance for log testing."""
        from ui.tui_v2 import TuiAppV2
        app = object.__new__(TuiAppV2)
        app._activity_log = []
        app._activity_lock = threading.RLock()
        app._activity_log_limit = 200
        app._app = None
        return app

    def test_log_append_single(self, app):
        app._log_append(("✓", "class:activity-done", "Task completed"))
        assert len(app._activity_log) == 1
        assert app._activity_log[0] == ("✓", "class:activity-done", "Task completed")

    def test_log_append_multiple(self, app):
        for i in range(5):
            app._log_append(("·", "class:activity-info", f"Event {i}"))
        assert app._log_count() == 5

    def test_log_last(self, app):
        app._log_append(("●", "class:activity-running", "Running"))
        app._log_append(("✓", "class:activity-done", "Done"))
        last = app._log_last()
        assert last == ("✓", "class:activity-done", "Done")

    def test_log_last_empty(self, app):
        assert app._log_last() is None

    def test_log_update_last(self, app):
        app._log_append(("●", "class:activity-running", "exec tool"))
        app._log_update_last(("✓", "class:activity-done", "tool"))
        last = app._log_last()
        assert last[0] == "✓"

    def test_log_update_last_empty(self, app):
        app._log_update_last(("✓", "class:activity-done", "x"))
        assert app._activity_log == []

    def test_log_clear(self, app):
        for i in range(5):
            app._log_append(("·", "", f"msg {i}"))
        app._log_clear()
        assert app._log_count() == 0

    def test_log_limit_enforced(self, app):
        app._activity_log_limit = 5
        for i in range(10):
            app._log_append(("·", "", f"msg {i}"))
        assert app._log_count() <= 5
        assert "msg 9" in app._log_snapshot()[-1][2]

    def test_log_snapshot(self, app):
        for i in range(10):
            app._log_append(("·", "", f"msg {i}"))
        snap = app._log_snapshot(limit=3)
        assert len(snap) == 3
        assert snap[-1][2] == "msg 9"

    def test_log_thread_safety(self, app):
        """Concurrent writes should not corrupt the log. Limit is 200."""
        # Disable log limit for this test
        app._activity_log_limit = 1000
        errors = []

        def writer():
            try:
                for i in range(100):
                    app._log_append(("·", "", f"thread-msg-{i}"))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"Thread errors: {errors}"
        assert app._log_count() == 400
