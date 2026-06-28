"""Tests for models.json config loading and provider configuration access.

Tests the models.json structure and config loading utility that the
DiagCommandsMixin and provider selector rely on.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


class TestModelsConfig:
    """Tests models.json provider configuration."""

    def _load_config(self):
        path = ROOT / "models.json"
        assert path.exists(), "models.json not found"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_config_is_valid_json(self):
        cfg = self._load_config()
        assert isinstance(cfg, dict)

    def test_has_providers(self):
        cfg = self._load_config()
        assert "providers" in cfg
        assert len(cfg["providers"]) >= 1

    def test_has_active_provider(self):
        cfg = self._load_config()
        assert "active" in cfg
        assert cfg["active"] in cfg["providers"]

    def test_each_provider_has_base_url(self):
        cfg = self._load_config()
        for pid, p in cfg["providers"].items():
            assert "base_url" in p, f"{pid} missing base_url"
            assert p["base_url"].startswith("http"), f"{pid} base_url not HTTP"

    def test_each_provider_has_models(self):
        cfg = self._load_config()
        for pid, p in cfg["providers"].items():
            assert "models" in p, f"{pid} missing models"
            assert isinstance(p["models"], dict)
            assert len(p["models"]) >= 1

    def test_active_provider_has_models(self):
        cfg = self._load_config()
        active = cfg["active"]
        models = cfg["providers"][active].get("models", {})
        assert "pro" in models or "light" in models

    def test_fallback_config(self):
        cfg = self._load_config()
        fallback = cfg.get("fallback", {})
        assert isinstance(fallback, dict)
        assert "enabled" in fallback


class TestProviderNameUniqueness:
    """All provider names should be unique."""

    def test_no_duplicate_names(self):
        path = ROOT / "models.json"
        cfg = json.loads(path.read_text(encoding="utf-8"))
        names = [p.get("name", pid) for pid, p in cfg["providers"].items()]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"


class TestProviderModelAccess:
    """Tests that models referenced as 'active' actually exist in the provider."""

    def test_active_model_reachable(self):
        path = ROOT / "models.json"
        cfg = json.loads(path.read_text(encoding="utf-8"))
        active = cfg["active"]
        provider = cfg["providers"][active]
        model_ids = provider.get("models", {})
        assert model_ids, f"Active provider {active} has no model IDs"
        for tier, model_id in model_ids.items():
            assert isinstance(model_id, str) and len(model_id) > 0, \
                f"Invalid model ID for {active}.{tier}: {model_id!r}"
