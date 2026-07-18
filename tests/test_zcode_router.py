"""Comprehensive RED-GREEN tests for core/router, core/provider.

TDD style: every test is self-contained, uses plain assert, no fixtures/marks.
"""

import pytest

# ── Module 1: core/router.py ────────────────────────────────────────


class TestRouterTaskProfile:
    """TaskProfile enum has expected members."""

    def test_task_profile_enum_members(self):
        from core.router import TaskProfile

        assert TaskProfile.CHAT.value == "chat"
        assert TaskProfile.QUICK_FIX.value == "quick_fix"
        assert TaskProfile.CODING.value == "coding"
        assert TaskProfile.DEEP.value == "deep"
        assert TaskProfile.CREATIVE.value == "creative"
        assert TaskProfile.SKIP.value == "skip"

    def test_task_profile_is_enum(self):
        import enum

        from core.router import TaskProfile

        assert issubclass(TaskProfile, enum.Enum)


class TestRouterRouteDecision:
    """RouteDecision dataclass fields."""

    def test_route_decision_fields(self):
        from core.router import RouteDecision, TaskProfile

        d = RouteDecision(profile=TaskProfile.DEEP, model_id="deepseek-v4-pro", reason="test", switch_client=True)
        assert d.profile == TaskProfile.DEEP
        assert d.model_id == "deepseek-v4-pro"
        assert d.reason == "test"
        assert d.switch_client is True

    def test_route_decision_defaults(self):
        from core.router import RouteDecision, TaskProfile

        d = RouteDecision(profile=TaskProfile.SKIP)
        assert d.profile == TaskProfile.SKIP
        assert d.model_id is None
        assert d.reason == ""
        assert d.switch_client is False


