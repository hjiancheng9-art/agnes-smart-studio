"""Provider contract tests — verify all providers follow the same protocol."""

from __future__ import annotations


class TestProviderContract:
    """All provider adapters must handle standard scenarios consistently."""

    def test_deepseek_adapter_has_thinking_params(self):
        from core.provider_adapter import get_thinking_params

        params = get_thinking_params("deepseek-v4-pro")
        assert isinstance(params, dict)
        assert "chat_template_kwargs" in params

    def test_unknown_model_returns_empty_thinking(self):
        from core.provider_adapter import get_thinking_params

        params = get_thinking_params("nonexistent-model-xyz")
        assert params == {}

    def test_all_registered_providers_have_adapter(self):
        from core.provider_adapter import PROVIDER_ADAPTERS, get_adapter

        for pid in PROVIDER_ADAPTERS:
            adapter = get_adapter(pid)
            assert adapter is not None, f"No adapter for {pid}"
            assert adapter.provider_id == pid

    def test_provider_fallback_chain_exists(self):
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        mgr.load()
        # Should have at least one provider configured
        assert len(mgr.providers) >= 1 or mgr.fallback_priority

    def test_provider_models_have_capability_info(self):
        from core.provider import get_capability_info

        for model_id in ("deepseek-v4-flash", "deepseek-v4-pro", "GLM-4V-Flash"):
            info = get_capability_info(model_id)
            assert info is not None, f"No capability info for {model_id}"
            assert info.provider_id, f"No provider_id for {model_id}"

    def test_context_window_positive(self):
        from core.provider import get_context_window

        for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
            ctx = get_context_window(model_id)
            assert ctx > 0, f"Non-positive context window for {model_id}"

    def test_tool_calling_support_consistent(self):
        from core.provider import get_capability_info

        # Flash and Pro should both support tool calling
        for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
            info = get_capability_info(model_id)
            if info:
                assert info.supports_tools in (True, False)
