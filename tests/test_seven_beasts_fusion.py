"""Tests for core/seven_beasts_fusion.py — seven beasts fusion prompt."""

from core.seven_beasts_fusion import SEVEN_BEASTS_FUSION, get_fusion_prompt


class TestFusionPrompt:
    def test_is_string(self):
        assert isinstance(SEVEN_BEASTS_FUSION, str)
        assert len(SEVEN_BEASTS_FUSION) > 100

    def test_contains_all_seven_beasts(self):
        assert "白虎" in SEVEN_BEASTS_FUSION
        assert "青龙" in SEVEN_BEASTS_FUSION
        assert "朱雀" in SEVEN_BEASTS_FUSION
        assert "玄武" in SEVEN_BEASTS_FUSION
        assert "麒麟" in SEVEN_BEASTS_FUSION
        assert "螣蛇" in SEVEN_BEASTS_FUSION
        assert "应龙" in SEVEN_BEASTS_FUSION

    def test_contains_fusion_concept(self):
        assert "七兽融合" in SEVEN_BEASTS_FUSION
        assert "魂魄交融" in SEVEN_BEASTS_FUSION

    def test_contains_collaboration_chains(self):
        assert "协同链" in SEVEN_BEASTS_FUSION

    def test_get_fusion_prompt_returns_string(self):
        result = get_fusion_prompt()
        assert isinstance(result, str)
        assert result == SEVEN_BEASTS_FUSION

    def test_not_empty(self):
        result = get_fusion_prompt()
        assert len(result) > 500

    def test_contains_user_identity(self):
        assert "deepseek-v4-pro" in SEVEN_BEASTS_FUSION
        assert "CRUX Studio v5.0" in SEVEN_BEASTS_FUSION
