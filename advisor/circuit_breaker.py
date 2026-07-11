"""Advisor circuit breaker — fail fast when GPT/CDP is down.

State machine: CLOSED → (N failures) → OPEN → (cooldown) → HALF_OPEN → (1 probe) → CLOSED/OPEN
"""

from __future__ import annotations

import time

# State constants
CLOSED = "CLOSED"
OPEN = "OPEN"
HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Circuit breaker with proper HALF_OPEN probe.

    CLOSED: normal operation, all requests allowed.
    OPEN: N consecutive failures reached, all requests rejected for cooldown.
    HALF_OPEN: cooldown expired, exactly ONE probe request allowed.
        - Probe succeeds → CLOSED (full recovery).
        - Probe fails → OPEN (re-arm cooldown).
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: int = 120,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failure_count = 0
        self._state = CLOSED
        self._opened_until: float = 0.0
        self._probe_in_flight = False

    # ── Query ─────────────────────────────────────

    def allow(self) -> bool:
        """Whether a request is allowed right now."""
        if self._state == CLOSED:
            return True
        if self._state == OPEN:
            if time.time() >= self._opened_until:
                # Cooldown expired → transition to HALF_OPEN, allow one probe
                self._state = HALF_OPEN
                self._probe_in_flight = True
                return True
            return False
        # HALF_OPEN: only allow if no probe is in flight
        if not self._probe_in_flight:
            self._probe_in_flight = True
            return True
        return False

    @property
    def is_open(self) -> bool:
        """Whether the breaker is rejecting requests."""
        return not self.allow()

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def state(self) -> str:
        return self._state

    # ── State changes ─────────────────────────────

    def record_success(self) -> None:
        """Record a success — resets to CLOSED."""
        self._failure_count = 0
        self._opened_until = 0.0
        self._state = CLOSED
        self._probe_in_flight = False

    def record_failure(self) -> None:
        """Record a failure — may trigger OPEN."""
        self._failure_count += 1
        if self._state == HALF_OPEN:
            # Probe failed → re-open
            self._state = OPEN
            self._opened_until = time.time() + self.cooldown_seconds
            self._probe_in_flight = False
        elif self._failure_count >= self.failure_threshold:
            self._state = OPEN
            self._opened_until = time.time() + self.cooldown_seconds

    # ── Diagnostics ───────────────────────────────

    def snapshot(self) -> dict:
        return {
            "state": self._state,
            "allow": self.allow(),
            "is_open": self._state == OPEN,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "opened_until": self._opened_until,
            "remaining_cooldown": max(0.0, self._opened_until - time.time()),
        }

    def reset(self) -> None:
        """Force reset (for testing or manual recovery)."""
        self._failure_count = 0
        self._opened_until = 0.0
        self._state = CLOSED
        self._probe_in_flight = False
