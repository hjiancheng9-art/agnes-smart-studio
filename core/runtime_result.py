"""Unified runtime result types — replaces mixed str/dataclass/tuple returns.

P0 Runtime Kernel: single result protocol consumed by chat.py, provider.py, and all tool dispatch paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolResult:
    """Normalized tool execution result. All dispatch paths must produce this."""

    ok: bool
    content: str = ""
    error_code: str | None = None
    retryable: bool = False
    side_effects: tuple = ()

    @classmethod
    def success(cls, content: str, side_effects: tuple = ()) -> ToolResult:
        return cls(ok=True, content=content, side_effects=side_effects)

    @classmethod
    def failure(cls, code: str, message: str, *, retryable: bool = False) -> ToolResult:
        return cls(ok=False, content=message, error_code=code, retryable=retryable)

    @classmethod
    def from_raw(cls, raw: Any) -> ToolResult:
        """Normalize any tool return value into ToolResult. Safe for all existing tools."""
        if isinstance(raw, ToolResult):
            return raw
        if raw is None:
            return cls.failure("tool_returned_none", "Tool returned None")
        if isinstance(raw, tuple) and len(raw) == 2:
            content, sides = raw
            if content is None:
                return cls.failure("tool_content_none", "Tool returned None content")
            content_str = str(content)
            if content_str.startswith("[错误]") or content_str.startswith("[自愈失败]"):
                return cls.failure("tool_error", content_str)
            if content_str.startswith("[超时]"):
                return cls.failure("tool_timeout", content_str, retryable=True)
            return cls.success(content_str, tuple(sides or []))
        return cls.success(str(raw))


# ── Provider-level error classification ──


class StreamError(RuntimeError):
    """Provider stream failure with retry semantics."""

    retryable: bool = False


class StreamTimeout(StreamError):
    retryable = True


class StreamFirstTokenTimeout(StreamError):
    retryable = True


class ProviderPermanentError(StreamError):
    """Non-retryable: auth failure, model not found, billing, etc."""

    retryable = False
