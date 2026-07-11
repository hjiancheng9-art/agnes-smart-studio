"""TDD RED phase — tests for ui/theme.py."""

from __future__ import annotations

from prompt_toolkit.styles import Style

from ui.theme import COLORS as C, build_style


class TestBuildStyle:
    """test_build_style_returns_style — build_style() returns non-None Style."""

    def test_build_style_returns_style(self):
        result = build_style()
        assert result is not None
        assert hasattr(result, 'style_rules')  # prompt_toolkit Style-like


class TestThemeRequiredKeys:
    """test_theme_has_required_keys — C dict has all required keys."""

    REQUIRED_KEYS = [
        "bg",
        "surface",
        "primary",
        "accent",
        "error",
        "warning",
        "success",
        "crux",
        "user",
    ]

    def test_theme_has_required_keys(self):
        for key in self.REQUIRED_KEYS:
            assert key in C, f"Missing required theme key: {key}"
            assert isinstance(C[key], str), f"Theme key {key} should be a string"
            assert len(C[key]) > 0, f"Theme key {key} should not be empty"
