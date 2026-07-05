"""Tests for utils/unicode_safety.py — surrogate character sanitization.

These tests validate that the Unicode safety layer:
1. Detects and removes lone surrogate characters from strings
2. Recursively sanitizes nested dict/list/tuple structures
3. Correctly reports the presence of surrogates
4. Validates UTF-8 encodability of sanitized output
5. Properly handles clean data (fast-path, no allocation)
"""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, ".")

from utils.unicode_safety import (
    InvalidUnicodePayloadError,
    ensure_utf8_encodable,
    find_surrogate_paths,
    has_surrogate,
    sanitize_payload,
    sanitize_text,
)

# ── Lone surrogate test strings ────────────────────────────────
_SURROGATE_HIGH = "\ud800"  # U+D800
_SURROGATE_LOW = "\udfff"   # U+DFFF
_SURROGATE_MID = "\ud900"   # U+D900


class TestSanitizeText:
    """Tests for sanitize_text() — the core string-level sanitizer."""

    def test_clean_string_passes_through(self):
        """Clean strings should be returned unchanged (fast-path)."""
        assert sanitize_text("hello world") == "hello world"
        assert sanitize_text("中文测试") == "中文测试"
        assert sanitize_text("") == ""

    def test_lone_surrogate_high_is_replaced(self):
        """U+D800 should be replaced with the replacement character."""
        result = sanitize_text(f"bad{_SURROGATE_HIGH}char")
        assert _SURROGATE_HIGH not in result
        assert "�" in result
        assert len(result) == len("bad_char")  # replacement is 1 char

    def test_lone_surrogate_low_is_replaced(self):
        """U+DFFF should be replaced."""
        result = sanitize_text(f"test{_SURROGATE_LOW}end")
        assert _SURROGATE_LOW not in result

    def test_multiple_surrogates_all_replaced(self):
        """All surrogates should be replaced, not just the first."""
        result = sanitize_text(f"{_SURROGATE_HIGH}a{_SURROGATE_LOW}b{_SURROGATE_MID}")
        assert _SURROGATE_HIGH not in result
        assert _SURROGATE_LOW not in result
        assert _SURROGATE_MID not in result

    def test_result_is_utf8_encodable(self):
        """Sanitized text must always be valid UTF-8."""
        result = sanitize_text(f"data{_SURROGATE_HIGH}{_SURROGATE_LOW}end")
        result.encode("utf-8")  # must not raise

    def test_non_string_passes_through(self):
        """Non-string inputs should be returned as-is."""
        assert sanitize_text(42) == 42
        assert sanitize_text(None) is None
        assert sanitize_text(["a", "b"]) == ["a", "b"]

    def test_custom_replacement(self):
        """Custom replacement character should be used."""
        result = sanitize_text(f"x{_SURROGATE_HIGH}y", replacement="?")
        assert result == "x?y"


class TestSanitizePayload:
    """Tests for sanitize_payload() — recursive structure sanitizer."""

    def test_flat_dict(self):
        result = sanitize_payload({"key": f"bad{_SURROGATE_HIGH}val"})
        assert _SURROGATE_HIGH not in result["key"]

    def test_nested_dict(self):
        payload = {
            "messages": [
                {"role": "user", "content": f"hello{_SURROGATE_LOW}world"},
                {"role": "assistant", "content": "clean"},
            ]
        }
        result = sanitize_payload(payload)
        assert _SURROGATE_LOW not in result["messages"][0]["content"]
        assert result["messages"][1]["content"] == "clean"

    def test_nested_list(self):
        data = [f"a{_SURROGATE_HIGH}", [f"b{_SURROGATE_LOW}", "c"]]
        result = sanitize_payload(data)
        assert _SURROGATE_HIGH not in result[0]
        assert _SURROGATE_LOW not in result[1][0]
        assert result[1][1] == "c"

    def test_tuple_preserved(self):
        data = (f"x{_SURROGATE_HIGH}", "y")
        result = sanitize_payload(data)
        assert isinstance(result, tuple)
        assert _SURROGATE_HIGH not in result[0]
        assert result[1] == "y"

    def test_mixed_types_preserved(self):
        data = {"str": "clean", "num": 42, "bool": True, "none": None, "float": 3.14}
        result = sanitize_payload(data)
        assert result == data

    def test_result_is_json_serializable(self):
        """Sanitized payload must be JSON-serializable with ensure_ascii=False."""
        payload = {"text": f"test{_SURROGATE_HIGH}{_SURROGATE_LOW}"}
        result = sanitize_payload(payload)
        json.dumps(result, ensure_ascii=False).encode("utf-8")  # must not raise

    def test_large_nested_structure(self):
        """Stress test: deeply nested structure with surrogates at various levels."""
        payload = {"a": [{"b": {"c": [f"d{_SURROGATE_HIGH}e"] * 10}}] * 5}
        result = sanitize_payload(payload)
        # Verify all surrogates are gone
        flat = json.dumps(result, ensure_ascii=False)
        assert _SURROGATE_HIGH not in flat
        flat.encode("utf-8")


