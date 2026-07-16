"""Tests for core/provider.py — ProviderManager, circuit breaker, failover."""

from core.provider import (
    MODEL_REGISTRY,
    ProviderState,
    get_max_tokens_for_model,
    get_model_info,
    get_provider_manager,
    reset_provider_manager,
    resolve_model_alias,
)


class TestModelRegistry:
    def test_all_models_registered(self):
        assert len(MODEL_REGISTRY) >= 8
        assert "deepseek-v4-pro" in MODEL_REGISTRY
        assert "deepseek-v4-flash" in MODEL_REGISTRY

    def test_model_info_fields(self):
        info = MODEL_REGISTRY["deepseek-v4-pro"]
        assert info.provider_id == "deepseek"
        assert info.supports_tools is True
        assert info.supports_thinking is True
        assert info.context_window == 1_000_000

    def test_resolve_alias(self):
        assert resolve_model_alias("deepseek") == "deepseek-v4-pro"
        assert resolve_model_alias("flash") == "deepseek-v4-flash"
        assert resolve_model_alias("pro") == "deepseek-v4-pro"
        assert resolve_model_alias("nonexistent") is None

    def test_get_model_info(self):
        info = get_model_info("deepseek-v4-pro")
        assert info is not None
        assert info.tier == "heavy"
        info = get_model_info("nonexistent-model")
        assert info is None


class TestMaxTokens:
    def test_tool_call_capped(self):
        tok = get_max_tokens_for_model("deepseek-v4-pro", is_tool_call=True)
        assert tok <= 8192

    def test_text_uses_adapter_default(self):
        tok = get_max_tokens_for_model("deepseek-v4-pro", is_tool_call=False)
        assert tok == 8192  # ProviderAdapter.default_max_tokens

    def test_unknown_model(self):
        tok = get_max_tokens_for_model("unknown-model", is_tool_call=False)
        assert tok == 16384
        tok = get_max_tokens_for_model("unknown-model", is_tool_call=True)
        assert tok == 8192


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        ps = ProviderState(active="test")
        assert ps.circuit_state("test") == "CLOSED"

    def test_opens_after_failures(self):
        ps = ProviderState(active="test")
        for _ in range(3):
            ps.record_failure("test")
        assert ps.circuit_state("test") == "OPEN"

    def test_closes_after_success(self):
        ps = ProviderState(active="test")
        for _ in range(3):
            ps.record_failure("test")
        ps.record_success("test")
        assert ps.circuit_state("test") == "CLOSED"

    def test_half_open_after_cooldown(self):
        ps = ProviderState(active="test", cooldown_sec=0.01)
        for _ in range(3):
            ps.record_failure("test")
        import time
        time.sleep(0.02)
        assert ps.circuit_can_try("test") is True
        # Second try in half-open should be blocked
        assert ps.circuit_can_try("test") is False

    def test_is_down_respects_cooldown(self):
        ps = ProviderState(active="test", cooldown_sec=0.01)
        ps.mark_down("test")
        assert ps.is_down("test") is True
        import time
        time.sleep(0.02)
        assert ps.is_down("test") is False

    def test_available_filters_down(self):
        ps = ProviderState(active="a")
        ps.mark_down("b")
        avail = ps.available(["a", "b", "c"])
        assert "b" not in avail
        assert "a" in avail


class TestProviderManager:
    def test_loads_without_crash(self):
        reset_provider_manager()
        mgr = get_provider_manager()
        assert len(mgr.providers) >= 3
        assert mgr.state.active in mgr.providers

    def test_singleton(self):
        reset_provider_manager()
        mgr1 = get_provider_manager()
        mgr2 = get_provider_manager()
        assert mgr1 is mgr2

    def test_get_model(self):
        mgr = get_provider_manager()
        pro = mgr.get_model("pro")
        assert pro and pro != "unknown"
        light = mgr.get_model("light")
        assert light and light != "unknown"

    def test_set_active(self):
        mgr = get_provider_manager()
        original = mgr.state.active
        try:
            mgr.set_active("deepseek")
            assert mgr.state.active == "deepseek"
        finally:
            mgr.set_active(original)

    def test_create_client_falls_back_for_unknown(self):
        """Unknown provider falls back to first available, doesn't crash."""
        mgr = get_provider_manager()
        # Should not raise — falls back gracefully
        client = mgr.create_client("nonexistent-provider-xyz")
        assert client is not None

    def test_first_available_finds_key(self):
        mgr = get_provider_manager()
        # deepseek should have an API key from .env
        pid = mgr._first_available()
        assert pid is not None

    def test_get_active_models_returns_dict(self):
        mgr = get_provider_manager()
        models = mgr.get_active_models()
        assert isinstance(models, dict)
        assert "pro" in models or "light" in models


class TestProviderState:
    def test_latency_tracking(self):
        ps = ProviderState(active="test")
        ps.record_latency("test", 1.0)
        ps.record_latency("test", 2.0)
        ps.record_latency("test", 3.0)
        hint = ps.health_hint()
        assert hint is None  # avg=2s, below 15s threshold

    def test_health_warns_on_slow(self):
        ps = ProviderState(active="test")
        ps.record_latency("test", 20.0)
        ps.record_latency("test", 20.0)
        ps.record_latency("test", 20.0)
        hint = ps.health_hint()
        assert hint is not None
        assert "20.0s" in hint or "慢" in hint
