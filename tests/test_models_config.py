"""Tests for models.json — provider registration, fallback chains, cost tiers."""

import json
from pathlib import Path

MODELS_PATH = Path(__file__).resolve().parent.parent / "models.json"


class TestModelsJson:
    def test_zhipu_provider_exists(self):
        data = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
        providers = data.get("providers", {})
        assert "zhipu" in providers, "zhipu provider must be registered"
        assert providers["zhipu"].get("cost_tier") == "free"
        assert "models" in providers["zhipu"]

    def test_deepseek_free_models(self):
        data = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
        ds = data["providers"]["deepseek"]
        models = ds["models"]
        assert "pro" in models
        assert "chat" in models or "deepseek-chat" in str(models)
        assert "reasoner" in models or "deepseek-reasoner" in str(models)

    def test_zhipu_has_no_hardcoded_key(self):
        data = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
        zhipu = data["providers"].get("zhipu", {})
        key = zhipu.get("api_key", "")
        assert not key or len(key) < 10, "API key must not be hardcoded in models.json"

    def test_fallback_includes_zhipu(self):
        data = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
        priority = data.get("fallback", {}).get("priority", [])
        assert "zhipu" in priority, "zhipu must be in fallback priority"

    def test_active_is_deepseek(self):
        data = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
        assert data.get("active") == "deepseek"
