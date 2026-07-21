"""Session-scoped lifecycle tracking — deterministic state model for CRUX sessions.

GPT architectural recommendation: "each conversation owns its provider client,
MCP client, event loop tasks, and cleanup hooks. Avoid global singletons."

This module provides the state machine; integration with ChatSession is gradual.
"""

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class SessionPhase(enum.Enum):
    """Deterministic lifecycle phases — no ambiguous 'maybe ready' states."""

    CREATED = "created"  # Object exists, nothing started
    INITIALIZING = "initializing"  # Provider/MCP setup in progress
    READY = "ready"  # Accepting user input
    STREAMING = "streaming"  # Response streaming (no new input)
    PAUSED = "paused"  # User interrupted, awaiting action
    CLEANING_UP = "cleaning_up"  # Tearing down resources
    DESTROYED = "destroyed"  # Terminal state


# Allowed transitions
_PHASE_TRANSITIONS: dict[SessionPhase, set[SessionPhase]] = {
    SessionPhase.CREATED: {SessionPhase.INITIALIZING, SessionPhase.DESTROYED},
    SessionPhase.INITIALIZING: {SessionPhase.READY, SessionPhase.DESTROYED},
    SessionPhase.READY: {SessionPhase.STREAMING, SessionPhase.PAUSED, SessionPhase.CLEANING_UP, SessionPhase.DESTROYED},
    SessionPhase.STREAMING: {SessionPhase.READY, SessionPhase.PAUSED, SessionPhase.CLEANING_UP, SessionPhase.DESTROYED},
    SessionPhase.PAUSED: {SessionPhase.READY, SessionPhase.CLEANING_UP, SessionPhase.DESTROYED},
    SessionPhase.CLEANING_UP: {SessionPhase.DESTROYED},
    SessionPhase.DESTROYED: set(),  # Terminal
}


@dataclass
class SessionLifecycle:
    """Per-session state machine with health tracking.

    Usage:
        lifecycle = SessionLifecycle()
        lifecycle.transition(SessionPhase.INITIALIZING)
        try:
            # ... setup ...
            lifecycle.transition(SessionPhase.READY)
        except Exception:
            lifecycle.record_error("setup failed")
            lifecycle.transition(SessionPhase.DESTROYED)
            raise
    """

    phase: SessionPhase = SessionPhase.CREATED
    created_at: float = field(default_factory=time.time)
    last_transition_at: float = field(default_factory=time.time)
    error_count: int = 0
    last_error: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def transition(self, target: SessionPhase) -> None:
        """Move to target phase. Raises ValueError on invalid transition."""
        allowed = _PHASE_TRANSITIONS.get(self.phase, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid phase transition: {self.phase.value} → {target.value}. Allowed: {[p.value for p in allowed]}"
            )
        with self._lock:
            old = self.phase
            self.phase = target
            self.last_transition_at = time.time()
            logger.debug("Session: %s → %s (%.1fs since creation)", old.value, target.value, self.age_seconds())

    def record_error(self, message: str) -> None:
        """Record an error without crashing — for health monitoring."""
        with self._lock:
            self.error_count += 1
            self.last_error = message[:500]
        logger.warning("Session error #%d: %s", self.error_count, message[:200])

    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def is_active(self) -> bool:
        return self.phase not in (SessionPhase.CLEANING_UP, SessionPhase.DESTROYED)

    def can_accept_input(self) -> bool:
        return self.phase in (SessionPhase.READY, SessionPhase.PAUSED)

    def health_report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "phase": self.phase.value,
                "age_seconds": round(self.age_seconds(), 1),
                "error_count": self.error_count,
                "last_error": self.last_error[:100] if self.last_error else None,
            }