class TestHasSurrogate:
    """Tests for has_surrogate() — fast detection without sanitization."""

    def test_clean_string(self):
        assert has_surrogate("hello") is False

    def test_dirty_string(self):
        assert has_surrogate(f"bad{_SURROGATE_HIGH}") is True

    def test_dirty_dict(self):
        assert has_surrogate({"x": f"bad{_SURROGATE_LOW}"}) is True

    def test_clean_dict(self):
        assert has_surrogate({"x": "clean"}) is False

    def test_dirty_nested_list(self):
        assert has_surrogate(["a", ["b", f"c{_SURROGATE_HIGH}"]]) is True

    def test_clean_nested_list(self):
        assert has_surrogate(["a", ["b", "c"]]) is False

    def test_non_string_types(self):
        assert has_surrogate(42) is False
        assert has_surrogate(None) is False
        assert has_surrogate(True) is False


class TestFindSurrogatePaths:
    """Tests for find_surrogate_paths() — diagnostic tool for dirty fields."""

    def test_simple_string(self):
        paths = find_surrogate_paths(f"ab{_SURROGATE_HIGH}cd")
        assert len(paths) == 1
        assert "root[2]" in paths[0]
        assert "D800" in paths[0]

    def test_nested_dict(self):
        payload = {"messages": [{"content": f"x{_SURROGATE_LOW}y"}]}
        paths = find_surrogate_paths(payload)
        assert len(paths) == 1
        assert "messages" in paths[0]
        assert "content" in paths[0]
        assert "DFFF" in paths[0]

    def test_clean_payload_returns_empty(self):
        paths = find_surrogate_paths({"clean": "data"})
        assert paths == []


class TestEnsureUtf8Encodable:
    """Tests for ensure_utf8_encodable() — final guard before API send."""

    def test_clean_payload(self):
        assert ensure_utf8_encodable({"text": "hello"}) is True

    def test_surrogate_payload(self):
        assert ensure_utf8_encodable({"text": f"bad{_SURROGATE_HIGH}"}) is False

    def test_sanitized_payload(self):
        payload = {"text": f"bad{_SURROGATE_HIGH}"}
        clean = sanitize_payload(payload)
        assert ensure_utf8_encodable(clean) is True

    def test_complex_clean_payload(self):
        payload = {
            "messages": [
                {"role": "user", "content": "你好世界！"},
                {"role": "assistant", "content": "Hello!"},
            ],
            "model": "test-model",
            "temperature": 0.7,
        }
        assert ensure_utf8_encodable(payload) is True


class TestInvalidUnicodePayloadError:
    """Tests for InvalidUnicodePayloadError — the "stop failover" signal."""

    def test_is_value_error(self):
        """Should be a ValueError subclass for compatibility with existing except clauses."""
        err = InvalidUnicodePayloadError("test")
        assert isinstance(err, ValueError)

    def test_message_preserved(self):
        err = InvalidUnicodePayloadError("custom message")
        assert "custom message" in str(err)

    def test_not_caught_as_generic_exception_only(self):
        """Ensure it can be caught specifically (not just by generic Exception)."""
        try:
            raise InvalidUnicodePayloadError("test")
        except InvalidUnicodePayloadError:
            pass  # Should be caught here
        except Exception:
            pytest.fail("InvalidUnicodePayloadError was caught by generic Exception")
