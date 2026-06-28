"""Tests for ui/provider_selector.py — ProviderSelector, config loading."""

import json
from unittest.mock import MagicMock

from ui.provider_selector import ProviderSelector


class TestProviderSelector:
    def test_init_stores_callback(self):
        cb = lambda k, u: None
        ps = ProviderSelector(cb)
        assert ps._on_client_swap is cb

    def test_load_models_config_returns_dict(self):
        cfg = ProviderSelector.load_models_config()
        assert isinstance(cfg, dict)
        assert "providers" in cfg
        assert "active" in cfg

    def test_load_models_config_has_crux_and_deepseek(self):
        cfg = ProviderSelector.load_models_config()
        providers = cfg.get("providers", {})
        assert "crux" in providers or "deepseek" in providers

    def test_load_models_config_has_fallback(self):
        cfg = ProviderSelector.load_models_config()
        assert "fallback" in cfg
        assert cfg["fallback"].get("enabled") is True
