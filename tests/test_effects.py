"""Tests for ui/effects.py — terminal animation effects."""

import sys
from unittest.mock import patch

from ui.effects import (
    divider,
    fade_in,
    progress_bar,
    splash_screen,
    success_pulse,
    thinking_dots,
    typewriter,
)


class TestFadeIn:
    def test_runs_without_error(self):
        with patch("ui.effects.time.sleep"):
            fade_in("test", duration=0.01, steps=2)


class TestSuccessPulse:
    def test_runs_without_error(self):
        with patch("ui.effects.time.sleep"), \
             patch("sys.stdout.write"), \
             patch("sys.stdout.flush"):
            success_pulse(count=1, interval=0.01)


class TestThinkingDots:
    def test_runs_without_error(self):
        with patch("ui.effects.time.sleep"), \
             patch("sys.stdout.write"), \
             patch("sys.stdout.flush"):
            thinking_dots(count=1, interval=0.01)


class TestProgressBar:
    def test_returns_progress_and_task(self):
        p, task = progress_bar("Loading", 100.0)
        assert p is not None
        assert task is not None


class TestTypewriter:
    def test_returns_immediately_for_empty(self):
        result = typewriter("", delay=0.01)
        assert result is None  # empty text returns None


class TestSplashScreen:
    def test_runs_without_error(self):
        with patch("ui.effects.time.sleep"):
            splash_screen()


class TestDivider:
    def test_does_not_raise(self):
        divider()  # prints to console, returns None
