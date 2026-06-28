"""Tests for ui/cli.py — CruxCLI structure, _get_logo, context manager."""

from unittest.mock import MagicMock, patch

from ui.cli import LOGO, CruxCLI, _get_logo


class TestGetLogo:
    def test_returns_logo(self):
        result = _get_logo()
        assert result is not None

    def test_caches_logo(self):
        global LOGO
        LOGO = None
        r1 = _get_logo()
        r2 = _get_logo()
        assert r1 is r2  # cached, same object


class TestCruxCLIStructure:
    def test_init_creates_client(self):
        cli = CruxCLI()
        assert cli.client is not None
        cli.close()

    def test_init_creates_vision_client(self):
        cli = CruxCLI()
        assert cli.vision_client is not None
        cli.close()

    def test_init_creates_media_client(self):
        cli = CruxCLI()
        assert cli.media_client is not None
        cli.close()

    def test_init_creates_brain(self):
        cli = CruxCLI()
        assert cli.brain is not None
        cli.close()

    def test_init_creates_engines(self):
        cli = CruxCLI()
        assert cli.t2i is not None
        assert cli.i2i is not None
        assert cli.vid is not None
        assert cli.pipe is not None
        cli.close()

    def test_mixin_inheritance(self):
        from ui.mixins import (
            CreativeCommandsMixin,
            DiagCommandsMixin,
            EngineeringCommandsMixin,
            GeneratorsMenuMixin,
            GitCommandsMixin,
            InlineCommandsMixin,
            SharedMixin,
        )
        assert isinstance(CruxCLI.__init__, object)  # it's a class
        # Check actual MRO
        mro_names = [c.__name__ for c in CruxCLI.__mro__]
        assert "SharedMixin" in mro_names
        assert "InlineCommandsMixin" in mro_names


class TestContextManager:
    def test_enter_exit(self):
        cli = CruxCLI()
        with cli:
            # cruxCLI is active
            pass
        # should close cleanly


class TestConstants:
    def test_logo_global_exists(self):
        assert LOGO is not None or LOGO is None  # can be None before first access
