"""Tests for theme_v2.py — single unified color scheme, accessibility modes, style building."""
import pytest
from prompt_toolkit.styles.base import BaseStyle

from ui.theme_v2 import BLADE as COLORS
from ui.theme_v2 import build_style_v2

REQUIRED_COLOR_KEYS = [
    "bg", "surface", "input_bg", "border",
    "primary", "secondary", "muted", "dim",
    "accent", "accent2",
    "error", "warning", "success", "info",
    "user", "crux", "code_bg",
]


class TestColors:
    """The single unified COLORS dict must be well-formed."""

    def test_colors_has_all_keys(self):
        for key in REQUIRED_COLOR_KEYS:
            assert key in COLORS, f"COLORS missing key '{key}'"

    def test_colors_are_valid_hex(self):
        for key in REQUIRED_COLOR_KEYS:
            value = COLORS[key]
            assert value.startswith("#"), f"COLORS.{key} = {value} not hex"
            assert len(value) == 7, f"COLORS.{key} = {value} wrong length"

    def test_colors_not_empty(self):
        assert len(COLORS) >= len(REQUIRED_COLOR_KEYS)


class TestBuildStyleV2:
    """build_style_v2 works with all accessibility modes."""

    @pytest.mark.parametrize("mode", ["normal", "high_contrast", "mono"])
    def test_build_all_modes(self, mode):
        style = build_style_v2(mode)
        assert isinstance(style, BaseStyle)
        assert len(style.style_rules) > 0

    def test_build_default_mode(self):
        """Default (no arg) should produce a valid BaseStyle."""
        style = build_style_v2()
        assert isinstance(style, BaseStyle)

    def test_unknown_mode_falls_back(self):
        """Unknown mode string should fall back to normal style."""
        style = build_style_v2("nonexistent_mode_xyz")
        assert isinstance(style, BaseStyle)
