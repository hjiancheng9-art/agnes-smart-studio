"""Tests for core/secret_redactor.py — strip API keys and sensitive values."""

from __future__ import annotations

import os
from unittest.mock import patch

from core.secret_redactor import (
    _get_secret_values,
    redact,
    reset_secret_redactor,
    safe_env_for_subprocess,
)


class TestGetSecretValues:
    """_get_secret_values() — cached env var resolution."""

    def test_empty_when_no_secrets_set(self):
        reset_secret_redactor()
        with patch.dict(os.environ, {}, clear=True):
            values = _get_secret_values()
            assert values == {}

    def test_caches_values(self):
        reset_secret_redactor()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key-123"}, clear=True):
            v1 = _get_secret_values()
            v2 = _get_secret_values()
            assert v1 is v2  # same dict, cached
            assert v1["OPENAI_API_KEY"] == "sk-test-key-123"

    def test_cache_reset(self):
        reset_secret_redactor()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "dk-test-456"}, clear=True):
            v1 = _get_secret_values()
            assert v1["DEEPSEEK_API_KEY"] == "dk-test-456"
        reset_secret_redactor()
        with patch.dict(os.environ, {}, clear=True):
            v2 = _get_secret_values()
            assert v2 == {}


class TestRedact:
    """redact() — replace API keys with [REDACTED]."""

    def test_empty_text(self):
        assert redact("") == ""
        assert redact("") == ""  # verify idempotent

    def test_no_secrets_present(self):
        reset_secret_redactor()
        with patch.dict(os.environ, {}, clear=True):
            assert redact("hello world") == "hello world"

    def test_redacts_known_key(self):
        reset_secret_redactor()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-abc123"}, clear=True):
            result = redact("Authorization: Bearer sk-abc123")
            assert "sk-abc123" not in result
            assert "[REDACTED:OPENAI_API_KEY]" in result

    def test_redacts_multiple_keys(self):
        reset_secret_redactor()
        env = {
            "OPENAI_API_KEY": "sk-key1",
            "ANTHROPIC_API_KEY": "sk-key2",
        }
        with patch.dict(os.environ, env, clear=True):
            text = f"Use key1={env['OPENAI_API_KEY']} and key2={env['ANTHROPIC_API_KEY']}"
            result = redact(text)
            assert "sk-key1" not in result
            assert "sk-key2" not in result
            assert "[REDACTED:OPENAI_API_KEY]" in result
            assert "[REDACTED:ANTHROPIC_API_KEY]" in result

    def test_redacts_long_base64_tokens(self):
        reset_secret_redactor()
        with patch.dict(os.environ, {}, clear=True):
            long_token = "A" * 40  # matches _KEY_PATTERN
            result = redact(f"token={long_token}")
            assert "[REDACTED:token]" in result
            assert long_token not in result

    def test_preserves_non_secret_text(self):
        reset_secret_redactor()
        text = "This is normal text with some.data.and.stuff"
        with patch.dict(os.environ, {}, clear=True):
            result = redact(text)
            assert result == text


class TestSafeEnvForSubprocess:
    """safe_env_for_subprocess() — minimal env for child processes."""

    def test_excludes_secret_vars(self):
        reset_secret_redactor()
        env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "OPENAI_API_KEY": "sk-secret",
            "DEEPSEEK_API_KEY": "dk-secret",
            "SYSTEMROOT": "C:\\Windows",
            "TEMP": "/tmp",
        }
        with patch.dict(os.environ, env, clear=True):
            safe = safe_env_for_subprocess()
            assert "PATH" in safe
            assert "HOME" in safe
            assert "OPENAI_API_KEY" not in safe
            assert "DEEPSEEK_API_KEY" not in safe

    def test_includes_extra_keys(self):
        reset_secret_redactor()
        with patch.dict(os.environ, {"PATH": "/bin"}, clear=True):
            safe = safe_env_for_subprocess(extra={"MY_VAR": "my_value"})
            assert safe["MY_VAR"] == "my_value"
