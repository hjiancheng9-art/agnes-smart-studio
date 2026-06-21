"""Unit tests for provider management."""
import sys
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import core.provider
from core.provider import (
    ProviderManager, get_provider_manager,
    MODEL_REGISTRY, ModelInfo, resolve_model_alias,
    get_tool_calling_models, get_model_description,
    get_provider_name, model_supports_tools, register_model,
)

class TestModelRegistry:
    def test_builtin_models_registered(self):
        assert "agnes-1.5-flash" in MODEL_REGISTRY
        assert "agnes-2.0-flash" in MODEL_REGISTRY
        assert "deepseek-v4-pro" in MODEL_REGISTRY
        assert "Pro/moonshotai/Kimi-K2.6" in MODEL_REGISTRY

    def test_model_info_fields(self):
        m = MODEL_REGISTRY["agnes-2.0-flash"]
        assert m.id == "agnes-2.0-flash"
        assert m.provider_id == "agnes"
        assert m.supports_tools is True
        assert m.supports_thinking is True
        assert "pro" in m.aliases

    def test_vision_model_has_vision_flag(self):
        assert MODEL_REGISTRY["agnes-1.5-flash"].supports_vision is True
        assert MODEL_REGISTRY["agnes-2.0-flash"].supports_vision is False

    def test_register_custom_model(self):
        info = ModelInfo(
            id="custom-model", name="Custom", provider_id="custom",
            provider_name="Custom Provider", supports_tools=True,
        )
        register_model(info)
        assert "custom-model" in MODEL_REGISTRY
        assert model_supports_tools("custom-model")


class TestResolveAlias:
    def test_resolve_builtin_alias(self):
        assert resolve_model_alias("light") == "agnes-1.5-flash"
        assert resolve_model_alias("pro") == "agnes-2.0-flash"

    def test_resolve_third_party_alias(self):
        assert resolve_model_alias("deepseek") == "deepseek-v4-pro"
        assert resolve_model_alias("ds") == "deepseek-v4-pro"
        assert resolve_model_alias("kimi") == "Pro/moonshotai/Kimi-K2.6"

    def test_resolve_exact_id(self):
        assert resolve_model_alias("agnes-2.0-flash") == "agnes-2.0-flash"

    def test_resolve_case_insensitive_id(self):
        result = resolve_model_alias("AGNES-2.0-FLASH")
        assert result == "agnes-2.0-flash"

    def test_resolve_unknown_returns_none(self):
        assert resolve_model_alias("nonexistent-model") is None


class TestToolCallingModels:
    def test_agnes_pro_supports_tools(self):
        assert "agnes-2.0-flash" in get_tool_calling_models()

    def test_agnes_light_no_tools(self):
        assert "agnes-1.5-flash" not in get_tool_calling_models()

    def test_third_party_supports_tools(self):
        models = get_tool_calling_models()
        assert "deepseek-v4-pro" in models
        assert "Pro/moonshotai/Kimi-K2.6" in models

    def test_model_supports_tools_helper(self):
        assert model_supports_tools("agnes-2.0-flash") is True
        assert model_supports_tools("agnes-1.5-flash") is False
        assert model_supports_tools("unknown") is False


class TestProviderName:
    def test_agnes_provider_name(self):
        assert get_provider_name("agnes-2.0-flash") == "Agnes AI"
        assert get_provider_name("agnes-1.5-flash") == "Agnes AI"

    def test_deepseek_provider_name(self):
        assert "DeepSeek" in get_provider_name("deepseek-v4-pro")

    def test_unknown_model_returns_id(self):
        assert get_provider_name("unknown-model") == "unknown-model"


class TestModelDescription:
    def test_known_model_has_description(self):
        desc = get_model_description("agnes-2.0-flash")
        assert "Agnes" in desc
        assert "2.0" in desc

    def test_unknown_model_returns_id(self):
        assert get_model_description("xyz") == "xyz"


class TestProviderManager:
    @pytest.fixture
    def tmp_models(self, tmp_path, monkeypatch):
        monkeypatch.setattr(core.provider, "ROOT", tmp_path)
        return tmp_path / "models.json"

    def test_load_providers(self, tmp_models):
        tmp_models.write_text(json.dumps({"providers": {"tp": {"name": "T", "base_url": "https://t.com/v1", "api_key": "k", "models": {"pro": "tp", "light": "tl"}}}, "active": "tp"}), encoding="utf-8")
        mgr = ProviderManager()
        mgr.load()
        assert "tp" in mgr.providers
        assert mgr.state.active == "tp"

    def test_set_active(self, tmp_models):
        tmp_models.write_text(json.dumps({"providers": {"a": {"name": "A", "base_url": "https://a.com/v1", "api_key": "ka", "models": {"pro": "ap", "light": "al"}}, "b": {"name": "B", "base_url": "https://b.com/v1", "api_key": "kb", "models": {"pro": "bp", "light": "bl"}}}, "active": "b"}), encoding="utf-8")
        mgr = ProviderManager()
        mgr.load()
        mgr.set_active("a")
        assert mgr.state.active == "a"

    def test_get_model(self, tmp_models):
        tmp_models.write_text(json.dumps({"providers": {"x": {"name": "X", "base_url": "https://x.com/v1", "api_key": "kx", "models": {"pro": "x-pro", "light": "x-light"}}}, "active": "x"}), encoding="utf-8")
        mgr = ProviderManager()
        mgr.load()
        assert mgr.get_model("pro").endswith("x-pro")

    def test_set_active_unknown(self, tmp_models):
        tmp_models.write_text(json.dumps({"providers": {"a": {"name": "A", "base_url": "https://a.com/v1", "api_key": "ka", "models": {"pro": "ap", "light": "al"}}}, "active": "a"}), encoding="utf-8")
        mgr = ProviderManager()
        mgr.load()
        mgr.set_active("nonexistent")
        assert mgr.state.active in ("a", "nonexistent")

class TestSingletonProvider:
    def test_singleton(self):
        assert get_provider_manager() is get_provider_manager()
    def test_type(self):
        assert isinstance(get_provider_manager(), ProviderManager)
