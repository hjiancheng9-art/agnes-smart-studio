"""Tests for browser_ai.py - platform configs and polling logic."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import browser_ai as ba


class TestPlatformConfig:
    REQUIRED_FIELDS = {"url", "input", "submit", "response", "stop_button"}

    def test_required_fields(self):
        for name, cfg in ba.PLATFORMS.items():
            missing = self.REQUIRED_FIELDS - set(cfg.keys())
            assert not missing, f"Platform '{name}' missing: {missing}"

    def test_url_valid(self):
        for _name, cfg in ba.PLATFORMS.items():
            assert cfg["url"].startswith("https://")


class TestNewFunctions:
    def test_count_messages_exists(self):
        assert hasattr(ba, "_count_messages")

    def test_read_response_accepts_platform(self):
        sig = inspect.signature(ba._read_response)
        assert "platform" in sig.parameters


class TestInterface:
    def test_send_to_ai_exists(self):
        assert hasattr(ba, "send_to_ai")

    def test_unknown_platform(self):
        result = ba.send_to_ai("nonexistent", "test")
        assert result.startswith("Unknown platform:")
