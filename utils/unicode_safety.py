"""Unicode safety layer — sanitize lone surrogate characters before they hit APIs, logs, or TUI.

CRUX processes text from many sources: conversation history, tool outputs, provider
responses, TUI paste buffers, streaming chunks, and run summaries.  Any of these can
contain lone surrogate code points (U+D800–U+DFFF) that are NOT valid UTF-8 and will
crash json.dumps(ensure_ascii=False), httpx requests, and Windows console rendering.

This module provides a single canonical sanitization path.  Call it at every boundary
where text enters or leaves the system:

    Boundary               Function to call
    ─────────              ─────────────────
    Provider API request   sanitize_payload(messages)
    Stream chunk received  sanitize_text(chunk)
    TUI render             sanitize_text(content)
    Log / persistence      sanitize_payload(record)
    JSON encode            sanitize_payload(obj) then json.dumps(ensure_ascii=False)
"""

from __future__ import annotations

from typing import Any

_SURROGATE_MIN: int = 0xD800
_SURROGATE_MAX: int = 0xDFFF
_REPLACEMENT: str = "�"  # Unicode replacement character


def sanitize_text(value: Any, replacement: str = _REPLACEMENT) -> Any:
    """Replace lone surrogate characters that cannot be encoded as UTF-8.

    Args:
        value: The input to sanitize.  Non-strings pass through unchanged.
        replacement: Character to substitute for each surrogate (default U+FFFD).

    Returns:
        A string with all lone surrogates replaced.  Non-string inputs are
        returned as-is.

    >>> sanitize_text("hello \\ud800 world")
    'hello � world'
    >>> sanitize_text("clean text")
    'clean text'
    """
    if not isinstance(value, str):
        return value

    # Fast path: most strings are clean
    if not any(_SURROGATE_MIN <= ord(ch) <= _SURROGATE_MAX for ch in value):
        return value

    return "".join(
        replacement if _SURROGATE_MIN <= ord(ch) <= _SURROGATE_MAX else ch
        for ch in value
    )


def sanitize_payload(value: Any, replacement: str = _REPLACEMENT) -> Any:
    """Recursively sanitize all strings in a nested structure.

    Handles dict, list, tuple, and bare str.  Numbers, bools, None pass through
    unchanged.  This is safe to call on any JSON-like payload before serialization.

    >>> sanitize_payload({"msg": [{"role": "user", "content": "bad \\udfff"}]})
    {'msg': [{'role': 'user', 'content': 'bad �'}]}
    """
    if isinstance(value, str):
        return sanitize_text(value, replacement=replacement)

    if isinstance(value, dict):
        return {
            sanitize_payload(k, replacement): sanitize_payload(v, replacement)
            for k, v in value.items()
        }

    if isinstance(value, list):
        return [sanitize_payload(v, replacement) for v in value]

    if isinstance(value, tuple):
        return tuple(sanitize_payload(v, replacement) for v in value)

    return value


def has_surrogate(value: Any) -> bool:
    """Check whether any string in a nested structure contains lone surrogates.

    Returns True as soon as one is found (short-circuit).  Use this for fast
    pre-flight checks before expensive sanitization.

    >>> has_surrogate("clean")
    False
    >>> has_surrogate({"x": "bad \\ud800"})
    True
    """
    if isinstance(value, str):
        return any(_SURROGATE_MIN <= ord(ch) <= _SURROGATE_MAX for ch in value)

    if isinstance(value, dict):
        return any(has_surrogate(k) or has_surrogate(v) for k, v in value.items())

    if isinstance(value, (list, tuple)):
        return any(has_surrogate(v) for v in value)

    return False


def find_surrogate_paths(value: Any, path: str = "root") -> list[str]:
    """Walk a nested structure and return the paths of all surrogate characters.

    Useful for debugging — run this once to identify which field is dirty:

        paths = find_surrogate_paths(payload)
        if paths:
            logger.warning("surrogate paths: %s", paths[:20])

    Returns a list of strings like ``"root.messages[12].content[0] U+DC00"``.
    """
    found: list[str] = []

    if isinstance(value, str):
        for i, ch in enumerate(value):
            if _SURROGATE_MIN <= ord(ch) <= _SURROGATE_MAX:
                found.append(f"{path}[{i}] U+{ord(ch):04X}")
        return found

    if isinstance(value, dict):
        for k, v in value.items():
            k_str = str(k)
            found.extend(find_surrogate_paths(k_str, f"{path}.<key>"))
            found.extend(find_surrogate_paths(v, f"{path}.{k_str}"))
        return found

    if isinstance(value, list):
        for i, v in enumerate(value):
            found.extend(find_surrogate_paths(v, f"{path}[{i}]"))
        return found

    return found


def ensure_utf8_encodable(value: str | dict | list) -> bool:
    """Validate that a value can be safely encoded to UTF-8 via json.dumps.

    Returns True if ``json.dumps(value, ensure_ascii=False).encode('utf-8')``
    succeeds without UnicodeEncodeError.  Use as a final guard before sending.

    >>> ensure_utf8_encodable({"text": "hello"})
    True
    """
    import json

    try:
        json.dumps(value, ensure_ascii=False).encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


class InvalidUnicodePayloadError(ValueError):
    """Raised when a payload contains unencodable characters that survived sanitization.

    This is a LOCAL payload problem, NOT a provider failure.  Fallback / failover
    logic MUST NOT retry on this exception — retrying with a different provider
    will hit the same encoding error and waste all providers.
    """

    pass
