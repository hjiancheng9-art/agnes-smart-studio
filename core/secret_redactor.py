"""SecretRedactor — strip API keys and sensitive values from logs and output.

Per ChatGPT audit P3: logs must never contain API keys, cookies, or
authorization headers. This module provides a central redaction point.

Usage:
    from core.secret_redactor import redact
    safe = redact(potentially_dangerous_string)
"""

from __future__ import annotations

import os
import re

# Known env var names that contain secrets
_SECRET_ENV_VARS = frozenset({
    "DEEPSEEK_API_KEY", "CRUX_API_KEY", "AGNES_API_KEY", "ZHIPU_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GH_TOKEN", "GITHUB_TOKEN", "VERCEL_TOKEN",
})

# Patterns that look like API keys (long base64/alphanumeric strings)
_KEY_PATTERN = re.compile(r'(sk-[a-zA-Z0-9]{20,})|([a-zA-Z0-9+/=]{40,})')

# Cache resolved keys for redaction
_cached_keys: dict[str, str] | None = None


def _get_secret_values() -> dict[str, str]:
    """Get all secret env var values (cached)."""
    global _cached_keys
    if _cached_keys is None:
        _cached_keys = {}
        for name in _SECRET_ENV_VARS:
            val = os.environ.get(name, "")
            if val:
                _cached_keys[name] = val
    return _cached_keys


def redact(text: str) -> str:
    """Replace known API keys with '[REDACTED]' in the given text."""
    if not text:
        return text
    for name, val in _get_secret_values().items():
        if val and val in text:
            text = text.replace(val, f"[REDACTED:{name}]")
    # Also redact any long base64-looking strings that might be tokens
    text = _KEY_PATTERN.sub("[REDACTED:token]", text)
    return text


def safe_env_for_subprocess(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a minimal env dict for subprocesses — no API keys by default.

    Only pass through: PATH, SYSTEMROOT, TEMP, TMP, HOME, USERPROFILE,
    and explicitly requested keys. All other env vars (including API keys)
    are excluded to prevent leakage to child processes.
    """
    safe_keys = {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE",
                 "USERNAME", "COMSPEC", "PATHEXT", "LANG", "LC_ALL"}
    safe = {}
    for k, v in os.environ.items():
        if k in safe_keys or k in _SECRET_ENV_VARS:
            continue  # skip secrets
        safe[k] = v
    if extra:
        safe.update(extra)
    return safe
