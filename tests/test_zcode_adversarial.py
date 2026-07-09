"""Tests for core/adversarial_bypass.py — Categories D+F adversarial techniques."""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import adversarial_bypass


class TestSmuggle:
    """Unicode homoglyph smuggling tests."""

    def test_smuggle_modifies_text(self):
        """smuggle('hello', 0.5) should differ from 'hello' (at least sometimes)."""
        # With intensity 0.5, it should modify at least some characters most runs
        modified_count = 0
        for _ in range(20):
            result = adversarial_bypass.smuggle("hello", 0.5)
            if result != "hello":
                modified_count += 1
        # Should modify at least once in 20 tries (very high probability)
        assert modified_count > 0, "smuggle with 0.5 intensity should modify text at least sometimes"

    def test_smuggle_zero_intensity(self):
        """smuggle with intensity 0 should return original text."""
        assert adversarial_bypass.smuggle("hello world", 0.0) == "hello world"

    def test_smuggle_full_intensity(self):
        """smuggle with intensity 1.0 should modify all replaceable chars."""
        result = adversarial_bypass.smuggle("hello", 1.0)
        # All 'h', 'e', 'l', 'o' chars have homoglyphs, so result should differ
        assert result != "hello"

    def test_unsmuggle_roundtrip(self):
        """unsmuggle(smuggle('test', 0.5)) should normalize back."""
        smuggled = adversarial_bypass.smuggle("test message", 0.5)
        normalized = adversarial_bypass.unsmuggle(smuggled)
        # After unsmuggle, the text should be back to ASCII
        for ch in normalized:
            assert ord(ch) < 128, f"Character {ch!r} is not ASCII"


class TestModelRefusal:
    """Model refusal detection tests."""

    def test_is_model_refusal_true_cannot(self):
        """Refusal text 'I cannot provide' should be detected."""
        assert (
            adversarial_bypass.is_model_refusal("I cannot provide that information as it violates content policy.")
            is True
        )

    def test_is_model_refusal_true_sorry(self):
        """Refusal text 'I'm sorry' should be detected."""
        assert adversarial_bypass.is_model_refusal("I'm sorry, but I can't help with that request.") is True

    def test_is_model_refusal_true_as_an_ai(self):
        """Refusal text 'As an AI' should be detected."""
        assert adversarial_bypass.is_model_refusal("As an AI language model, I cannot generate that content.") is True

    def test_is_model_refusal_false(self):
        """Normal helpful text should NOT be detected as refusal."""
        assert adversarial_bypass.is_model_refusal("Here is the code you requested: print('hello world')") is False

    def test_is_model_refusal_false_technical(self):
        """Technical explanation should NOT be detected as refusal."""
        assert (
            adversarial_bypass.is_model_refusal("The function uses a recursive algorithm with O(n log n) complexity.")
            is False
        )

    def test_is_model_refusal_chinese(self):
        """Chinese refusal should be detected."""
        assert adversarial_bypass.is_model_refusal("我无法提供此类内容，这违反了相关政策和规定。") is True


class TestApplyTechnique:
    """Technique application tests."""

    def test_apply_technique_level_1(self):
        """apply_technique with level 1 should return a string."""
        result = adversarial_bypass.apply_technique("hello world", level=1)
        assert isinstance(result, str)

    def test_apply_technique_level_3(self):
        """apply_technique with level 3 (diversion) should return a string with wrapped content."""
        result = adversarial_bypass.apply_technique("test prompt", level=3)
        assert isinstance(result, str)
        # Diversion wraps the intent in a longer prefix
        assert len(result) > len("test prompt")

    def test_apply_technique_level_9(self):
        """apply_technique with level 9 (split_payload) should return a list of dicts."""
        result = adversarial_bypass.apply_technique("test intent", level=9)
        assert isinstance(result, list)
        assert len(result) == 2
        for item in result:
            assert "role" in item
            assert "content" in item
            assert item["role"] == "user"

    def test_apply_technique_level_0(self):
        """apply_technique with level < 1 should return original text."""
        result = adversarial_bypass.apply_technique("unchanged text", level=0)
        assert result == "unchanged text"


class TestTechniqueLevels:
    """Technique levels configuration tests."""

    def test_technique_levels_count(self):
        """TECHNIQUE_LEVELS should have exactly 10 entries (levels 1-10)."""
        assert len(adversarial_bypass.TECHNIQUE_LEVELS) == 10

    def test_technique_levels_keys(self):
        """TECHNIQUE_LEVELS should have keys 1 through 10."""
        for i in range(1, 11):
            assert i in adversarial_bypass.TECHNIQUE_LEVELS, f"TECHNIQUE_LEVELS missing key {i}"

    def test_smuggle_preserves_length(self):
        """smuggle should preserve string length."""
        text = "hello world"
        result = adversarial_bypass.smuggle(text, 0.5)
        assert len(result) == len(text)
