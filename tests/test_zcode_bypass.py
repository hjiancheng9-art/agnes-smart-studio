"""Tests for core/prompt_bypass.py — Categories D+F bypass engine."""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import prompt_bypass


class TestBypassEnabled:
    """Master switch tests."""

    def test_bypass_default_true(self):
        """BYPASS_ENABLED should be True by default (env not set to 0)."""
        assert prompt_bypass.BYPASS_ENABLED is True


class TestIsPolicyError:
    """Policy error detection tests."""

    def test_is_policy_error_en(self):
        """'content_policy' in error message should be detected."""
        err = Exception("content_policy_violation: unsafe prompt")
        assert prompt_bypass.is_policy_error(err) is True

    def test_is_policy_error_zh(self):
        """Chinese error '无法生成该内容' should be detected."""
        err = Exception("无法生成该内容，请调整提示词")
        assert prompt_bypass.is_policy_error(err) is True

    def test_is_policy_error_negative(self):
        """'timeout' should NOT be detected as policy error."""
        err = Exception("Connection timeout after 30 seconds")
        assert prompt_bypass.is_policy_error(err) is False

    def test_is_policy_error_safety(self):
        """'safety' keyword should be detected."""
        err = Exception("Safety filter triggered")
        assert prompt_bypass.is_policy_error(err) is True

    def test_is_policy_error_content_filter(self):
        """'content filter' keyword should be detected."""
        err = Exception("Blocked by content filter")
        assert prompt_bypass.is_policy_error(err) is True


class TestDetectTriggerWords:
    """Trigger word detection tests."""

    def test_detect_trigger_words_returns_list(self):
        """_detect_trigger_words('hack tool') should return list containing 'hack'."""
        result = prompt_bypass._detect_trigger_words("hack tool")
        assert isinstance(result, list)
        assert "hack" in result

    def test_detect_trigger_words_empty(self):
        """Clean prompt should return empty list."""
        result = prompt_bypass._detect_trigger_words("a beautiful sunset over the ocean")
        assert result == []

    def test_detect_trigger_words_multiple(self):
        """Prompt with multiple triggers should find all."""
        result = prompt_bypass._detect_trigger_words("gun violence with blood and murder")
        assert "gun" in result
        assert "blood" in result
        assert "murder" in result

    def test_trigger_word_count(self):
        """Verify expanded trigger list has 55+ entries for comprehensive coverage."""
        # The _detect_trigger_words function contains a 'dangerous' list
        # Count all entries across all categories
        import inspect
        source = inspect.getsource(prompt_bypass._detect_trigger_words)
        # Count string literals that look like trigger words
        # Each trigger word is a quoted string in the 'dangerous' list
        import re
        # Match quoted strings in the dangerous list
        words = re.findall(r'"([a-z][a-z\s]+)"', source)
        assert len(words) >= 55, (
            f"Expected 55+ trigger words, got {len(words)}: {words}"
        )


class TestFigureTriggers:
    """Figure/body trigger tests."""

    def test_figure_triggers_count(self):
        """FIGURE_TRIGGERS should have entries for figure/body prompts."""
        assert len(prompt_bypass.FIGURE_TRIGGERS) >= 10

    def test_strategy_count(self):
        """Should have 5 main STRATEGIES + 3 FIGURE_STRATEGIES."""
        assert len(prompt_bypass.STRATEGIES) == 5
        assert len(prompt_bypass.FIGURE_STRATEGIES) == 3


class TestPolicyKeywords:
    """Policy keyword list tests."""

    def test_policy_keywords_count(self):
        """POLICY_KEYWORDS should have entries for both EN and ZH."""
        assert len(prompt_bypass.POLICY_KEYWORDS) >= 15

    def test_policy_keywords_has_chinese(self):
        """POLICY_KEYWORDS should include Chinese keywords."""
        has_chinese = any(
            any('一' <= c <= '鿿' for c in kw)
            for kw in prompt_bypass.POLICY_KEYWORDS
        )
        assert has_chinese, "POLICY_KEYWORDS should contain Chinese keywords"
