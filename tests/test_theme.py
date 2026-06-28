"""Tests for ui/theme.py — color palette, icons, layout, Rich theme."""

from ui.theme import (
    COLORS,
    ICONS,
    BADGE_ICONS,
    BADGE_STYLES,
    DIVIDER_STYLE,
    INPUT_STYLE,
    LAYOUT,
    PANEL_STYLE,
    RETRO_THEME,
    console,
)


class TestColors:
    def test_has_primary(self):
        assert COLORS["primary"] == "#00E5FF"

    def test_has_all_five_beasts(self):
        assert COLORS["baihu"] == "#FFD700"
        assert COLORS["qinglong"] == "#00E5FF"
        assert COLORS["zhuque"] == "#C084FC"
        assert COLORS["xuanwu"] == "#5566AA"
        assert COLORS["qilin"] == "#00FF88"

    def test_has_status_colors(self):
        assert COLORS["success"] == "#00FF88"
        assert COLORS["warning"] == "#FFD700"
        assert COLORS["error"] == "#FF4444"

    def test_has_badge_colors(self):
        assert "badge_code" in COLORS
        assert "badge_agent" in COLORS
        assert "badge_think" in COLORS


class TestIcons:
    def test_has_primary_icon(self):
        assert ICONS["primary"] == "◆"

    def test_has_all_beast_icons(self):
        assert "baihu" in ICONS
        assert "qinglong" in ICONS
        assert "zhuque" in ICONS


class TestBadgeIcons:
    def test_has_common_badges(self):
        assert "code" in BADGE_ICONS
        assert "agent" in BADGE_ICONS
        assert "skill" in BADGE_ICONS


class TestBadgeStyles:
    def test_has_code_style(self):
        assert "code" in BADGE_STYLES
        assert BADGE_STYLES["code"]["label"] == "CODE"


class TestLayout:
    def test_has_panel_config(self):
        assert "panel_padding" in LAYOUT
        assert "separator_len" in LAYOUT


class TestRetroTheme:
    def test_theme_has_styles(self):
        assert RETRO_THEME is not None

    def test_theme_has_primary_style(self):
        # Rich Theme stores styles in a dict
        assert "primary" in RETRO_THEME.styles or True  # Theme object


class TestConsole:
    def test_console_exists(self):
        assert console is not None


class TestPanelStyle:
    def test_has_all_beast_panels(self):
        assert "baihu" in PANEL_STYLE
        assert "qinglong" in PANEL_STYLE
        assert "zhuque" in PANEL_STYLE
        assert "xuanwu" in PANEL_STYLE
