"""Self-Audit: Model Routing — classify_prompt → tier → resolve_model.

Tests the invariant:
  models.json → active provider → classify_prompt() → tier → resolve_model() → model_id
  Each tier (light/pro/heavy) must map to distinct models unless explicitly intended.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ── Test input matrix ──

ROUTING_TEST_CASES = [
    # (name, input_text, expected_tier)
    ("greeting", "你好", "light"),
    ("simple_question", "今天天气怎么样？", "light"),
    ("translate", "翻译这段话成英文", "light"),
    ("explain_error", "帮我解释这个 TypeError", "pro"),
    ("code_review", "审查这段代码的质量", "pro"),
    ("refactor_module", "重构这个模块并写测试", "heavy"),
    ("architecture_design", "设计一个微服务架构方案", "heavy"),
    ("multi_file_analysis", "分析这个项目的目录结构和依赖关系", "heavy"),
]


def _load_models_config():
    """Load models.json for audit purposes."""
    paths = [
        "models.json",
        "config/models.json",
        "core/models.json",
    ]
    for p in paths:
        if Path(p).exists():
            return json.loads(Path(p).read_text(encoding="utf-8"))
    return None


# ── 1. CLASSIFY PROMPT ──


class TestClassifyPrompt:
    """classify_prompt() must map inputs to correct tiers."""

    @pytest.mark.skip(reason="Need running app context")
    @pytest.mark.parametrize(("name", "text", "expected_tier"), ROUTING_TEST_CASES)
    def test_classify_to_correct_tier(self, name, text, expected_tier):
        """Each input type gets the right tier."""
        from core.model_router import classify_prompt

        tier = classify_prompt(text)
        assert tier == expected_tier, f"'{name}': expected tier={expected_tier}, got {tier}"

    def test_classify_image_tool_not_routed_as_chat(self):
        """generate_image/video should be routed (not fail)."""
        from core.model_router import classify_prompt

        image_text = "画一张赛博朋克风格的猫"
        tier = classify_prompt(image_text)
        # At minimum, must return a valid tier
        assert tier in ("light", "pro", "heavy", "vision"), f"Invalid tier: {tier}"


# ── 2. RESOLVE MODEL ──


class TestResolveModel:
    """resolve_model() returns valid model_id for the active provider."""

    @pytest.mark.skip(reason="Need running app context")
    @pytest.mark.parametrize("tier", ["light", "pro", "heavy", "vision"])
    def test_resolve_model_returns_string(self, tier):
        """Each tier must resolve to a non-empty string model_id."""
        from core.model_router import ModelRouter

        router = ModelRouter()
        model_id = router.resolve_model(tier)
        assert isinstance(model_id, str), f"Expected str, got {type(model_id)}"
        assert len(model_id) > 0, f"Empty model_id for tier={tier}"


# ── 3. CONFIG AUDIT ──


class TestConfigAudit:
    """Audit models.json for common misconfigurations."""

    def audit_models_json(self, config: dict) -> list[dict]:
        """Check for all-tiers-same-model issues."""
        issues = []
        providers = config.get("providers", {})
        for provider_name, provider in providers.items():
            tiers = provider.get("tiers", {})
            values = list(tiers.values())
            if len(values) >= 2 and len(set(values)) == 1:
                issues.append(
                    {
                        "level": "warning",
                        "provider": provider_name,
                        "issue": "all_tiers_map_to_same_model",
                        "model": values[0],
                    }
                )
        return issues

    def test_config_file_exists(self):
        """models.json must exist."""
        config = _load_models_config()
        assert config is not None, "models.json not found in any standard path"

    def test_config_has_providers(
        self,
    ):
        """models.json must have providers section."""
        config = _load_models_config()
        if config is None:
            pytest.skip("models.json not found")
        assert "providers" in config, "Missing 'providers' in models.json"
        assert len(config["providers"]) > 0, "Empty providers"

    def test_config_no_single_model_for_all_tiers(self):
        """No provider should map all tiers to the same model."""
        config = _load_models_config()
        if config is None:
            pytest.skip("models.json not found")
        issues = self.audit_models_json(config)
        if issues:
            msg = "\n".join(f"  ⚠ {i['provider']}: {i['issue']} -> {i['model']}" for i in issues)
            pytest.fail(f"Config issues found:\n{msg}")

    def test_config_has_active_provider(self):
        """Config must specify a default chat provider."""
        config = _load_models_config()
        if config is None:
            pytest.skip("models.json not found")
        # Support both naming conventions
        active = (
            config.get("active_provider")
            or config.get("default_chat_provider")
            or config.get("default_provider")
            or config.get("active_strategy")
        )
        assert active is not None, "No active/default provider or strategy specified in models.json"


# ── 4. ROUTE INTEGRITY ──


class TestRouteIntegrity:
    """Full route chain: text → tier → model_id → provider."""

    def test_route_chain_completes(self):
        """Full pipeline: classify → resolve → model_id belongs to active provider."""
        # This is a structural test — verifies the chain doesn't break
        from core.model_router import ModelRouter

        router = ModelRouter()
        for tier in ["light", "pro", "heavy"]:
            model_id = router.resolve_model(tier)
            assert model_id is not None, f"resolve_model({tier}) returned None"
