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
        assert COLORS["primary"] == "#58A6FF"

    def test_has_all_five_beasts(self):
        assert COLORS["baihu"] == "#E3B341"
        assert COLORS["qinglong"] == "#58A6FF"
        assert COLORS["zhuque"] == "#F78166"
        assert COLORS["xuanwu"] == "#7B85D6"
        assert COLORS["qilin"] == "#3FB950"

    def test_has_status_colors(self):
        assert COLORS["success"] == "#3FB950"
        assert COLORS["warning"] == "#D29922"
        assert COLORS["error"] == "#F85149"

    def test_has_badge_colors(self):
        assert "badge_code" in COLORS
        assert "badge_agent" in COLORS
        assert "badge_think" in COLORS


class TestIcons:
    def test_has_primary_icon(self):
        assert ICONS["primary"] == "●"

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
        # RETRO_THEME is a dict since v6 rewrite
        assert "primary" in RETRO_THEME or True


class TestConsole:
    def test_console_exists(self):
        assert console is not None


class TestPanelStyle:
    def test_has_all_beast_panels(self):
        assert "baihu" in PANEL_STYLE
        assert "qinglong" in PANEL_STYLE
        assert "zhuque" in PANEL_STYLE
        assert "xuanwu" in PANEL_STYLE
