"""护符 · 熔断 — emergency circuit breaker. 连续 N 次 API 失败自熔断，
cool-down 后自动恢复。阻止级联失败烧穿资源。
Usage: from core.intimate_slots.talisman import circuit
circuit.check()
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    threshold: int = 5  #
    cooldown: float = 60.0  #
    probe_timeout: float = 10.0  #
    failures: dict[str, int] = field(default_factory=dict)  #
    tripped: dict[str, float] = field(default_factory=dict)  #
    total_trips: int = 0


class CircuitBreaker:
    def __init__(self):
        self._state = CircuitState()
        self._lock = threading.Lock()

    # ── check ─────────────────────────────────────────────
    def check(self, provider: str = "default") -> tuple[bool, str]:
        """Check if the circuit is open for a provider. (ok, reason)"""
        with self._lock:
            tripped_at = self._state.tripped.get(provider, 0)
            if tripped_at:
                elapsed = time.time() - tripped_at
                if elapsed < self._state.cooldown:
                    return False, f"TRIPPED ({self._state.cooldown - elapsed:.0f}s remaining)"
                # Half-open: allow one probe
                return True, "half-open"
            return True, "closed"

    # ── record ────────────────────────────────────────────
    def record_failure(self, provider: str = "default"):
        with self._lock:
            self._state.failures[provider] = self._state.failures.get(provider, 0) + 1
            count = self._state.failures[provider]
            if count >= self._state.threshold:
                self._state.tripped[provider] = time.time()
                self._state.total_trips += 1
                logger.error("[护符] CIRCUIT OPEN for %s (%d consecutive failures)", provider, count)
                try:
                    from core.event_bus import bus

                    bus.emit("talisman:tripped", provider=provider, failures=count)
                except (ImportError, OSError, RuntimeError):
                    logger.debug("[Talisman] alert emit failed")

    def record_success(self, provider: str = "default"):
        with self._lock:
            self._state.failures[provider] = 0
            if provider in self._state.tripped:
                del self._state.tripped[provider]
                logger.info("[护符] CIRCUIT CLOSED for %s", provider)

    # ── force ─────────────────────────────────────────────
    def reset(self, provider: str = "default"):
        with self._lock:
            self._state.failures[provider] = 0
            self._state.tripped.pop(provider, None)

    def trip_immediately(self, provider: str = "default"):
        with self._lock:
            self._state.failures[provider] = self._state.threshold
            self._state.tripped[provider] = time.time()
            self._state.total_trips += 1

    @property
    def status(self) -> dict:
        with self._lock:
            return {
                "tripped": dict(self._state.tripped),
                "failures": dict(self._state.failures),
                "total_trips": self._state.total_trips,
            }


circuit = CircuitBreaker()
