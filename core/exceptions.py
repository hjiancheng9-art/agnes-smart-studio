"""Structured exception hierarchy for Agnes Smart Studio.

All domain-specific exceptions inherit from AgnesError, so callers can
catch the base class or narrow down to specific categories.

Usage::

    from core.exceptions import AgnesError, ProviderError, ToolError

    try:
        ...
    except ProviderError:
        # provider is down / bad key / model not found
        ...
    except AgnesError:
        # any other agnes-domain error
        raise
"""


# ── Base ────────────────────────────────────────────────────────────────

class AgnesError(Exception):
    """Base exception for all Agnes-domain errors.

    Carries an optional *code* short-tag for programmatic matching::

        raise ToolError("ffmpeg not found", code="TOOL_MISSING")
    """

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


# ── Infrastructure ───────────────────────────────────────────────────────

class ConfigError(AgnesError):
    """Misconfiguration: missing key, invalid models.json, bad settings."""


class ProviderError(AgnesError):
    """Provider-level failure: auth rejected, model unavailable, rate-limited."""


class NetworkError(AgnesError):
    """Network connectivity issue: DNS failure, timeout, connection reset."""


class EncodingError(AgnesError):
    """Character encoding problem: UTF-8 BOM, GBK mojibake, code page mismatch."""


# ── Tools & Engines ───────────────────────────────────────────────────────

class ToolError(AgnesError):
    """A tool function failed to execute."""


class ToolTimeoutError(ToolError):
    """A tool function exceeded its execution time limit."""


class EngineError(AgnesError):
    """Generation engine (image/video/code) failure."""


class GenerationError(EngineError):
    """Image or video generation pipeline failed."""


# ── Agent & Chat ─────────────────────────────────────────────────────────

class AgentError(AgnesError):
    """Agent planning, spawning, or orchestration failure."""


class SessionError(AgnesError):
    """Session save/restore/load failure."""


class MessageError(AgnesError):
    """Message parsing, tool-call reassembly, or format error."""


# ── Self-* subsystems ─────────────────────────────────────────────────────

class AuditError(AgnesError):
    """Self-audit scan or analysis failure."""


class EvolutionError(AgnesError):
    """Self-evolve analysis or patch generation failure."""


class FixError(AgnesError):
    """Auto-fix patch application failure."""


# ── Skill & Marketplace ──────────────────────────────────────────────────

class SkillError(AgnesError):
    """Skill loading, parsing, or execution failure."""


class MarketplaceError(AgnesError):
    """Marketplace search, install, or update failure."""


# ── Sandbox & Security ───────────────────────────────────────────────────

class SandboxError(AgnesError):
    """Sandbox creation, isolation, or resource limit failure."""


class SecurityError(AgnesError):
    """Security violation: command injection, path traversal, unauthorized access."""


__all__ = [
    # Base
    "AgnesError",
    # Infrastructure
    "ConfigError", "ProviderError", "NetworkError", "EncodingError",
    # Tools & Engines
    "ToolError", "ToolTimeoutError", "EngineError", "GenerationError",
    # Agent & Chat
    "AgentError", "SessionError", "MessageError",
    # Self-* subsystems
    "AuditError", "EvolutionError", "FixError",
    # Skill & Marketplace
    "SkillError", "MarketplaceError",
    # Sandbox & Security
    "SandboxError", "SecurityError",
]
