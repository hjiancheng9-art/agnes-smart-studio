"""三级 tier 路由测试（v6.0 动态路由，配置来源 models.json）。

覆盖:
- ModelRouter.select_for_tier: light / pro / heavy / auto 映射
- ModelRouter.select: 按任务类型 + 能力旗标路由
- ModelRouter tier 常量与 MODEL_PROFILES 一致性
- 三级 tier 接入点（agent.py / multi_agent.py 调用契约）
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent import ModelRouter


class TestTierConstants:
    """tier 常量定义稳定。"""

    def test_three_tiers_defined(self):
        assert ModelRouter.TIER_LIGHT == "light"
        assert ModelRouter.TIER_PRO == "pro"
        assert ModelRouter.TIER_HEAVY == "heavy"

    def test_tiers_distinct(self):
        tiers = {ModelRouter.TIER_LIGHT, ModelRouter.TIER_PRO, ModelRouter.TIER_HEAVY}
        assert len(tiers) == 3


class TestSelectForTier:
    """阶段 3c: select_for_tier 三级映射。

    契约:
    - light → deepseek-v4-flash（最便宜快档）
    - pro   → deepseek-v4-flash（flash 覆盖 pro 档轻量 tool calling）
    - heavy → deepseek-v4-pro（深度思考 + 1M 上下文）
    - auto/未知 → primary（最稳）
    """

    def test_light_tier_returns_light(self):
        router = ModelRouter()
        assert router.select_for_tier("light") == router.light

    def test_pro_tier_returns_pro(self):
        router = ModelRouter()
        assert router.select_for_tier("pro") == router.pro

    def test_heavy_tier_returns_primary(self):
        router = ModelRouter()
        assert router.select_for_tier("heavy") == router.primary

    def test_auto_tier_returns_primary(self):
        router = ModelRouter()
        assert router.select_for_tier("auto") == router.primary

    def test_unknown_tier_returns_primary(self):
        """未知 tier 字符串退回 primary（安全默认）。"""
        router = ModelRouter()
        assert router.select_for_tier("nonexistent") == router.primary

    def test_light_and_pro_are_valid_models(self):
        """light 和 pro 都是有效的模型 ID（不一定相同）。"""
        router = ModelRouter()
        assert isinstance(router.light, str) and len(router.light) > 0
        assert isinstance(router.pro, str) and len(router.pro) > 0

    def test_heavy_distinct_from_light(self):
        """heavy 档必须与 light 档不同（深度思考 vs 快速响应）。"""
        router = ModelRouter()
        assert router.select_for_tier("heavy") != router.select_for_tier("light")


class TestRouterDefaults:
    """ModelRouter 默认值契约（v6.0 动态读取 models.json）。"""

    def test_default_light_is_flash(self):
        """当前 models.json active=deepseek → light=deepseek-v4-flash。"""
        router = ModelRouter()
        assert router.light == "deepseek-v4-flash"

    def test_default_vision_is_glm_4v_flash(self):
        """视觉模型优先智谱多模态（GLM-4V-Flash），比 agnes-1.5-flash 视觉能力更强。"""
        router = ModelRouter()
        assert router.vision_model == "GLM-4V-Flash"

    def test_primary_is_valid_model(self):
        """primary 必须是已注册的有效模型 ID。"""
        from core.provider import MODEL_REGISTRY

        router = ModelRouter()
        assert router.primary in MODEL_REGISTRY or router.primary == "deepseek-v4-pro"


class TestSelectRouting:
    """ModelRouter.select 任务类型路由。"""

    def test_image_generation_hardcoded(self):
        router = ModelRouter()
        assert router.select(task_type="image_generation") == "agnes-image-2.1-flash"

    def test_video_generation_hardcoded(self):
        router = ModelRouter()
        assert router.select(task_type="video_generation") == "agnes-video-v2.0"

    def test_vision_uses_independent_channel(self):
        """视觉需求走独立通道（agnes-1.5-flash），不受 tier 影响。"""
        router = ModelRouter()
        assert router.select(needs_vision=True) == router.vision_model

    def test_long_context_uses_primary(self):
        router = ModelRouter()
        assert router.select(needs_long_context=True) == router.primary

    def test_tools_with_thinking_uses_primary(self):
        """tool calling + 思考 → heavy tier（deepseek-v4-pro）。"""
        router = ModelRouter()
        assert router.select(needs_tools=True, needs_thinking=True) == router.primary

    def test_tools_without_thinking_uses_light(self):
        """tool calling 无思考 → light tier（flash，省成本）。"""
        router = ModelRouter()
        assert router.select(needs_tools=True, needs_thinking=False) == router.light

    def test_chat_task_uses_light(self):
        """日常对话 → light tier（最省）。"""
        router = ModelRouter()
        assert router.select(task_type="chat") == router.light

    def test_code_task_uses_primary(self):
        """代码任务 → heavy tier（深度思考）。"""
        router = ModelRouter()
        assert router.select(task_type="code") == router.primary

    def test_unknown_task_defaults_to_primary(self):
        """未知任务类型 → primary（最稳）。"""
        router = ModelRouter()
        assert router.select(task_type="unknown_xyz") == router.primary


class TestModelProfiles:
    """MODEL_PROFILES tier 分配一致性。"""

    def test_flash_profile_is_light(self):
        assert ModelRouter.MODEL_PROFILES["deepseek-v4-flash"]["tier"] == "light"

    def test_pro_profile_is_heavy(self):
        assert ModelRouter.MODEL_PROFILES["deepseek-v4-pro"]["tier"] == "heavy"

    def test_flash_supports_tools(self):
        """阶段 3c: flash 支持 tool calling（覆盖 pro 档轻量场景）。"""
        assert ModelRouter.MODEL_PROFILES["deepseek-v4-flash"]["supports_tools"] is True

    def test_flash_no_thinking(self):
        """flash 非思考模式（思考需切 pro）。"""
        assert ModelRouter.MODEL_PROFILES["deepseek-v4-flash"]["supports_thinking"] is False

    def test_pro_supports_thinking(self):
        assert ModelRouter.MODEL_PROFILES["deepseek-v4-pro"]["supports_thinking"] is True

    def test_vision_profile_independent(self):
        """agnes-1.5-flash tier=light 但走独立视觉通道。"""
        assert ModelRouter.MODEL_PROFILES["agnes-1.5-flash"]["supports_vision"] is True


class TestFallbackChain:
    """ModelRouter fallback 链构建（v6.0: 免费优先，付费兜底）。"""

    def test_fallback_chain_is_non_empty(self):
        router = ModelRouter()
        chain = router._fallback_chain
        assert len(chain) >= 1
        assert all(isinstance(m, str) and len(m) > 0 for m in chain)

    def test_fallback_chain_first_is_free_provider(self):
        """免费 provider (zhipu) 的模型排在链首。"""
        router = ModelRouter()
        chain = router._fallback_chain
        assert chain[0] == "glm-4.7-flash"

    def test_fallback_chain_last_is_paid_provider(self):
        """付费 provider (copilot) 的模型排在链尾。"""
        router = ModelRouter()
        chain = router._fallback_chain
        assert chain[-1] == "gpt-5-mini"

    def test_get_fallback_returns_next(self):
        router = ModelRouter()
        chain = router._fallback_chain
        if len(chain) >= 2:
            nxt = router.get_fallback(chain[0])
            assert nxt == chain[1]

    def test_get_fallback_none_at_end(self):
        """链尾模型无后续 fallback。"""
        router = ModelRouter()
        chain = router._fallback_chain
        assert router.get_fallback(chain[-1]) is None

    def test_get_fallback_unknown_model_returns_none(self):
        router = ModelRouter()
        assert router.get_fallback("nonexistent-model") is None
