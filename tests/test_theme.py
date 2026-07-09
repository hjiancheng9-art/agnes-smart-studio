"""Tests for core/theme.py — 主题常量"""

from core.theme import BEAST_ICONS, BEAST_ORDER, BEAST_PALETTE, COLORS


class TestBeastIcons:
    def test_all_seven_beasts(self):
        assert len(BEAST_ICONS) == 7

    def test_has_core_beasts(self):
        assert "BAIHU" in BEAST_ICONS
        assert "QINGLONG" in BEAST_ICONS
        assert "ZHUQUE" in BEAST_ICONS
        assert "XUANWU" in BEAST_ICONS

    def test_icons_are_strings(self):
        for k, v in BEAST_ICONS.items():
            assert isinstance(k, str)
            assert isinstance(v, str)


class TestBeastOrder:
    def test_has_seven_items(self):
        assert len(BEAST_ORDER) == 7

    def test_baihu_first(self):
        assert BEAST_ORDER[0] == "BAIHU"

    def test_yinglong_last(self):
        assert BEAST_ORDER[-1] == "YINGLONG"


class TestBeastPalette:
    def test_is_dict(self):
        assert isinstance(BEAST_PALETTE, dict)

    def test_has_beasts(self):
        for beast in BEAST_ORDER:
            assert beast in BEAST_PALETTE


class TestColors:
    def test_is_dict(self):
        assert isinstance(COLORS, dict)

    def test_non_empty(self):
        assert len(COLORS) > 0

    def test_values_are_colors(self):
        for _k, v in COLORS.items():
            assert isinstance(v, str)
            assert v.startswith("#") or "," in v or "rgb" in v.lower()
