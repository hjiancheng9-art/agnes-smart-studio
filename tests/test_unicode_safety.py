"""Tests for utils/unicode_safety.py — surrogate character sanitization layer."""

import pytest

from utils.unicode_safety import (
    InvalidUnicodePayloadError,
    ensure_utf8_encodable,
    find_surrogate_paths,
    has_surrogate,
    sanitize_payload,
    sanitize_text,
)


class TestSanitizeText:
    """Tests for sanitize_text() — the core sanitization function."""

    def test_clean_string_passes_through(self):
        assert sanitize_text("hello world") == "hello world"
        assert sanitize_text("emoji works") == "emoji works"

    def test_lone_high_surrogate_replaced(self):
        result = sanitize_text("bad \ud800 text")
        assert "\ud800" not in result
        assert "\ufffd" in result

    def test_lone_low_surrogate_replaced(self):
        result = sanitize_text("bad \udfff text")
        assert "\udfff" not in result
        assert "\ufffd" in result

    def test_multiple_lone_surrogates_all_replaced(self):
        result = sanitize_text("\ud800\ud801\udfff")
        assert result == "\ufffd\ufffd\ufffd"

    def test_custom_replacement_character(self):
        result = sanitize_text("\ud800 bad", replacement="?")
        assert result == "? bad"

    def test_empty_string_unchanged(self):
        assert sanitize_text("") == ""

    def test_non_string_passes_through(self):
        assert sanitize_text(42) == 42
        assert sanitize_text(None) is None
        assert sanitize_text(True) is True

    def test_mixed_surrogate_and_normal(self):
        result = sanitize_text("a\ud800b\udfffc")
        assert result == "a\ufffdb\ufffdc"


class TestHasSurrogate:
    """Tests for has_surrogate() — fast pre-flight surrogate detection."""

    def test_clean_string_returns_false(self):
        assert has_surrogate("hello") is False
        assert has_surrogate("") is False

    def test_string_with_surrogate_returns_true(self):
        assert has_surrogate("\ud800") is True
        assert has_surrogate("a\udfff") is True

    def test_non_string_returns_false(self):
        assert has_surrogate(42) is False
        assert has_surrogate(None) is False

    def test_dict_with_surrogate_returns_true(self):
        assert has_surrogate({"key": "\ud800"}) is True

    def test_clean_dict_returns_false(self):
        assert has_surrogate({"key": "value"}) is False

    def test_list_with_surrogate_returns_true(self):
        assert has_surrogate(["clean", "\udfff"]) is True

    def test_clean_list_returns_false(self):
        assert has_surrogate(["a", "b"]) is False

    def test_nested_structure_short_circuits(self):
        assert has_surrogate({"outer": {"inner": ["a", {"deep": "\ud800"}]}}) is True


class TestSanitizePayload:
    """Tests for sanitize_payload() — recursive nested sanitization."""

    def test_bare_string_sanitized(self):
        assert sanitize_payload("\ud800") == "\ufffd"

    def test_dict_values_sanitized(self):
        result = sanitize_payload({"a": "\ud800", "b": "clean"})
        assert result["a"] == "\ufffd"
        assert result["b"] == "clean"

    def test_nested_dict_sanitized(self):
        result = sanitize_payload({"level1": {"level2": "\udfff"}})
        assert result["level1"]["level2"] == "\ufffd"

    def test_list_sanitized(self):
        result = sanitize_payload(["\ud800", "clean", "\udfff"])
        assert result == ["\ufffd", "clean", "\ufffd"]

    def test_tuple_sanitized(self):
        result = sanitize_payload(("\ud800", "clean"))
        assert isinstance(result, tuple)
        assert result == ("\ufffd", "clean")

    def test_numbers_pass_through(self):
        result = sanitize_payload({"count": 42, "price": 9.99})
        assert result["count"] == 42
        assert result["price"] == 9.99

    def test_booleans_and_none_pass_through(self):
        result = sanitize_payload({"flag": True, "nothing": None, "no": False})
        assert result["flag"] is True
        assert result["nothing"] is None
        assert result["no"] is False

    def test_complex_nested_structure(self):
        payload = {
            "messages": [
                {"role": "user", "content": "bad \ud800 char"},
                {"role": "assistant", "content": "clean"},
            ],
            "metadata": {"source": "\udfff-test"},
        }
        result = sanitize_payload(payload)
        assert result["messages"][0]["content"] == "bad \ufffd char"
        assert result["messages"][1]["content"] == "clean"
        assert result["metadata"]["source"] == "\ufffd-test"


class TestFindSurrogatePaths:
    """Tests for find_surrogate_paths()."""

    def test_clean_string_returns_empty(self):
        assert find_surrogate_paths("hello") == []

    def test_finds_surrogate_in_string(self):
        paths = find_surrogate_paths("\ud800")
        assert len(paths) == 1
        assert "U+D800" in paths[0]

    def test_finds_surrogate_in_dict_value(self):
        paths = find_surrogate_paths({"msg": "\udfff"})
        assert len(paths) >= 1
        assert any("msg" in p for p in paths)

    def test_finds_surrogate_in_list(self):
        paths = find_surrogate_paths(["clean", "\ud800"])
        assert len(paths) >= 1
        assert any("[1]" in p for p in paths)


class TestEnsureUtf8Encodable:
    """Tests for ensure_utf8_encodable()."""

    def test_clean_dict_is_encodable(self):
        assert ensure_utf8_encodable({"text": "hello"}) is True

    def test_clean_string_is_encodable(self):
        assert ensure_utf8_encodable("hello") is True

    def test_string_with_lone_surrogate_not_encodable(self):
        assert ensure_utf8_encodable("\ud800") is False

    def test_valid_emoji_is_encodable(self):
        assert ensure_utf8_encodable("\U0001f600") is True


class TestInvalidUnicodePayloadError:
    """Tests for InvalidUnicodePayloadError."""

    def test_is_value_error_subclass(self):
        assert issubclass(InvalidUnicodePayloadError, ValueError)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(InvalidUnicodePayloadError):
            raise InvalidUnicodePayloadError("test error")
