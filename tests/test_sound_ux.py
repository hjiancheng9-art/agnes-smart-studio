"""Tests for core/sound_ux.py — Sound effects system, toggle, graceful degradation."""

import sys
from unittest.mock import patch

from core.sound_ux import SOUND_DIR, SoundUX


class TestSoundDir:
    def test_dir_exists(self):
        assert SOUND_DIR.exists()


class TestToggle:
    def test_default_enabled(self):
        assert SoundUX.toggle() is True

    def test_disable(self):
        SoundUX.toggle(False)
        assert SoundUX.toggle() is False
        SoundUX.toggle(True)  # restore

    def test_toggle_on(self):
        SoundUX.toggle(True)
        assert SoundUX.toggle() is True

    def test_toggle_returns_current(self):
        SoundUX.toggle(False)
        result = SoundUX.toggle(None)
        assert result is False
        SoundUX.toggle(True)  # restore

    def test_toggle_explicit_none_does_not_change(self):
        SoundUX.toggle(True)
        SoundUX.toggle(None)
        assert SoundUX.toggle() is True


class TestClassState:
    def test_lock_exists(self):
        assert hasattr(SoundUX, "_lock")

    def test_enabled_flag(self):
        assert hasattr(SoundUX, "_enabled")
        assert isinstance(SoundUX._enabled, bool)


class TestPlayDisabled:
    def test_play_noop_when_disabled(self):
        SoundUX.toggle(False)
        with patch("threading.Thread.start") as mock_start:
            SoundUX._play("test", 0.1)
            mock_start.assert_not_called()
        SoundUX.toggle(True)  # restore


class TestSoundMethodsNoCrash:
    """Verify sound methods handle ImportError gracefully (winsound unavailable)."""

    def test_success_does_not_raise(self):
        SoundUX.success()  # should not raise even without winsound

    def test_error_does_not_raise(self):
        SoundUX.error()

    def test_alert_does_not_raise(self):
        SoundUX.alert()

    def test_alchemy_does_not_raise(self):
        SoundUX.alchemy()

    def test_beep_fallback_does_not_raise(self):
        SoundUX._beep_fallback()

    def test_startup_is_async_noop(self):
        SoundUX.startup()  # spawns thread, should not raise


class TestWin32Paths:
    """Test win32-specific code paths when winsound IS available."""

    def test_success_with_winsound_mock(self):
        mock_winsound = type("winsound", (), {"Beep": lambda self, freq, dur: None})()
        with patch.dict(sys.modules, {"winsound": mock_winsound}):
            SoundUX.success()  # should use Beep

    def test_error_with_winsound_mock(self):
        mock_winsound = type("winsound", (), {"Beep": lambda self, freq, dur: None})()
        with patch.dict(sys.modules, {"winsound": mock_winsound}):
            SoundUX.error()

    def test_alert_with_winsound_mock(self):
        mock_winsound = type("winsound", (), {"Beep": lambda self, freq, dur: None})()
        with patch.dict(sys.modules, {"winsound": mock_winsound}):
            SoundUX.alert()

    def test_alchemy_with_winsound_mock(self):
        mock_winsound = type("winsound", (), {"Beep": lambda self, freq, dur: None})()
        with patch.dict(sys.modules, {"winsound": mock_winsound}):
            SoundUX.alchemy()

    def test_beep_fallback_with_winsound(self):
        mock_winsound = type("winsound", (), {"Beep": lambda self, freq, dur: None})()
        with patch.dict(sys.modules, {"winsound": mock_winsound}), \
             patch("sys.platform", "win32"):
            SoundUX._beep_fallback()


class TestNonWin32Beep:
    def test_beep_fallback_linux(self):
        with patch("sys.platform", "linux"), \
             patch("sys.stdout") as mock_out:
            SoundUX._beep_fallback()
            assert mock_out.write.called
            assert mock_out.flush.called
