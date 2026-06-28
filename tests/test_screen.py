"""Tests for ui/screen.py — BootScreen and helpers."""

from unittest.mock import MagicMock, patch

from ui.screen import BootScreen, render_boot


class TestBootScreen:
    def test_render_static_does_not_raise(self):
        with patch("ui.screen.console.print"), \
             patch("ui.screen.time.sleep", return_value=None):
            BootScreen.render(v="v9.9", animate=False)

    def test_render_animate_does_not_raise(self):
        with patch("ui.screen.console.print"), \
             patch("ui.screen.console.clear"), \
             patch("ui.screen.time.sleep", return_value=None):
            BootScreen.render(animate=True)


class TestRenderBoot:
    def test_static_does_not_raise(self):
        with patch("ui.screen.console.print"), \
             patch("ui.screen.time.sleep", return_value=None):
            render_boot(animate=False)
