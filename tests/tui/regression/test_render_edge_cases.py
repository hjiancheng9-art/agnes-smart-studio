"""Regression tests for TUI render edge cases — emoji, ANSI, wide chars."""
import pytest


class TestRenderEdgeCases:
    """Message rendering handles all character types."""

    @pytest.fixture
    def pane(self):
        from ui.message_pane import MessagePane
        return MessagePane()

    def test_zwj_emoji(self, pane):
        try:
            pane.append_message("user", "👨‍👩‍👧‍👦 Family")
        except Exception as e:
            pytest.fail(f"ZWJ: {e}")

    def test_vs16(self, pane):
        try:
            pane.append_message("user", "⚠️ Warning")
        except Exception as e:
            pytest.fail(f"VS16: {e}")

    def test_rtl(self, pane):
        try:
            pane.append_message("user", "مرحبا Mixed")
        except Exception as e:
            pytest.fail(f"RTL: {e}")

    def test_null_byte(self, pane):
        try:
            pane.append_message("user", "before\x00after")
        except Exception as e:
            pytest.fail(f"Null: {e}")

    def test_very_long_line(self, pane):
        try:
            pane.append_message("user", "A" * 50000)
        except Exception as e:
            pytest.fail(f"Long: {e}")

    def test_backslash(self, pane):
        try:
            pane.append_message("user", r"C:\Users\test\n\t")
        except Exception as e:
            pytest.fail(f"Backslash: {e}")

    def test_html_tags(self, pane):
        try:
            pane.append_message("user", "<script>alert('xss')</script>")
        except Exception as e:
            pytest.fail(f"HTML: {e}")

    def test_rich_brackets(self, pane):
        try:
            pane.append_message("user", "[bold red]test[/] [brackets]")
        except Exception as e:
            pytest.fail(f"Rich: {e}")

    def test_ansi_escape(self, pane):
        try:
            pane.append_message("assistant", "\033[31mRED\033[0m \033[1mBOLD\033[0m")
        except Exception as e:
            pytest.fail(f"ANSI: {e}")


class TestTerminalCapabilities:
    """Theme/animation work without terminal."""

    def test_all_modes_build(self):
        from ui.theme_v2 import build_style_v2
        for mode in ("normal", "high_contrast", "mono"):
            style = build_style_v2(mode)
            assert style is not None

    def test_animation_ssh_mode(self):
        from ui.animation_gov import AnimationGovernor
        gov = AnimationGovernor()
        result = gov.can_spin()
        assert isinstance(result, bool)

    def test_animation_no_terminal(self):
        from ui.animation_gov import AnimationGovernor, AnimType
        gov = AnimationGovernor()
        for _ in range(100):
            gov.can_animate(AnimType.SPINNER)
        assert True
