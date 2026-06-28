"""Tests for ui/terminal_logo.py — GLYPHS, pixel grid, banner rendering."""

from ui.terminal_logo import (
    GLYPHS,
    ICON,
    PIXEL_KIND,
    build_banner,
    render_mini_logo,
    render_pixel_grid,
    render_rich,
)


class TestGlyphs:
    def test_has_crux_letters(self):
        assert "C" in GLYPHS
        assert "R" in GLYPHS
        assert "U" in GLYPHS
        assert "X" in GLYPHS

    def test_c_glyph_is_8x_width(self):
        rows = GLYPHS["C"]
        assert len(rows) == 8
        for row in rows:
            assert len(row) == 8

    def test_r_glyph_dimensions(self):
        rows = GLYPHS["R"]
        assert len(rows) == 8
        for row in rows:
            assert len(row) == 8


class TestPixelKind:
    def test_maps_chars_to_colors(self):
        assert PIXEL_KIND["#"] == "primary"
        assert PIXEL_KIND["@"] == "accent"
        assert PIXEL_KIND["+"] == "highlight"
        assert PIXEL_KIND["."] is None


class TestIcon:
    def test_icon_is_5_rows(self):
        assert len(ICON) == 5

    def test_icon_has_pixels(self):
        for row in ICON:
            assert len(row) > 0


class TestRenderPixelGrid:
    def test_returns_2d_list(self):
        grid = render_pixel_grid()
        assert isinstance(grid, list)
        assert len(grid) > 0
        assert isinstance(grid[0], list)

    def test_has_pixels(self):
        grid = render_pixel_grid()
        has_pixel = any(cell is not None for row in grid for cell in row)
        assert has_pixel

    def test_dimensions_are_crux_size(self):
        grid = render_pixel_grid()
        # C(8)+R(8)+U(8)+X(8) + gaps*3 + shadow offset
        assert len(grid) >= 8


class TestBuildBanner:
    def test_returns_string_like_object(self):
        banner = build_banner()
        assert banner is not None

    def test_returns_text_with_content(self):
        from rich.text import Text
        banner = build_banner()
        assert isinstance(banner, Text)

    def test_custom_version(self):
        banner = build_banner(v="v9.9", t="99", s="999")
        assert banner is not None


class TestRenderMiniLogo:
    def test_returns_string(self):
        result = render_mini_logo()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRenderRich:
    def test_returns_text(self):
        from rich.text import Text
        result = render_rich()
        assert isinstance(result, Text)
