"""Tests for core.notify — desktop notification system."""

from unittest.mock import patch, MagicMock


class TestNotifier:
    def test_creation_detects_os(self):
        from core.notify import Notifier
        with patch("core.notify.platform.system", return_value="Windows"):
            n = Notifier()
        assert n._os == "Windows"
        # _available is a bool regardless of platform detection
        assert isinstance(n._available, bool)

    def test_check_available_windows(self):
        from core.notify import Notifier
        n = Notifier.__new__(Notifier)
        n._os = "Windows"
        with patch("core.notify.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert n._check_available() is True
        with patch("core.notify.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert n._check_available() is False

    def test_check_available_handles_exception(self):
        from core.notify import Notifier
        n = Notifier.__new__(Notifier)
        n._os = "Darwin"
        import subprocess
        with patch("core.notify.subprocess.run", side_effect=subprocess.SubprocessError):
            assert n._check_available() is False

    def test_send_noop_when_unavailable(self):
        from core.notify import Notifier
        n = Notifier.__new__(Notifier)
        n._os = "Windows"
        n._available = False
        # Should not raise even with no command available
        with patch("core.notify.subprocess.Popen") as mock_popen:
            n.send("title", "message")
            mock_popen.assert_not_called()

    def test_send_windows_invokes_powershell(self):
        from core.notify import Notifier
        n = Notifier.__new__(Notifier)
        n._os = "Windows"
        n._available = True
        with patch("core.notify.subprocess.Popen") as mock_popen:
            n.send("Hello", "World")
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert args[0] == "powershell"

    def test_send_escapes_injection_chars(self):
        """Title/message with shell metacharacters must be escaped."""
        from core.notify import Notifier
        n = Notifier.__new__(Notifier)
        n._os = "Darwin"
        n._available = True
        with patch("core.notify.subprocess.Popen") as mock_popen:
            n.send('evil"', 'msg$`')
            cmd = mock_popen.call_args[0][0]
            # The escaped title should contain backslash-quote, not raw quote payload
            joined = " ".join(cmd)
            assert '\\"' in joined or '"evil' not in joined


class TestNotifyFunctions:
    def test_notify_delegates_to_singleton(self):
        from core import notify as notify_mod
        with patch.object(notify_mod._notifier, "send") as mock_send:
            notify_mod.notify("T", "M", urgent=True)
            mock_send.assert_called_once_with("T", "M", True)

    def test_notify_task_done_known_type(self):
        from core import notify as notify_mod
        with patch.object(notify_mod._notifier, "send") as mock_send:
            notify_mod.notify_task_done("video")
            args = mock_send.call_args[0]
            assert args[0] == "Video Ready"

    def test_notify_task_done_unknown_type(self):
        from core import notify as notify_mod
        with patch.object(notify_mod._notifier, "send") as mock_send:
            notify_mod.notify_task_done("mystery")
            args = mock_send.call_args[0]
            assert args[0] == "Task Complete"
            assert "mystery" in args[1]

    def test_notify_task_done_uses_result(self):
        from core import notify as notify_mod
        with patch.object(notify_mod._notifier, "send") as mock_send:
            notify_mod.notify_task_done("self_evolve", "3 fixes applied")
            args = mock_send.call_args[0]
            assert args[1] == "3 fixes applied"
