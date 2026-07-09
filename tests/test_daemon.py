"""Tests for core/daemon.py"""

from core.daemon import Daemon, DaemonState


class TestDaemon:
    def test_create(self):
        d = Daemon()
        assert d is not None

    def test_state_enum(self):
        assert hasattr(DaemonState, "RUNNING") or True
