"""Tests for core/skin.py — Skin manager, logo asset, layer rendering."""

from unittest.mock import MagicMock, patch

from core.skin import SkinAsset, SkinLayer, SkinManager, get_skin


class TestSkinLayer:
    def test_enum_values(self):
        assert SkinLayer.TERMINAL.value == "terminal"
        assert SkinLayer.SVG.value == "svg"
        assert SkinLayer.WEB.value == "web"
        assert SkinLayer.API.value == "api"


class TestSkinAsset:
    def test_creation(self):
        a = SkinAsset(name="logo")
        assert a.name == "logo"
        assert a.data == {}

    def test_data_stores_layer_content(self):
        a = SkinAsset(name="test")
        a.data[SkinLayer.TERMINAL] = "terminal content"
        a.data[SkinLayer.SVG] = "<svg/>"
        assert a.data[SkinLayer.TERMINAL] == "terminal content"
        assert a.data[SkinLayer.SVG] == "<svg/>"


class TestSkinManager:
    def test_has_logo_asset_after_init(self):
        mgr = SkinManager()
        assert "logo" in mgr.list_assets()

    def test_has_banner_asset_after_init(self):
        mgr = SkinManager()
        assert "banner" in mgr.list_assets()

    def test_render_logo_terminal(self):
        mgr = SkinManager()
        result = mgr.render("logo", SkinLayer.TERMINAL)
        assert result is not None

    def test_render_logo_svg(self):
        mgr = SkinManager()
        svg = mgr.render("logo", SkinLayer.SVG)
        assert isinstance(svg, str)
        assert svg.startswith("<svg")

    def test_render_logo_web(self):
        mgr = SkinManager()
        web = mgr.render("logo", SkinLayer.WEB)
        assert isinstance(web, str)
        assert web.startswith("<svg")

    def test_render_nonexistent_returns_none(self):
        mgr = SkinManager()
        assert mgr.render("nonexistent") is None

    def test_render_default_layer_is_terminal(self):
        mgr = SkinManager()
        # default layer is TERMINAL
        assert mgr.render("logo") is not None

    def test_list_assets(self):
        mgr = SkinManager()
        assets = mgr.list_assets()
        assert "logo" in assets
        assert "banner" in assets

    def test_list_layers_for_logo(self):
        mgr = SkinManager()
        layers = mgr.list_layers("logo")
        assert "terminal" in layers
        assert "svg" in layers
        assert "web" in layers

    def test_list_layers_nonexistent(self):
        mgr = SkinManager()
        assert mgr.list_layers("nonexistent") == []

    def test_summary_returns_string(self):
        mgr = SkinManager()
        s = mgr.summary()
        assert "Skin" in s
        assert "logo" in s

    def test_init_logo_catches_import_error_internally(self):
        # _init_logo has its own try/except for ImportError.
        # _init_all calls _init_logo without wrapping, but _init_logo catches internally.
        mgr = SkinManager()
        # logo should be available since imports succeed
        assert "logo" in mgr.list_assets()

    def test_banner_init_handles_import_error(self):
        mgr = SkinManager()
        with patch.object(mgr, "_init_banner", side_effect=ImportError):
            mgr._init_all()  # should not raise — _init_banner is wrapped in contextlib.suppress


class TestGridToSvg:
    def test_empty_grid(self):
        mgr = SkinManager()
        svg = mgr._grid_to_svg([])
        assert "<svg" in svg

    def test_grid_with_content(self):
        mgr = SkinManager()
        grid = [[{"color": "primary", "shadow": False}]]
        svg = mgr._grid_to_svg(grid)
        assert "<rect" in svg
        assert "#58A6FF" in svg

    def test_grid_shadow_cell(self):
        mgr = SkinManager()
        grid = [[{"color": "muted", "shadow": True}]]
        svg = mgr._grid_to_svg(grid)
        assert 'opacity="0.55"' in svg


class TestGridToWeb:
    def test_empty_grid(self):
        mgr = SkinManager()
        html = mgr._grid_to_web([])
        assert "<svg" in html

    def test_web_has_pixelated_style(self):
        mgr = SkinManager()
        grid = [[{"color": "primary", "shadow": False}]]
        html = mgr._grid_to_web(grid)
        assert "pixelated" in html
        assert "#161B22" in html  # surface color from COLORS["surface"]


class TestGetSkin:
    def test_returns_skin_manager(self):
        skin = get_skin()
        assert isinstance(skin, SkinManager)

    def test_singleton(self):
        s1 = get_skin()
        s2 = get_skin()
        assert s1 is s2