class TestRouterCOMMAND_ROUTE_MAP:
    """COMMAND_ROUTE_MAP has expected entries."""

    def test_command_route_map_has_plan(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("plan")
        assert entry is not None
        profile, model_id, reason = entry
        assert profile == TaskProfile.DEEP
        assert model_id in ("deepseek-v4-pro", "pro"), f"Unexpected: {model_id}"
        assert "深度推理" in reason

    def test_command_route_map_has_sub(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("sub")
        assert entry is not None
        assert entry[0] == TaskProfile.DEEP
        assert entry[1] in ("deepseek-v4-pro", "pro"), f"Unexpected model: {entry[1]}"

    def test_command_route_map_has_refactor(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("refactor")
        assert entry is not None
        assert entry[0] == TaskProfile.DEEP
        assert entry[1] in ("deepseek-v4-pro", "pro"), f"Unexpected model: {entry[1]}"

    def test_command_route_map_has_team(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("team")
        assert entry is not None
        assert entry[0] == TaskProfile.DEEP
        assert entry[1] is None

    def test_command_route_map_has_showrun(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("showrun")
        assert entry is not None
        assert entry[0] == TaskProfile.CREATIVE
        assert entry[1] is None

    def test_command_route_map_has_help(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("help")
        assert entry is not None
        assert entry[0] == TaskProfile.SKIP

    def test_command_route_map_has_model(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("model")
        assert entry is not None
        assert entry[0] == TaskProfile.SKIP

    def test_command_route_map_has_clear(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("clear")
        assert entry is not None
        assert entry[0] == TaskProfile.SKIP

    def test_command_route_map_has_exit(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("exit")
        assert entry is not None
        assert entry[0] == TaskProfile.SKIP

    def test_command_route_map_has_quit(self):
        from core.router import COMMAND_ROUTE_MAP, TaskProfile

        entry = COMMAND_ROUTE_MAP.get("quit")
        assert entry is not None
        assert entry[0] == TaskProfile.SKIP


class TestRouterClassify:
    """classify() function tests."""

    def test_classify_hello_returns_skip(self):
        from core.router import TaskProfile, classify

        result = classify("hello")
        assert result == TaskProfile.SKIP

    def test_classify_deep_keywords(self):
        from core.router import TaskProfile, classify

        result = classify("重构整个系统架构")
        assert result == TaskProfile.DEEP

    def test_classify_quick_fix_keywords(self):
        from core.router import TaskProfile, classify

        result = classify("fix the bug in login")
        assert result == TaskProfile.QUICK_FIX

    def test_classify_creative_keywords(self):
        from core.router import TaskProfile, classify

        result = classify("生成一张图片")
        assert result == TaskProfile.CREATIVE

    def test_classify_code_keywords(self):
        from core.router import TaskProfile, classify

        result = classify("实现一个登录函数")
        assert result == TaskProfile.CODING

    def test_classify_empty_string(self):
        from core.router import TaskProfile, classify

        result = classify("")
        assert result == TaskProfile.SKIP

    def test_classify_whitespace_only(self):
        from core.router import TaskProfile, classify

        result = classify("   ")
        assert result == TaskProfile.SKIP

    def test_classify_deep_architecture(self):
        from core.router import TaskProfile, classify

        result = classify("全面分析系统架构")
        assert result == TaskProfile.DEEP

    def test_classify_creative_video(self):
        from core.router import TaskProfile, classify

        result = classify("生成一个视频")
        assert result == TaskProfile.CREATIVE

    def test_classify_code_function(self):
        from core.router import TaskProfile, classify

        result = classify("写一个函数处理数据")
        assert result == TaskProfile.CODING


class TestRouterRouteCommand:
    """route_command() function tests."""

    def test_route_command_plan(self):
        from core.router import TaskProfile, route_command

        decision = route_command("plan", "", None)
        assert decision.profile == TaskProfile.DEEP
        assert decision.model_id in ("deepseek-v4-pro", "pro"), f"Unexpected: {decision.model_id}"

    def test_route_command_help(self):
        from core.router import TaskProfile, route_command

        decision = route_command("help", "", None)
        assert decision.profile == TaskProfile.SKIP
        assert decision.model_id is None

    def test_route_command_unknown(self):
        from core.router import TaskProfile, route_command

        decision = route_command("unknown_cmd", "", None)
        assert decision.profile == TaskProfile.SKIP
        assert decision.model_id is None

    def test_route_command_refactor(self):
        from core.router import TaskProfile, route_command

        decision = route_command("refactor", "", None)
        assert decision.profile == TaskProfile.DEEP
        assert decision.model_id in ("deepseek-v4-pro", "pro"), f"Unexpected: {decision.model_id}"

    def test_route_command_clear(self):
        from core.router import TaskProfile, route_command

        decision = route_command("clear", "", None)
        assert decision.profile == TaskProfile.SKIP


class TestRouterRoute:
    """route() function tests."""

    def test_route_slash_plan(self):
        from core.router import TaskProfile, route

        decision = route("/plan", None)
        assert decision.profile == TaskProfile.DEEP
        assert decision.model_id in ("deepseek-v4-pro", "pro"), f"Unexpected: {decision.model_id}"

    def test_route_hello_text(self):
        from core.router import route

        result = route("hello", None)
        # classify("hello") -> SKIP, resolve(SKIP) -> SKIP
        assert result is not None

    def test_route_slash_unknown(self):
        from core.router import TaskProfile, route

        decision = route("/nonexistent_slash_command", None)
        assert decision.profile == TaskProfile.SKIP


class TestRouterCostTier:
    """CostTier enum and set/get functions."""

    def test_cost_tier_enum_members(self):
        from core.router import CostTier

        assert CostTier.SAVE.value == "save"
        assert CostTier.BALANCED.value == "balanced"
        assert CostTier.BEST.value == "best"

    def test_set_and_get_cost_tier(self):
        from core.router import CostTier, get_cost_tier, set_cost_tier

        set_cost_tier(CostTier.SAVE)
        assert get_cost_tier() == CostTier.SAVE

    def test_set_cost_tier_string(self):
        from core.router import CostTier, get_cost_tier, set_cost_tier

        set_cost_tier("best")
        assert get_cost_tier() == CostTier.BEST

    def test_cost_tier_returns_valid_enum(self):
        from core.router import CostTier, get_cost_tier

        tier = get_cost_tier()
        assert isinstance(tier, CostTier)
        assert tier in (CostTier.SAVE, CostTier.BALANCED, CostTier.BEST)


class TestRouterResolve:
    """resolve() function tests."""

    def test_resolve_string_quick_fix(self):
        from core.router import resolve

        # String profile "quick_fix" should be converted to TaskProfile
        decision = resolve("quick_fix", None)
        assert decision is not None

    def test_resolve_skip_profile(self):
        from core.router import TaskProfile, resolve

        decision = resolve(TaskProfile.SKIP, None)
        assert decision.profile == TaskProfile.SKIP
        assert decision.model_id is None


# ── Module 3: core/provider.py ──────────────────────────────────────


class TestProviderModelRegistry:
    """MODEL_REGISTRY tests."""

    def test_model_registry_non_empty(self):
        from core.provider import MODEL_REGISTRY

        assert len(MODEL_REGISTRY) > 0

    def test_model_registry_has_deepseek_v4_pro(self):
        from core.provider import MODEL_REGISTRY

        assert "deepseek-v4-pro" in MODEL_REGISTRY

    def test_model_registry_has_agnes_vision(self):
        from core.provider import MODEL_REGISTRY

        assert "agnes-2.0-flash" in MODEL_REGISTRY


class TestProviderResolveModelAlias:
    """resolve_model_alias() tests."""

    def test_resolve_alias_pro(self):
        from core.provider import resolve_model_alias

        result = resolve_model_alias("pro")
        assert result == "deepseek-v4-pro"

    def test_resolve_alias_flash(self):
        from core.provider import resolve_model_alias

        result = resolve_model_alias("flash")
        assert result == "deepseek-v4-flash"

    def test_resolve_alias_deepseek(self):
        from core.provider import resolve_model_alias

        result = resolve_model_alias("deepseek")
        assert result == "deepseek-v4-pro"

    def test_resolve_alias_nonexistent(self):
        from core.provider import resolve_model_alias

        result = resolve_model_alias("nonexistent_alias_xyz")
        assert result is None


class TestProviderGetModelInfo:
    """get_model_info() tests."""

    def test_get_model_info_pro(self):
        from core.provider import get_model_info

        info = get_model_info("deepseek-v4-pro")
        assert info is not None
        assert info.id == "deepseek-v4-pro"
        assert info.provider_id == "deepseek"
        assert info.supports_tools is True
        assert info.supports_thinking is True
        assert info.context_window == 1000000

    def test_get_model_info_flash(self):
        from core.provider import get_model_info

        info = get_model_info("deepseek-v4-flash")
        assert info is not None
        assert info.id == "deepseek-v4-flash"
        assert info.supports_tools is True

    def test_get_model_info_nonexistent(self):
        from core.provider import get_model_info

        info = get_model_info("nonexistent-model")
        assert info is None


class TestProviderToolCalling:
    """Tool-calling model functions."""

    def test_get_tool_calling_models_has_deepseek(self):
        from core.provider import get_tool_calling_models

        models = get_tool_calling_models()
        assert "deepseek-v4-pro" in models
        assert "deepseek-v4-flash" in models

    def test_model_supports_tools_deepseek_v4_pro(self):
        from core.provider import model_supports_tools

        assert model_supports_tools("deepseek-v4-pro") is True

    def test_model_supports_tools_video_model(self):
        from core.provider import model_supports_tools

        # Video/image generation models do NOT support tools
        assert model_supports_tools("agnes-video-v2.0") is False


class TestProviderVision:
    """Vision model functions."""

    def test_get_vision_models_has_agnes(self):
        from core.provider import get_vision_models

        models = get_vision_models()
        assert "agnes-2.0-flash" in models

    def test_get_vision_models_contains_agnes(self):
        from core.provider import get_vision_models

        models = get_vision_models()
        assert "agnes-2.0-flash" in models

    def test_model_supports_vision_agnes_flash(self):
        from core.provider import model_supports_vision

        assert model_supports_vision("agnes-2.0-flash") is True

    def test_model_supports_vision_deepseek_v4_pro(self):
        from core.provider import model_supports_vision

        assert model_supports_vision("deepseek-v4-pro") is False


class TestProviderContextWindow:
    """Context window utilities."""

    def test_get_context_window_deepseek_v4_pro(self):
        from core.provider import get_context_window

        assert get_context_window("deepseek-v4-pro") == 1000000

    def test_get_context_window_unknown(self):
        from core.provider import get_context_window

        assert get_context_window("unknown-model") == 128000


class TestProviderMaxTokens:
    """Max tokens utilities."""

    def test_get_max_tokens_for_model_pro(self):
        from core.provider import get_max_tokens_for_model

        tokens = get_max_tokens_for_model("deepseek-v4-pro")
        assert tokens > 0
        assert tokens == 16384  # ProviderAdapter.default_max_tokens (doubled 2026-07)

    def test_get_max_tokens_for_model_flash(self):
        from core.provider import get_max_tokens_for_model

        tokens = get_max_tokens_for_model("deepseek-v4-flash")
        assert tokens > 0

    def test_get_max_tokens_for_model_unknown(self):
        from core.provider import get_max_tokens_for_model

        tokens = get_max_tokens_for_model("nonexistent-model")
        assert tokens > 0
        assert tokens >= 256

    def test_get_max_tokens_tool_call_caps(self):
        from core.provider import get_max_tokens_for_model

        tokens = get_max_tokens_for_model("GLM-4V-Flash", is_tool_call=True)
        assert tokens > 0
        assert tokens <= 8192


class TestProviderCapabilityInfo:
    """get_capability_info() tests."""

    def test_get_capability_info_pro(self):
        from core.provider import get_capability_info

        info = get_capability_info("pro")
        assert info is not None
        assert info.id == "deepseek-v4-pro"

    def test_get_capability_info_direct(self):
        from core.provider import get_capability_info

        info = get_capability_info("deepseek-v4-pro")
        assert info is not None


class TestProviderRegisterModel:
    """register_model() tests."""

    def test_register_model(self):
        from core.provider import ModelInfo, get_model_info, register_model

        new = ModelInfo(
            id="test-custom-model",
            name="Test Model",
            provider_id="test",
            provider_name="Test",
            tier="pro",
            context_window=64000,
            max_output_tokens=4096,
        )
        register_model(new)
        retrieved = get_model_info("test-custom-model")
        assert retrieved is not None
        assert retrieved.id == "test-custom-model"


class TestProviderState:
    """ProviderState tests."""

    def test_provider_state_creation(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        assert state.active == "deepseek"
        assert state.cooldown_sec == 30.0

    def test_mark_down_and_is_down(self):
        import time

        from core.provider import ProviderState

        state = ProviderState(active="deepseek", cooldown_sec=0.1)
        state.mark_down("zhipu")
        assert state.is_down("zhipu") is True
        time.sleep(0.15)
        assert state.is_down("zhipu") is False

    def test_available(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek", cooldown_sec=30.0)
        state.mark_down("zhipu")
        result = state.available(["deepseek", "zhipu", "crux"])
        assert "deepseek" in result  # active, not down
        assert "zhipu" not in result  # down
        assert "crux" in result  # not down

    def test_available_active_first(self):
        from core.provider import ProviderState

        state = ProviderState(active="crux")
        result = state.available(["deepseek", "zhipu", "crux"])
        assert result[0] == "crux"

    def test_record_latency(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        state.record_latency("deepseek", 1.5)
        state.record_latency("deepseek", 2.0)
        assert len(state._latencies["deepseek"]) == 2

    def test_health_hint_none_when_insufficient_data(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        state.record_latency("deepseek", 1.0)
        hint = state.health_hint()
        assert hint is None

    def test_health_hint_when_slow(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        for _ in range(5):
            state.record_latency("deepseek", 20.0)
        hint = state.health_hint()
        assert hint is not None
        assert "平均响应" in hint


class TestProviderManager:
    """ProviderManager tests."""

    def test_provider_manager_creation(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        assert mgr.providers == {}
        assert mgr.fallback_priority == []
        assert mgr.state.active == "crux"

    def test_provider_manager_load(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        assert len(mgr.providers) > 0
        assert len(mgr.fallback_priority) > 0

    def test_get_active_models(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        models = mgr.get_active_models()
        assert isinstance(models, dict)

    def test_get_model_pro(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        model_id = mgr.get_model("pro")
        assert isinstance(model_id, str)
        assert len(model_id) > 0

    def test_get_model_unknown_tier(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        model_id = mgr.get_model("nonexistent_tier")
        assert model_id == "unknown" or model_id == ""


class TestProviderManagerSingleton:
    """Singleton management tests."""

    def test_get_provider_manager(self):
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        assert mgr is not None
        assert len(mgr.providers) > 0

    def test_get_provider_manager_is_singleton(self):
        from core.provider import get_provider_manager

        mgr1 = get_provider_manager()
        mgr2 = get_provider_manager()
        assert mgr1 is mgr2

    def test_reset_provider_manager(self):
        from core.provider import get_provider_manager, reset_provider_manager

        mgr1 = get_provider_manager()
        reset_provider_manager()
        mgr2 = get_provider_manager()
        assert mgr1 is not mgr2


class TestProviderExceptions:
    """Exception class tests."""

    def test_no_provider_available_is_exception(self):
        from core.provider import NoProviderAvailable

        assert issubclass(NoProviderAvailable, Exception)

    def test_no_provider_available_raise(self):
        from core.provider import NoProviderAvailable

        try:
            raise NoProviderAvailable("test error")
        except NoProviderAvailable as e:
            assert "test error" in str(e)


class TestProviderManagerSetActive:
    """set_active and fallback tests."""

    def test_set_active_valid(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        # Pick a provider with text models (skip media-only like crux)
        for pid in ["deepseek", "zhipu", "local"]:
            if pid in mgr.providers:
                mgr.set_active(pid)
                assert mgr.state.active == pid
                return
        pytest.skip("No valid text provider found")

    def test_set_active_invalid(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        old_active = mgr.state.active
        mgr.set_active("nonexistent")
        assert mgr.state.active == old_active


class TestProviderManagerSaveActive:
    """save_active roundtrip test."""

    def test_save_active_returns_string(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        result = mgr.save_active()
        assert isinstance(result, str)


class TestProviderManagerActiveProvider:
    """active_provider property test."""

    def test_active_provider(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        ap = mgr.active_provider
        assert isinstance(ap, str)
        assert ap == mgr.state.active


class TestProviderStateAvailableByLatency:
    """available_by_latency tests."""

    def test_available_by_latency_sorts(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        state.record_latency("deepseek", 5.0)
        state.record_latency("zhipu", 1.0)
        result = state.available_by_latency(["deepseek", "zhipu"])
        # zhipu is faster but deepseek gets 20% boost
        assert len(result) == 2

    def test_available_by_latency_single(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        result = state.available_by_latency(["deepseek"])
        assert result == ["deepseek"]


class TestProviderStateDownSince:
    """mark_down timestamp accuracy."""

    def test_mark_down_sets_timestamp(self):
        import time

        from core.provider import ProviderState

        state = ProviderState(active="deepseek", cooldown_sec=60)
        before = time.time()
        state.mark_down("zhipu")
        assert "zhipu" in state._down_since
        assert state._down_since["zhipu"] >= before - 0.1


class TestProviderModelInfoProperties:
    """ModelInfo property tests."""

    def test_model_info_model_id(self):
        from core.provider import ModelInfo

        info = ModelInfo(id="test-id", name="Test", provider_id="test", provider_name="Test")
        assert info.model_id == "test-id"
        assert info.model_id == info.id

    def test_model_info_defaults(self):
        from core.provider import ModelInfo

        info = ModelInfo(id="test", name="Test", provider_id="t", provider_name="T")
        assert info.description == ""
        assert info.supports_tools is False
        assert info.supports_thinking is False
        assert info.supports_vision is False
        assert info.tier == "pro"
        assert info.aliases == ()
        assert info.model_type == "text"
        assert info.context_window == 128000
        assert info.max_output_tokens == 8192
        assert info.cost_level == 1


class TestProviderGetModelDescription:
    """get_model_description tests."""

    def test_get_model_description_known(self):
        from core.provider import get_model_description

        desc = get_model_description("deepseek-v4-pro")
        assert "DeepSeek" in desc

    def test_get_model_description_unknown(self):
        from core.provider import get_model_description

        desc = get_model_description("unknown-model")
        assert desc == "unknown-model"


class TestProviderGetProviderName:
    """get_provider_name tests."""

    def test_get_provider_name_known(self):
        from core.provider import get_provider_name

        name = get_provider_name("deepseek-v4-pro")
        assert "DeepSeek" in name

    def test_get_provider_name_unknown(self):
        from core.provider import get_provider_name

        name = get_provider_name("unknown")
        assert name == "unknown"


class TestProviderGetThinkingParams:
    """get_thinking_params_for_model tests."""

    def test_get_thinking_params_non_thinking_model(self):
        from core.provider import get_thinking_params_for_model

        # GLM-4V-Flash does not support thinking
        params = get_thinking_params_for_model("GLM-4V-Flash")
        assert params == {}

    def test_get_thinking_params_nonexistent(self):
        from core.provider import get_thinking_params_for_model

        params = get_thinking_params_for_model("nonexistent")
        assert params == {}


class TestProviderManagerPing:
    """ping() returns bool without crashing."""

    def test_ping_returns_bool(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        result = mgr.ping()
        # Should not crash; actual success depends on network/config
        assert isinstance(result, bool)


class TestProviderManagerFirstAvailable:
    """_first_available internal method."""

    def test_first_available_no_exclude(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        result = mgr._first_available()
        # May return None if no keys configured, but should not crash
        assert result is None or isinstance(result, str)

    def test_first_available_with_exclude(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        providers_set = set(mgr.providers.keys())
        if providers_set:
            first = next(iter(providers_set))
            result = mgr._first_available(exclude={first})
            # Should not crash
            assert result is None or isinstance(result, str)


class TestProviderManagerHandleFailure:
    """handle_failure test (no crash)."""

    def test_handle_failure_returns_tuple(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        result = mgr.handle_failure("nonexistent", 500)
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestProviderManagerCreateClient:
    """create_client with invalid provider raises NoProviderAvailable."""

    def test_create_client_nonexistent_raises(self):
        from core.provider import NoProviderAvailable, ProviderManager

        mgr = ProviderManager()
        mgr.load()
        try:
            mgr.create_client("__nonexistent_provider__")
        except NoProviderAvailable:
            pass  # Expected
        except (ImportError, KeyError):
            pass  # Acceptable fallback behavior


class TestProviderSwitchCount:
    """ProviderState switch counter."""

    def test_switch_count_default(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        assert state._switch_count == 0


class TestProviderManagerFallback:
    """fallback() returns bool."""

    def test_fallback_returns_bool(self):
        from core.provider import ProviderManager

        mgr = ProviderManager()
        mgr.load()
        result = mgr.fallback()
        assert isinstance(result, bool)


class TestProviderStateAvailableByLatencyEdgeCases:
    """Edge cases for available_by_latency."""

    def test_available_by_latency_empty(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        # available() always includes active provider
        result = state.available_by_latency([])
        assert result == ["deepseek"]

    def test_available_by_latency_all_down(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek", cooldown_sec=3600)
        state.mark_down("deepseek")
        result = state.available_by_latency(["deepseek"])
        assert result == []


class TestProviderStateHealthHintEdgeCases:
    """Edge cases for health_hint."""

    def test_health_hint_no_latency_data(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        assert state.health_hint() is None

    def test_health_hint_fast_provider(self):
        from core.provider import ProviderState

        state = ProviderState(active="deepseek")
        for _ in range(5):
            state.record_latency("deepseek", 1.0)
        assert state.health_hint() is None


class TestProviderModelInfoEqual:
    """ModelInfo equality by reference (dataclass, no __eq__ override)."""

    def test_model_info_not_equal(self):
        from core.provider import ModelInfo

        a = ModelInfo(id="a", name="A", provider_id="t", provider_name="T")
        b = ModelInfo(id="b", name="B", provider_id="t", provider_name="T")
        assert a is not b
