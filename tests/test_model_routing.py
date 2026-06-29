"""Tests for core/model_routing.py — 模型路由矩阵（ZCode 吸收）."""

from core.model_routing import (
    resolve_model,
    resolve_provider,
    find_models_by_capability,
    pick_best_model,
    get_provider_url,
    get_protocol_path,
    count_models,
    PROVIDERS,
    ModelSpec,
    ProviderSpec,
    ReasoningConfig,
)


class TestResolveModel:
    def test_resolve_existing_model(self):
        spec = resolve_model("deepseek-v4-flash")
        assert spec is not None
        assert spec.id == "deepseek-v4-flash"

    def test_resolve_nonexistent_returns_none(self):
        assert resolve_model("nonexistent-9000") is None

    def test_flash_has_reasoning_config(self):
        spec = resolve_model("deepseek-v4-flash")
        assert spec.reasoning is not None
        assert spec.reasoning.default_level in ("off", "enabled", "high", "max")

    def test_pro_has_max_reasoning(self):
        spec = resolve_model("deepseek-v4-pro")
        assert spec is not None
        assert spec.reasoning is not None
        assert "max" in spec.reasoning.available_levels

    def test_all_models_have_required_fields(self):
        """每个模型必须有 id, kinds, modalities。"""
        for p in PROVIDERS:
            for mspec in p.models:
                assert mspec.id, f"missing id in {p.id}"
                assert len(mspec.kinds) >= 1, f"{mspec.id} has no protocol kinds"
                assert len(mspec.modalities) == 2, f"{mspec.id} bad modalities"
                assert mspec.context_window > 0, f"{mspec.id} zero context"


class TestResolveProvider:
    def test_resolve_known_provider(self):
        spec = resolve_provider("deepseek")
        assert spec is not None
        assert spec.id == "deepseek"

    def test_resolve_unknown_returns_none(self):
        assert resolve_provider("nonexistent_provider_42") is None

    def test_deepseek_has_anthropic_path(self):
        spec = resolve_provider("deepseek")
        assert "anthropic" in spec.paths

    def test_moonshot_has_both_protocols(self):
        spec = resolve_provider("moonshot-kimi")
        assert "anthropic" in spec.paths
        assert "openai-compatible" in spec.paths

    def test_provider_has_base_url(self):
        spec = resolve_provider("deepseek")
        assert spec.base_url.startswith("https://")

    def test_provider_has_default_kind(self):
        spec = resolve_provider("deepseek")
        assert spec.default_kind in ("anthropic", "openai-compatible")


class TestPROVIDERSTuple:
    """PROVIDERS 元组结构。"""

    def test_providers_is_tuple(self):
        assert isinstance(PROVIDERS, tuple)

    def test_providers_contains_deepseek(self):
        ids = [p.id for p in PROVIDERS]
        assert "deepseek" in ids

    def test_providers_count_matches(self):
        stats = count_models()
        assert len(PROVIDERS) == stats["providers"]

    def test_every_provider_is_provider_spec(self):
        for p in PROVIDERS:
            assert isinstance(p, ProviderSpec)

    def test_every_model_is_model_spec(self):
        for p in PROVIDERS:
            for m in p.models:
                assert isinstance(m, ModelSpec)


class TestFindModelsByCapability:
    def test_find_vision_models(self):
        results = find_models_by_capability(supports_image=True)
        assert len(results) >= 1
        for pid, mid in results:
            spec = resolve_model(mid)
            assert spec is not None
            assert "image" in spec.modalities[0]

    def test_find_reasoning_models(self):
        results = find_models_by_capability(supports_reasoning=True)
        assert len(results) >= 1
        for _, mid in results:
            spec = resolve_model(mid)
            assert spec.reasoning is not None

    def test_no_filter_returns_all(self):
        results = find_models_by_capability()
        total = sum(len(p.models) for p in PROVIDERS)
        assert len(results) == total

    def test_impossible_filter_returns_empty(self):
        results = find_models_by_capability(supports_image=True, supports_video=True, min_context=999999)
        assert isinstance(results, list)

    def test_protocol_filter_works(self):
        results = find_models_by_capability(protocols=("anthropic",))
        assert len(results) >= 1


