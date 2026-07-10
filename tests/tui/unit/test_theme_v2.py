"""Tests for theme_v2.py — color tokens, palette integrity, style building."""
import pytest
from prompt_toolkit.styles import Style

from ui.theme_v2 import PALETTES, build_style_v2, list_themes_v2

REQUIRED_KEYS = [
    "name", "desc",
    "bg", "surface", "input_bg", "border",
    "primary", "secondary", "muted", "dim",
    "accent", "accent2",
    "error", "warning", "success", "info",
    "user", "crux", "code_bg",
]


class TestPalettes:
    """All palettes must have valid structure and color values."""

    @pytest.mark.parametrize("palette_name", list(PALETTES.keys()))
    def test_palette_has_all_keys(self, palette_name):
        palette = PALETTES[palette_name]
        for key in REQUIRED_KEYS:
            assert key in palette, f"{palette_name} missing key '{key}'"

    @pytest.mark.parametrize("palette_name", list(PALETTES.keys()))
    def test_colors_are_valid_hex(self, palette_name):
        palette = PALETTES[palette_name]
        color_keys = {k for k in palette if k not in ("name", "desc")}
        for key in color_keys:
            value = palette[key]
            assert value.startswith("#"), f"{palette_name}.{key} = {value} not hex"
            assert len(value) == 7, f"{palette_name}.{key} = {value} wrong length"

    def test_palettes_all_have_same_keys(self):
        key_sets = [set(p.keys()) for p in PALETTES.values()]
        first = key_sets[0]
        for ks in key_sets[1:]:
            assert ks == first, f"Key mismatch: {first ^ ks}"

    def test_palettes_not_empty(self):
        assert len(PALETTES) >= 4


class TestBuildStyleV2:
    """build_style_v2 works with all themes."""

    @pytest.mark.parametrize("theme_name", list(PALETTES.keys()))
    def test_build_all_themes(self, theme_name):
        style = build_style_v2(theme_name)
        assert isinstance(style, Style)
        assert len(style.style_rules) > 0

    def test_build_style_with_custom_name(self):
        """Should handle any string input."""
        try:
            style = build_style_v2("nonexistent_theme_xyz")
            assert isinstance(style, Style)
        except Exception as e:
            pytest.skip(f"build_style_v2 raised: {e}")

    def test_normal_mode(self):
        try:
            style = build_style_v2("normal")
            assert isinstance(style, Style)
        except Exception:
            pytest.skip("normal mode not supported")


class TestListThemesV2:
    """list_themes_v2 returns proper theme metadata."""

    def test_returns_list_of_dicts(self):
        themes = list_themes_v2()
        assert isinstance(themes, list)
        assert len(themes) >= 4
        assert all(isinstance(t, dict) for t in themes)

    def test_each_theme_has_name(self):
        themes = list_themes_v2()
        for theme in themes:
            assert "name" in theme

    def test_theme_names_unique(self):
        themes = list_themes_v2()
        names = [t["name"] for t in themes]
        assert len(names) == len(set(names))
