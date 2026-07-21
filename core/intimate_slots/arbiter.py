"""功过格 · 赏罚仲裁 — merit-demerit ledger with decay and degradation.

Tracks every tool call and provider event through the EventBus.
Scores decay exponentially (24h half-life). When total score drops below
the degrade threshold, emits ``arbiter:degraded`` so right_ring can react.
High-merit tools get priority suggestions; low-merit providers get
deprioritized in fallback chains.

Usage: from core.intimate_slots.arbiter import arbiter
arbiter.record_tool_success("read_file", 0.3, "openai")
arbiter.report()
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
STATE_FILE = ROOT / "output" / "merit_state.json"

logger = logging.getLogger(__name__)

# ── Scoring constants ──────────────────────────────────────────
MERIT_FAST_TOOL = 1.0  # tool success + latency < 500ms
MERIT_NORMAL_TOOL = 0.5  # tool success, latency >= 500ms
MERIT_SESSION_CLEAN = 2.0  # session with zero errors
MERIT_PROVIDER_OK = 0.3  # provider health check passes
MERIT_CIRCUIT_RESTORED = 1.0  # circuit closed after trip

DEMERIT_TOOL_FAIL = -1.0  # any tool failure
DEMERIT_TIMEOUT = -2.0  # timeout (classified as TIMEOUT)
DEMERIT_PROVIDER = -1.5  # provider returns error
DEMERIT_CIRCUIT = -5.0  # circuit breaker trips
DEMERIT_HIGH_RISK = -3.0  # high-risk tool called without confirmation
DEMERIT_REPEATED = -4.0  # same-tool + same-error-type 3+ consecutive times

DEGRADE_THRESHOLD = -10.0
DECAY_HALF_LIFE = 86400.0  # 24 hours in seconds
DECAY_MIN_INTERVAL = 3600.0  # minimum 1 hour between decay runs
SAVE_MIN_INTERVAL = 5.0  # minimum 5 seconds between saves


@dataclass
class MeritEntry:
    """Single merit/demerit record for one tracked entity (tool or provider)."""

    score: float = 0.0
    total_successes: int = 0
    total_failures: int = 0
    last_error_type: str = ""
    same_error_streak: int = 0  # consecutive same-error-same-tool count
    high_risk_calls_wo_confirm: int = 0
    last_updated: float = 0.0


@dataclass
class MeritState:
    tools: dict[str, MeritEntry] = field(default_factory=dict)
    providers: dict[str, MeritEntry] = field(default_factory=dict)
    # Global session counters
    session_errors: int = 0
    session_calls: int = 0
    circuit_trips: int = 0
    sessions_completed: int = 0
    sessions_without_error: int = 0
    # Metadata
    last_decay_ts: float = 0.0
    last_save_ts: float = 0.0
    degraded: bool = False


class MeritDemeritArbiter:
    """功过格 — the merit-demerit ledger. Thread-safe, decay-capable, event-driven."""

    def __init__(self) -> None:
        self._state = MeritState()
        self._lock = threading.Lock()
        self._load()

    # ── Core atomic mutations ──────────────────────────────────

    def award_merit(self, target: str, amount: float, reason: str = "") -> None:
        with self._lock:
            self._decay_unlocked()
            entry = self._ensure_tool(target)
            entry.score += amount
            entry.total_successes += 1
            entry.last_updated = time.time()
            entry.same_error_streak = 0
            logger.debug("[功过格] +%.1f → %s (%.1f) %s", amount, target, entry.score, reason)
            self._check_degraded_unlocked()
            self._maybe_save_unlocked()

    def assign_demerit(self, target: str, amount: float, reason: str = "") -> None:
        with self._lock:
            self._decay_unlocked()
            entry = self._ensure_tool(target)
            entry.score += amount
            entry.total_failures += 1
            entry.last_updated = time.time()
            logger.debug("[功过格] %.1f → %s (%.1f) %s", amount, target, entry.score, reason)
            self._check_degraded_unlocked()
            self._maybe_save_unlocked()

    def get_score(self, target: str) -> float:
        with self._lock:
            return self._state.tools.get(target, MeritEntry()).score

    # ── Tool lifecycle ─────────────────────────────────────────

    def record_tool_success(self, tool_name: str, latency: float, provider: str = "") -> None:
        amount = MERIT_FAST_TOOL if latency < 0.5 else MERIT_NORMAL_TOOL
        self.award_merit(tool_name, amount, f"success {latency * 1000:.0f}ms")
        if provider:
            self._record_provider_result(provider, success=True)

    def record_tool_failure(self, tool_name: str, error_type: str, provider: str = "") -> None:
        with self._lock:
            self._decay_unlocked()
            entry = self._ensure_tool(tool_name)

            # Repeated-error detection
            if entry.last_error_type == error_type:
                entry.same_error_streak += 1
            else:
                entry.same_error_streak = 1
                entry.last_error_type = error_type

            penalty = DEMERIT_TIMEOUT if error_type.lower() in ("timeout",) else DEMERIT_TOOL_FAIL
            entry.score += penalty
            entry.total_failures += 1
            entry.last_updated = time.time()

            if entry.same_error_streak >= 3:
                entry.score += DEMERIT_REPEATED
                logger.warning(
                    "[功过格] repeated-error penalty: %s ×%d (%s)", tool_name, entry.same_error_streak, error_type
                )

            logger.debug("[功过格] %.1f → %s (%.1f) fail:%s", penalty, tool_name, entry.score, error_type)
            self._check_degraded_unlocked()
            self._maybe_save_unlocked()

        if provider:
            self._record_provider_result(provider, success=False)

    def record_tool_timeout(self, tool_name: str, provider: str = "") -> None:
        self.assign_demerit(tool_name, DEMERIT_TIMEOUT, "timeout")
        if provider:
            self._record_provider_result(provider, success=False)

    # ── Provider lifecycle ─────────────────────────────────────

    def _record_provider_result(self, provider: str, success: bool) -> None:
        with self._lock:
            entry = self._ensure_provider(provider)
            if success:
                entry.total_successes += 1
                entry.score += MERIT_PROVIDER_OK
                entry.same_error_streak = 0
            else:
                entry.total_failures += 1
                entry.score += DEMERIT_PROVIDER
            entry.last_updated = time.time()
            self._maybe_save_unlocked()

    def record_provider_healthy(self, provider: str) -> None:
        with self._lock:
            entry = self._ensure_provider(provider)
            entry.score += MERIT_PROVIDER_OK
            entry.last_updated = time.time()
            self._maybe_save_unlocked()

    def record_provider_error(self, provider: str) -> None:
        with self._lock:
            entry = self._ensure_provider(provider)
            entry.score += DEMERIT_PROVIDER
            entry.total_failures += 1
            entry.last_updated = time.time()
            self._maybe_save_unlocked()

    # ── Circuit breaker ────────────────────────────────────────

    def record_circuit_trip(self, provider: str = "default") -> None:
        with self._lock:
            entry = self._ensure_provider(provider)
            entry.score += DEMERIT_CIRCUIT
            entry.last_updated = time.time()
            self._state.circuit_trips += 1
            logger.warning("[功过格] circuit trip penalty: %s (%.1f)", provider, entry.score)
            self._check_degraded_unlocked()
            self._maybe_save_unlocked()

    def record_circuit_restored(self, provider: str = "default") -> None:
        with self._lock:
            entry = self._ensure_provider(provider)
            entry.score += MERIT_CIRCUIT_RESTORED
            entry.last_updated = time.time()
            self._check_degraded_unlocked()
            self._maybe_save_unlocked()

    # ── High-risk ──────────────────────────────────────────────

    def record_high_risk_call(self, tool_name: str, confirmed: bool) -> None:
        if not confirmed:
            self.assign_demerit(tool_name, DEMERIT_HIGH_RISK, "high-risk unconfirmed")
            with self._lock:
                entry = self._ensure_tool(tool_name)
                entry.high_risk_calls_wo_confirm += 1
                self._maybe_save_unlocked()

    # ── Session lifecycle ──────────────────────────────────────

    def record_session_start(self) -> None:
        with self._lock:
            self._state.session_errors = 0
            self._state.session_calls = 0

    def record_session_end(self, error_count: int, call_count: int) -> None:
        with self._lock:
            self._state.sessions_completed += 1
            if error_count == 0 and call_count > 0:
                self._state.sessions_without_error += 1
                # Award clean-session merit to global score (stored as a tool entry)
                clean = self._ensure_tool("_session")
                clean.score += MERIT_SESSION_CLEAN
                clean.last_updated = time.time()
            self._check_degraded_unlocked()
            self._maybe_save_unlocked()

    # ── Decay ──────────────────────────────────────────────────

    def _decay_unlocked(self) -> None:
        """Exponential decay: N(t) = N0 * 0.5^(t/half_life). Caller must hold lock."""
        now = time.time()
        if self._state.last_decay_ts == 0:
            self._state.last_decay_ts = now
            return
        elapsed = now - self._state.last_decay_ts
        if elapsed < DECAY_MIN_INTERVAL:
            return
        factor = 0.5 ** (elapsed / DECAY_HALF_LIFE)
        for entry in self._state.tools.values():
            entry.score *= factor
        for entry in self._state.providers.values():
            entry.score *= factor
        self._state.last_decay_ts = now
        logger.debug("[功过格] decay applied: factor=%.4f elapsed=%.0fs", factor, elapsed)

    # ── Degradation state ──────────────────────────────────────

    def _check_degraded_unlocked(self) -> None:
        """Check if total score crossed the degrade threshold. Caller must hold lock."""
        total = sum(e.score for e in self._state.tools.values()) + sum(e.score for e in self._state.providers.values())
        was_degraded = self._state.degraded
        if not was_degraded and total <= DEGRADE_THRESHOLD:
            self._state.degraded = True
            logger.warning("[功过格] DEGRADED — total score %.1f ≤ %.0f", total, DEGRADE_THRESHOLD)
            try:
                from core.event_bus import bus

                bus.emit("arbiter:degraded", total_score=total)
            except (ImportError, OSError, RuntimeError):
                pass
        elif was_degraded and total > DEGRADE_THRESHOLD + 5.0:
            self._state.degraded = False
            logger.info("[功过格] RECOVERED — total score %.1f", total)
            try:
                from core.event_bus import bus

                bus.emit("arbiter:recovered", total_score=total)
            except (ImportError, OSError, RuntimeError):
                pass

    def is_degraded(self) -> bool:
        with self._lock:
            return self._state.degraded

    # ── Suggestion / ordering queries ──────────────────────────

    def suggest_tool_priority(self, candidates: list[str]) -> list[str]:
        """Sort candidates by descending merit score (high score = preferred)."""
        with self._lock:
            scored = [(c, self._state.tools.get(c, MeritEntry()).score) for c in candidates]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [c for c, _ in scored]

    def deprioritize_providers(self, providers: list[str]) -> list[str]:
        """Sort providers by descending score; those below -5.0 move to end."""
        with self._lock:
            scored = [(p, self._state.providers.get(p, MeritEntry()).score) for p in providers]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [p for p, _ in scored]

    # ── Persistence ────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if not STATE_FILE.exists():
                return
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self._state = MeritState(
                tools={k: MeritEntry(**v) for k, v in raw.get("tools", {}).items()},
                providers={k: MeritEntry(**v) for k, v in raw.get("providers", {}).items()},
                session_errors=raw.get("session_errors", 0),
                session_calls=raw.get("session_calls", 0),
                circuit_trips=raw.get("circuit_trips", 0),
                sessions_completed=raw.get("sessions_completed", 0),
                sessions_without_error=raw.get("sessions_without_error", 0),
                last_decay_ts=raw.get("last_decay_ts", 0.0),
                last_save_ts=raw.get("last_save_ts", 0.0),
                degraded=raw.get("degraded", False),
            )
            logger.debug(
                "[功过格] loaded state: %d tools, %d providers", len(self._state.tools), len(self._state.providers)
            )
        except (json.JSONDecodeError, TypeError, KeyError, OSError) as e:
            logger.debug("[功过格] load failed: %s — starting fresh", e)
            self._state = MeritState()

    def save(self) -> None:
        """Persist state unconditionally (bypasses throttle)."""
        with self._lock:
            self._write_unlocked()

    def _maybe_save_unlocked(self) -> None:
        """Throttled save — at most once per SAVE_MIN_INTERVAL. Caller must hold lock."""
        now = time.time()
        if now - self._state.last_save_ts < SAVE_MIN_INTERVAL:
            return
        self._write_unlocked()

    def _write_unlocked(self) -> None:
        """Write state to disk. Caller must hold lock."""
        self._state.last_save_ts = time.time()
        try:
            os.makedirs(STATE_FILE.parent, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps(
                    {
                        "tools": {k: self._entry_to_dict(v) for k, v in self._state.tools.items()},
                        "providers": {k: self._entry_to_dict(v) for k, v in self._state.providers.items()},
                        "session_errors": self._state.session_errors,
                        "session_calls": self._state.session_calls,
                        "circuit_trips": self._state.circuit_trips,
                        "sessions_completed": self._state.sessions_completed,
                        "sessions_without_error": self._state.sessions_without_error,
                        "last_decay_ts": self._state.last_decay_ts,
                        "last_save_ts": self._state.last_save_ts,
                        "degraded": self._state.degraded,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except (OSError, TypeError, ValueError) as e:
            logger.debug("[功过格] save failed: %s", e)

    @staticmethod
    def _entry_to_dict(entry: MeritEntry) -> dict:
        return {
            "score": entry.score,
            "total_successes": entry.total_successes,
            "total_failures": entry.total_failures,
            "last_error_type": entry.last_error_type,
            "same_error_streak": entry.same_error_streak,
            "high_risk_calls_wo_confirm": entry.high_risk_calls_wo_confirm,
            "last_updated": entry.last_updated,
        }

    # ── Internal helpers ───────────────────────────────────────

    def _ensure_tool(self, name: str) -> MeritEntry:
        if name not in self._state.tools:
            self._state.tools[name] = MeritEntry()
        return self._state.tools[name]

    def _ensure_provider(self, name: str) -> MeritEntry:
        if name not in self._state.providers:
            self._state.providers[name] = MeritEntry()
        return self._state.providers[name]

    # ── Reports ────────────────────────────────────────────────

    @property
    def status(self) -> dict:
        with self._lock:
            tools_scored = len(self._state.tools)
            worst_tool = ""
            worst_score = 0.0
            for t, e in self._state.tools.items():
                if e.score < worst_score:
                    worst_score = e.score
                    worst_tool = t
            worst_provider = ""
            worst_pscore = 0.0
            for p, e in self._state.providers.items():
                if e.score < worst_pscore:
                    worst_pscore = e.score
                    worst_provider = p
            total = sum(e.score for e in self._state.tools.values()) + sum(
                e.score for e in self._state.providers.values()
            )
            return {
                "degraded": self._state.degraded,
                "tools_scored": tools_scored,
                "providers_scored": len(self._state.providers),
                "total_score": round(total, 2),
                "worst_tool": worst_tool,
                "worst_provider": worst_provider,
                "circuit_trips": self._state.circuit_trips,
                "sessions_completed": self._state.sessions_completed,
                "clean_sessions": self._state.sessions_without_error,
            }

    def summary(self) -> str:
        s = self.status
        tag = "[red]DEGRADED[/]" if s["degraded"] else "[green]OK[/]"
        return (
            f"[功过格] tools:{s['tools_scored']} providers:{s['providers_scored']} "
            f"score:{s['total_score']:.1f} sessions:{s['sessions_completed']} "
            f"trips:{s['circuit_trips']} {tag}"
        )

    def report(self) -> dict:
        """Full dict with all state for external consumption."""
        with self._lock:
            return {
                "degraded": self._state.degraded,
                "tools": {k: self._entry_to_dict(v) for k, v in self._state.tools.items()},
                "providers": {k: self._entry_to_dict(v) for k, v in self._state.providers.items()},
                "circuit_trips": self._state.circuit_trips,
                "sessions_completed": self._state.sessions_completed,
                "sessions_without_error": self._state.sessions_without_error,
                "last_decay_ts": self._state.last_decay_ts,
            }


# Module-level singleton
arbiter = MeritDemeritArbiter()


def reset_arbiter() -> None:
    """Reset arbiter state for test isolation."""
    global arbiter
    arbiter = MeritDemeritArbiter()
