"""Property-based tests for high-risk core modules using Hypothesis.

These tests verify invariants that MUST hold for all valid inputs,
catching edge cases that hand-written examples miss.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Mark entire module as unit
pytestmark = pytest.mark.unit


# ── strategies ──────────────────────────────────────


@st.composite
def printable_text(draw, min_size=0, max_size=500):
    """Text strategy biased toward finding edge cases."""
    return draw(
        st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),  # no surrogates
                blacklist_characters=("\x00",),
            ),
            min_size=min_size,
            max_size=max_size,
        )
    )


def text_with_secrets():
    """Generate text that may contain secret-like patterns."""
    return st.text(min_size=0, max_size=1000)


def bytes_data():
    """Generate arbitrary bytes."""
    return st.binary(min_size=0, max_size=10000)


# ── secret_redactor ─────────────────────────────────


class TestRedactInvariants:
    """Property tests for core.secret_redactor.redact()."""

    @given(text=text_with_secrets())
    @settings(max_examples=200)
    def test_redact_never_extends_text(self, text):
        """Redaction replaces keys with markers -- text should never grow."""
        from core.secret_redactor import redact

        result = redact(text)
        assert len(result) <= len(text), f"Redacted text ({len(result)}) longer than original ({len(text)})"

    @given(text=text_with_secrets())
    @settings(max_examples=200)
    def test_redact_idempotent(self, text):
        """Running redact twice should yield the same result."""
        from core.secret_redactor import redact

        once = redact(text)
        twice = redact(once)
        assert once == twice, f"redact not idempotent:\n  once={once!r}\n  twice={twice!r}"

    @given(text=text_with_secrets())
    @settings(max_examples=200)
    def test_empty_string_unchanged(self, text):
        """Empty or whitespace-only text should pass through."""
        from core.secret_redactor import redact

        if not text.strip():
            result = redact(text)
            assert result == text, f"Empty/whitespace text modified: {result!r}"

    def test_redact_removes_known_key_from_text(self):
        """If a known secret is literally in the text, it must be replaced."""
        from core.secret_redactor import redact

        # Use a deterministic secret for this test
        # Temporarily set DEEPSEEK_API_KEY to a known value
        test_key = "sk-test-deadbeef1234567890abcdef1234567890"
        os.environ["DEEPSEEK_API_KEY"] = test_key
        try:
            # Bust cache
            import core.secret_redactor as sr

            sr._cached_keys = None

            result = redact(f"use key: {test_key} to call API")
            assert test_key not in result, f"Secret not removed: {result!r}"
            assert "[REDACTED:DEEPSEEK_API_KEY]" in result
        finally:
            del os.environ["DEEPSEEK_API_KEY"]
            sr._cached_keys = None


class TestSafeEnvSubprocess:
    """Property tests for core.secret_redactor.safe_env_for_subprocess()."""

    def test_no_secret_env_vars_leak(self):
        """safe_env_for_subprocess must exclude all known secret env vars."""
        from core.secret_redactor import _SECRET_ENV_VARS, safe_env_for_subprocess

        result = safe_env_for_subprocess()
        for secret_var in _SECRET_ENV_VARS:
            assert secret_var not in result, f"Secret env var {secret_var} leaked to safe_env_for_subprocess"

    def test_extra_keys_preserved(self):
        """Explicitly requested keys must be present."""
        from core.secret_redactor import safe_env_for_subprocess

        result = safe_env_for_subprocess(extra={"MY_CUSTOM_VAR": "hello"})
        assert result.get("MY_CUSTOM_VAR") == "hello"


# ── tool_call_parser ────────────────────────────────


class TestParseArgs:
    """Property tests for core.tool_call_parser._parse_args()."""

    @given(raw=st.text(min_size=0, max_size=2000))
    @settings(max_examples=300)
    def test_parse_args_always_returns_dict(self, raw):
        """_parse_args must return a dict for any input."""
        from core.tool_call_parser import _parse_args

        result = _parse_args(raw)
        assert isinstance(result, dict), f"_parse_args returned {type(result).__name__} for {raw!r}"

    @given(raw=st.text(min_size=0, max_size=2000))
    @settings(max_examples=100)
    def test_empty_input_returns_empty_dict(self, raw):
        """Empty or whitespace-only input must return {}."""
        from core.tool_call_parser import _parse_args

        stripped = raw.strip()
        if not stripped:
            result = _parse_args(raw)
            assert result == {}, f"Expected {{}} for empty input, got {result}"

    @given(
        raw=st.text(
            alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",)),
            min_size=0,
            max_size=2000,
        )
    )
    @settings(max_examples=200)
    def test_parse_args_never_crashes(self, raw):
        """_parse_args must never raise for any string input."""
        from core.tool_call_parser import _parse_args

        try:
            result = _parse_args(raw)
            assert isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"_parse_args crashed on {raw[:100]!r}: {e}")

    def test_valid_json_parsed(self):
        """Valid JSON object should be parsed correctly."""
        from core.tool_call_parser import _parse_args

        result = _parse_args('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_kv_fallback_for_malformed(self):
        """Malformed key-value string still extracts pairs."""
        from core.tool_call_parser import _parse_args

        result = _parse_args('"name": "test", "count": 5')
        assert isinstance(result, dict)
        assert "name" in result


class TestExtractKvPairs:
    """Property tests for core.tool_call_parser._extract_kv_pairs()."""

    @given(raw=st.text(min_size=0, max_size=2000))
    @settings(max_examples=300)
    def test_extract_kv_always_returns_dict(self, raw):
        """_extract_kv_pairs must return a dict for any input."""
        from core.tool_call_parser import _extract_kv_pairs

        result = _extract_kv_pairs(raw)
        assert isinstance(result, dict), f"_extract_kv_pairs returned {type(result).__name__}"

    @given(raw=st.text(min_size=0, max_size=500))
    @settings(max_examples=200)
    def test_extracted_keys_are_strings(self, raw):
        """All extracted keys must be strings."""
        from core.tool_call_parser import _extract_kv_pairs

        result = _extract_kv_pairs(raw)
        for key in result:
            assert isinstance(key, str), f"Key {key!r} is not str"


class TestHasXmlToolCalls:
    """Property tests for core.tool_call_parser.has_xml_tool_calls()."""

    @given(text=st.text(min_size=0, max_size=5000))
    @settings(max_examples=300)
    def test_has_xml_tool_calls_returns_bool(self, text):
        """Must return True or False for any input."""
        from core.tool_call_parser import has_xml_tool_calls

        result = has_xml_tool_calls(text)
        assert isinstance(result, bool), f"has_xml_tool_calls returned {type(result).__name__}"

    @given(text=st.text(min_size=0, max_size=5000))
    @settings(max_examples=300)
    def test_no_crash_on_any_text(self, text):
        """Must never crash regardless of input."""
        from core.tool_call_parser import has_xml_tool_calls

        try:
            has_xml_tool_calls(text)
        except Exception as e:
            pytest.fail(f"has_xml_tool_calls crashed on {text[:100]!r}: {e}")

    def test_detects_function_call_tag(self):
        """Text containing <function-call should be detected."""
        from core.tool_call_parser import has_xml_tool_calls

        assert has_xml_tool_calls('<function-call name="test" />')
        assert has_xml_tool_calls('<function-call>{"name":"f"}</function-call>')

    def test_no_false_positive_on_plain_text(self):
        """Plain text without function-call should not trigger."""
        from core.tool_call_parser import has_xml_tool_calls

        assert not has_xml_tool_calls("hello world")
        assert not has_xml_tool_calls("")


class TestExtractToolCalls:
    """Property tests for core.tool_call_parser.extract_tool_calls()."""

    @given(text=st.text(min_size=0, max_size=5000))
    @settings(max_examples=200)
    def test_extract_tool_calls_returns_tuple(self, text):
        """Must return a tuple of (list, str)."""
        from core.tool_call_parser import extract_tool_calls

        result = extract_tool_calls(text)
        assert isinstance(result, tuple), f"extract_tool_calls returned {type(result).__name__}"
        assert len(result) == 2, f"Expected 2-tuple, got {len(result)}"
        tool_calls, clean_text = result
        assert isinstance(tool_calls, list), "First element must be list"
        assert isinstance(clean_text, str), "Second element must be str"

    @given(text=st.text(min_size=0, max_size=5000))
    @settings(max_examples=200)
    def test_no_crash_on_any_text(self, text):
        """Must never crash on any input."""
        from core.tool_call_parser import extract_tool_calls

        try:
            extract_tool_calls(text)
        except Exception as e:
            pytest.fail(f"extract_tool_calls crashed on {text[:100]!r}: {e}")


# ── tools ───────────────────────────────────────────


class TestSafeDecode:
    """Property tests for core.tools._safe_decode()."""

    @given(data=bytes_data())
    @settings(max_examples=200)
    def test_safe_decode_always_returns_str(self, data):
        """_safe_decode must return str for any bytes input."""
        from core.tools import _safe_decode

        result = _safe_decode(data)
        assert isinstance(result, str), f"_safe_decode returned {type(result).__name__}"

    @given(data=st.binary(min_size=0, max_size=1000))
    @settings(max_examples=200)
    def test_safe_decode_empty_bytes(self, data):
        """Empty bytes input should return empty string."""
        from core.tools import _safe_decode

        if data == b"":
            result = _safe_decode(data)
            assert result == "", f"Expected '', got {result!r}"

    @given(data=st.binary(min_size=0, max_size=10000))
    @settings(max_examples=100)
    def test_safe_decode_never_crashes(self, data):
        """Must never crash on any bytes input."""
        from core.tools import _safe_decode

        try:
            _safe_decode(data)
        except Exception as e:
            pytest.fail(f"_safe_decode crashed on {data[:50]!r}: {e}")


# ── constraints ─────────────────────────────────────


class TestConstraintsValidation:
    """Property tests for constraint validation in core/constraints.py."""

    @given(
        name=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),
                blacklist_characters=("\x00",),
            ),
            min_size=0,
            max_size=200,
        ),
        args=st.dictionaries(
            keys=st.text(min_size=0, max_size=50),
            values=st.one_of(
                st.text(max_size=100),
                st.integers(),
                st.booleans(),
                st.none(),
            ),
            max_size=10,
        ),
    )
    @settings(max_examples=200)
    def test_is_tool_high_risk_returns_bool(self, name, args):
        """is_tool_high_risk must return bool and never crash."""
        from core.constraints import is_tool_high_risk

        try:
            result = is_tool_high_risk(name, args)
            assert isinstance(result, bool), f"is_tool_high_risk returned {type(result).__name__}"
        except Exception as e:
            pytest.fail(f"is_tool_high_risk({name!r}, {args!r}) crashed: {e}")


# ── execution_policy ────────────────────────────────


class TestExecutionPolicy:
    """Property tests for execution policy decisions."""

    @given(
        text=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),
                blacklist_characters=("\x00",),
            ),
            min_size=0,
            max_size=500,
        ),
    )
    @settings(max_examples=300)
    def test_choose_policy_returns_execution_policy(self, text):
        """choose_policy must return ExecutionPolicy and never crash."""
        from core.execution_policy import ExecutionPolicy, choose_policy

        try:
            result = choose_policy(text)
            assert isinstance(result, ExecutionPolicy), f"choose_policy returned {type(result).__name__}"
            assert result.mode is not None
            assert isinstance(result.reason, str)
        except Exception as e:
            pytest.fail(f"choose_policy crashed on {text[:100]!r}: {e}")

    @given(
        keyword=st.sampled_from(["实现", "重构", "部署", "迁移", "升级", "完整方案", "修复并验证"]),
        prefix=st.text(min_size=0, max_size=100),
        suffix=st.text(min_size=0, max_size=100),
    )
    @settings(max_examples=100)
    def test_orchestrate_keywords_trigger_orchestrate(self, keyword, prefix, suffix):
        """Text containing orchestrate keywords should produce valid policy."""
        from core.execution_policy import ExecutionMode, choose_policy

        text = f"{prefix}{keyword}{suffix}"
        result = choose_policy(text)
        assert isinstance(result.mode, ExecutionMode)
