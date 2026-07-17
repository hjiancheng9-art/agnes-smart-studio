"""Unit tests for core.session_config — SessionConfig dataclass."""

from __future__ import annotations

from core.session_config import SessionConfig


class TestSessionConfigDefaults:
    def test_default_model_is_empty(self):
        cfg = SessionConfig()
        assert cfg.model == ""

    def test_default_code_mode_false(self):
        cfg = SessionConfig()
        assert cfg.code_mode is False

    def test_default_agent_mode_false(self):
        cfg = SessionConfig()
        assert cfg.agent_mode is False

    def test_default_auto_model_true(self):
        cfg = SessionConfig()
        assert cfg.auto_model is True

    def test_default_enable_thinking_true(self):
        cfg = SessionConfig()
        assert cfg.enable_thinking is True

    def test_default_browser_disabled(self):
        cfg = SessionConfig()
        assert cfg.browser_enabled is False

    def test_default_notebook_disabled(self):
        cfg = SessionConfig()
        assert cfg.notebook_enabled is False

    def test_default_audio_disabled(self):
        cfg = SessionConfig()
        assert cfg.audio_enabled is False

    def test_default_unlimited_tools_false(self):
        cfg = SessionConfig()
        assert cfg.unlimited_tools is False

    def test_default_consecutive_skips_zero(self):
        cfg = SessionConfig()
        assert cfg.consecutive_skips == 0

    def test_default_mode_is_chat(self):
        cfg = SessionConfig()
        assert cfg.mode == "chat"

    def test_default_intel_mode_balanced(self):
        cfg = SessionConfig()
        assert cfg.intel_mode == "BALANCED"


class TestSessionConfigCustom:
    def test_model_set_on_init(self):
        cfg = SessionConfig(model="deepseek-v4-pro")
        assert cfg.model == "deepseek-v4-pro"

    def test_code_mode_set_on_init(self):
        cfg = SessionConfig(code_mode=True)
        assert cfg.code_mode is True

    def test_all_fields_independent(self):
        """Verify that setting one field doesn't affect others."""
        cfg = SessionConfig(
            model="pro",
            code_mode=True,
            agent_mode=True,
            browser_enabled=True,
            enable_thinking=False,
        )
        assert cfg.model == "pro"
        assert cfg.code_mode is True
        assert cfg.agent_mode is True
        assert cfg.browser_enabled is True
        assert cfg.enable_thinking is False
        assert cfg.auto_model is True  # default untouched
        assert cfg.notebook_enabled is False  # default untouched

    def test_auto_tier_order_default(self):
        cfg = SessionConfig()
        assert cfg.auto_tier_order == ["reasoner", "pro", "light"]

    def test_mutable_fields_independent_instances(self):
        """auto_tier_order should be a new list per instance."""
        cfg1 = SessionConfig()
        cfg2 = SessionConfig()
        cfg1.auto_tier_order.append("extra")
        assert len(cfg2.auto_tier_order) == 3  # not affected by cfg1 mutation


class TestSessionConfigMethods:
    def test_reset_skips(self):
        cfg = SessionConfig(consecutive_skips=5)
        cfg.reset_skips()
        assert cfg.consecutive_skips == 0

    def test_set_deep(self):
        cfg = SessionConfig(enable_thinking=False)
        cfg.set_deep()
        assert cfg.enable_thinking is True

    def test_set_fast(self):
        cfg = SessionConfig(enable_thinking=True)
        cfg.set_fast()
        assert cfg.enable_thinking is False
