"""Tests for core/golden_finger.py — golden finger prompt and summary."""

from core.golden_finger import (
    GOLDEN_FINGER_PROMPT,
    get_golden_finger_prompt,
    get_golden_finger_summary,
)


class TestGoldenFingerPrompt:
    def test_prompt_is_string(self):
        assert isinstance(GOLDEN_FINGER_PROMPT, str)
        assert len(GOLDEN_FINGER_PROMPT) > 100

    def test_prompt_contains_key_sections(self):
        assert "金手指谱" in GOLDEN_FINGER_PROMPT
        assert "残魂老祖" in GOLDEN_FINGER_PROMPT
        assert "凭什么强" in GOLDEN_FINGER_PROMPT

    def test_get_prompt_returns_same(self):
        result = get_golden_finger_prompt()
        assert result == GOLDEN_FINGER_PROMPT
        assert isinstance(result, str)

    def test_prompt_not_empty(self):
        result = get_golden_finger_prompt()
        assert len(result) > 500


class TestGoldenFingerSummary:
    def test_summary_is_string(self):
        result = get_golden_finger_summary()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_summary_contains_key_items(self):
        result = get_golden_finger_summary()
        assert "金手指" in result
