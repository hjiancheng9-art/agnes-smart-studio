"""Structured exception hierarchy for CRUX Studio.

All domain-specific exceptions inherit from CruxError, so callers can
catch the base class or narrow down to specific categories.

Usage::

    from core.exceptions import CruxError, ProviderError, ToolError

    try:
        ...
    except ProviderError:
        # provider is down / bad key / model not found
        ...
    except CruxError:
        # any other CRUX-domain error
        raise
"""


# ── Base ────────────────────────────────────────────────────────────────


class CruxError(Exception):
    """Base exception for all CRUX-domain errors.

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


class ConfigError(CruxError):
    """Misconfiguration: missing key, invalid models.json, bad settings."""


class ProviderError(CruxError):
    """Provider-level failure: auth rejected, model unavailable, rate-limited."""


class NetworkError(CruxError):
    """Network connectivity issue: DNS failure, timeout, connection reset."""


class EncodingError(CruxError):
    """Character encoding problem: UTF-8 BOM, GBK mojibake, code page mismatch."""


# ── Tools & Engines ───────────────────────────────────────────────────────


class ToolError(CruxError):
    """A tool function failed to execute."""


class ToolTimeoutError(ToolError):
    """A tool function exceeded its execution time limit."""


class EngineError(CruxError):
    """Generation engine (image/video/code) failure."""


class GenerationError(EngineError):
    """Image or video generation pipeline failed."""


# ── Agent & Chat ─────────────────────────────────────────────────────────


class AgentError(CruxError):
    """Agent planning, spawning, or orchestration failure."""


class SessionError(CruxError):
    """Session save/restore/load failure."""


class MessageError(CruxError):
    """Message parsing, tool-call reassembly, or format error."""


# ── Self-* subsystems ─────────────────────────────────────────────────────


class AuditError(CruxError):
    """Self-audit scan or analysis failure."""


class EvolutionError(CruxError):
    """Self-evolve analysis or patch generation failure."""


class FixError(CruxError):
    """Auto-fix patch application failure."""


# ── Skill & Marketplace ──────────────────────────────────────────────────


class SkillError(CruxError):
    """Skill loading, parsing, or execution failure."""


class MarketplaceError(CruxError):
    """Marketplace search, install, or update failure."""


# ── Sandbox & Security ───────────────────────────────────────────────────


class SandboxError(CruxError):
    """Sandbox creation, isolation, or resource limit failure."""


class SecurityError(CruxError):
    """Security violation: command injection, path traversal, unauthorized access."""


__all__ = [
    # Agent & Chat
    "AgentError",
    # Self-* subsystems
    "AuditError",
    # Infrastructure
    "ConfigError",
    # Base
    "CruxError",
    "EncodingError",
    "EngineError",
    "EvolutionError",
    "FixError",
    "GenerationError",
    "MarketplaceError",
    "MessageError",
    "NetworkError",
    "ProviderError",
    # Sandbox & Security
    "SandboxError",
    "SecurityError",
    "SessionError",
    # Skill & Marketplace
    "SkillError",
    # Tools & Engines
    "ToolError",
    "ToolTimeoutError",
]