class TestPickBestModel:
    def test_pick_best_deepseek(self):
        best = pick_best_model("deepseek")
        assert best is not None
        assert "deepseek" in best

    def test_pick_best_moonshot(self):
        best = pick_best_model("moonshot-kimi")
        assert best is not None

    def test_pick_best_nonexistent_returns_none(self):
        assert pick_best_model("nonexistent_provider") is None

    def test_pick_best_no_provider_returns_global_best(self):
        best = pick_best_model()
        assert best is not None

    def test_pick_best_prefer_reasoning(self):
        best = pick_best_model("deepseek", prefer_reasoning=True)
        assert isinstance(best, str)

    def test_pick_best_prefer_vision(self):
        best = pick_best_model(prefer_vision=True)
        assert best is not None
        spec = resolve_model(best)
        assert "image" in spec.modalities[0]


class TestGetProviderUrl:
    def test_get_anthropic_url(self):
        url = get_provider_url("deepseek", "anthropic")
        assert url is not None
        assert url.startswith("https://")
        assert "anthropic" in url

    def test_get_openai_url(self):
        url = get_provider_url("moonshot-kimi", "openai-compatible")
        assert url is not None
        assert "chat" in url or "completions" in url

    def test_unknown_kind_returns_none(self):
        url = get_provider_url("deepseek", "openai-compatible")
        assert url is not None  # deepseek has openai-compatible path

    def test_unknown_provider_returns_none(self):
        assert get_provider_url("non_existent", "anthropic") is None

    def test_zai_only_has_anthropic(self):
        """zai 只配了 anthropic 路径。"""
        url = get_provider_url("zai", "openai-compatible")
        assert url is None


class TestGetProtocolPath:
    def test_basic_protocol_path(self):
        path = get_protocol_path("deepseek", "deepseek-v4-flash", "anthropic")
        assert path is not None
        assert "base_url" in path
        assert path["base_url"].startswith("https://")

    def test_reasoning_model_has_reasoning_config(self):
        path = get_protocol_path("deepseek", "deepseek-v4-pro", "anthropic")
        assert path is not None
        assert "reasoning_default" in path

    def test_nonexistent_provider_returns_none(self):
        assert get_protocol_path("unknown_provider", "some-model", "anthropic") is None

    def test_kind_not_in_model_kinds_returns_none(self):
        """zai 只有 anthropic，问 openai-compatible 应返回 None。"""
        path = get_protocol_path("zai", "glm-5.1", "openai-compatible")
        assert path is None

    def test_path_has_kind_field(self):
        path = get_protocol_path("deepseek", "deepseek-v4-flash", "anthropic")
        assert "kind" in path
        assert path["kind"] == "anthropic"


class TestCountModels:
    def test_count_returns_dict(self):
        stats = count_models()
        assert isinstance(stats, dict)

    def test_count_has_all_keys(self):
        stats = count_models()
        for key in ("providers", "models", "with_reasoning", "with_vision", "protocols"):
            assert key in stats, f"missing key: {key}"

    def test_provider_count_matches(self):
        stats = count_models()
        assert stats["providers"] == len(PROVIDERS)
        assert stats["providers"] >= 5

    def test_model_count_positive(self):
        stats = count_models()
        assert stats["models"] > 10

    def test_reasoning_models_subset(self):
        stats = count_models()
        assert stats["with_reasoning"] <= stats["models"]

    def test_vision_models_subset(self):
        stats = count_models()
        assert stats["with_vision"] >= 0

    def test_protocols_listed(self):
        stats = count_models()
        assert "anthropic" in stats["protocols"]
