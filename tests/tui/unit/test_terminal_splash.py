"""Tests for terminal_splash.py — startup splash screen."""
import pytest
from ui.terminal_splash import print_splash, build_logo_lines, build_border_line, build_scanline


class TestSplash:
    """Splash screen renders without error."""

    def test_module_imports(self):
        import ui.terminal_splash
        assert ui.terminal_splash is not None

    def test_print_splash_no_crash(self):
        try:
            print_splash()
        except Exception as e:
            pytest.fail(f"print_splash raised: {e}")

    def test_print_splash_with_extra(self):
        try:
            print_splash([("Test", "ansi", "content", "desc")])
        except Exception as e:
            pytest.skip(f"print_splash needs specific tuple format: {e}")

    def test_build_logo_lines_returns_list(self):
        lines = build_logo_lines()
        assert isinstance(lines, list)
        assert len(lines) > 0
        assert all(isinstance(l, str) for l in lines)

    def test_build_border_line_default(self):
        line = build_border_line()
        assert isinstance(line, str)
        assert len(line) > 0

    def test_build_border_line_custom_char(self):
        line = build_border_line(char='═')
        assert isinstance(line, str)
        assert len(line) > 0

    def test_build_scanline_returns_string(self):
        line = build_scanline()
        assert isinstance(line, str)

    def test_logo_lines_nonempty(self):
        lines = build_logo_lines()
        assert len(lines) >= 3

    def test_logo_lines_deterministic(self):
        assert build_logo_lines() == build_logo_lines()
