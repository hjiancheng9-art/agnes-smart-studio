"""Tests for core/daemon.py — DaemonState, Daemon, command handling, singleton."""

import json
import time
from unittest.mock import patch

from core.daemon import (
    Daemon,
    DaemonState,
    get_daemon,
    reset_daemon,
    STATE_FILE,
)


class TestDaemonState:
    def test_defaults(self):
        s = DaemonState()
        assert s.pid == 0
        assert s.started_at == 0.0
        assert s.sessions_active == 0
        assert s.total_sessions == 0

    def test_to_dict(self):
        s = DaemonState(pid=42, started_at=100.0)
        d = s.to_dict()
        assert d["pid"] == 42
        assert d["schema_version"] == "crux.daemon.v1"

    def test_uptime_in_dict(self):
        s = DaemonState(started_at=time.time() - 10)
        d = s.to_dict()
        assert d["uptime"] >= 9  # ~10s uptime


class TestDaemon:
    def test_initial_state(self):
        d = Daemon()
        assert d.is_running is False
        assert d.state.pid > 0  # os.getpid()

    def test_start_stop(self):
        d = Daemon()
        with patch.object(d, "_serve", return_value=None):
            ok = d.start(background=False)
            assert ok is True
            assert d.is_running is True
            d.stop()
            assert d.is_running is False

    def test_double_start_returns_false(self):
        d = Daemon()
        with patch.object(d, "_serve", return_value=None):
            d.start()
            ok2 = d.start()
            assert ok2 is False
            d.stop()

    def test_double_stop_noop(self):
        d = Daemon()
        d.stop()  # should not raise
        d.stop()  # should not raise

    def test_handle_command_attach(self):
        d = Daemon()
        resp = json.loads(d._handle_command("attach"))
        assert resp["ok"] is True
        assert resp["session"] == 1
        # second attach
        resp2 = json.loads(d._handle_command("attach"))
        assert resp2["session"] == 2

    def test_handle_command_detach(self):
        d = Daemon()
        d._handle_command("attach")
        d._handle_command("attach")
        resp = json.loads(d._handle_command("detach"))
        assert resp["ok"] is True
        assert resp["session"] == 1

    def test_handle_command_detach_below_zero(self):
        d = Daemon()
        resp = json.loads(d._handle_command("detach"))
        assert resp["session"] == 0  # clamped at 0

    def test_handle_command_status(self):
        d = Daemon()
        d.state.started_at = time.time()
        resp = json.loads(d._handle_command("status"))
        assert "pid" in resp
        assert "uptime" in resp

    def test_handle_command_unknown(self):
        d = Daemon()
        resp = json.loads(d._handle_command("bogus"))
        assert resp["ok"] is False
        assert "unknown" in resp["error"]

    def test_handle_command_empty_defaults_to_status(self):
        d = Daemon()
        resp = json.loads(d._handle_command(""))
        assert "pid" in resp

    def test_attach_detach_methods(self):
        d = Daemon()
        assert d.attach() is True
        assert d.state.sessions_active == 1
        assert d.state.total_sessions == 1
        d.detach()
        assert d.state.sessions_active == 0

    def test_summary(self):
        d = Daemon()
        s = d.summary()
        assert "Daemon" in s

    def test_save_state(self):
        d = Daemon()
        d.state.started_at = time.time()
        d._save_state()
        assert STATE_FILE.exists()


class TestSingleton:
    def test_get_daemon_returns_daemon(self):
        d = get_daemon()
        assert isinstance(d, Daemon)

    def test_singleton_same_instance(self):
        reset_daemon()
        d1 = get_daemon()
        d2 = get_daemon()
        assert d1 is d2
        reset_daemon()

    def test_reset_daemon_creates_new(self):
        reset_daemon()
        d1 = get_daemon()
        reset_daemon()
        d2 = get_daemon()
        assert d1 is not d2
        reset_daemon()
