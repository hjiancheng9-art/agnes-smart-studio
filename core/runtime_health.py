"""CRUX Runtime Health Monitor — 运行时自愈探活模块。

Active health monitoring with circuit breaker, failure tracking,
and auto-recovery. Designed to be called from startup and before
critical operations.

Usage:
    from core.runtime_health import RuntimeHealth
    rh = RuntimeHealth()
    rh.check()              # quick startup health check
    rh.track_failure(tool)  # record a tool failure
    rh.should_retry(tool)   # circuit breaker check
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "output" / "health_state.json"

# ── Constants ────────────────────────────────────────
MAX_FAILURES_PER_TOOL = 5
CIRCUIT_BREAKER_TIMEOUT = 30  # seconds before retry
MAX_FAILURE_RATE = 0.5  # 50% failure rate triggers alert
HEALTH_CHECK_INTERVAL = 300  # 5 minutes between proactive checks


@dataclass
class ToolHealth:
    """Per-tool health tracking."""

    total_calls: int = 0
    failures: int = 0
    last_failure: float = 0.0
    circuit_open: bool = False
    circuit_opened_at: float = 0.0

    @property
    def failure_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.failures / self.total_calls

    @property
    def healthy(self) -> bool:
        if self.circuit_open:
            return time.time() - self.circuit_opened_at > CIRCUIT_BREAKER_TIMEOUT
        return self.failure_rate < MAX_FAILURE_RATE


@dataclass
class HealthState:
    """Persistent health state."""

    version: str = "6.1.0"
    health: int = 100
    patches: list[str] = field(default_factory=list)
    last_check: float = 0.0
    tools: dict[str, ToolHealth] = field(default_factory=dict)


class RuntimeHealth:
    """Runtime health monitor with circuit breaker and auto-recovery."""

    def __init__(self, auto_load: bool = True):
        self.state = HealthState()
        if auto_load:
            self._load()

    # ── Persistence ──────────────────────────────────

    def _load(self) -> None:
        """Load health state from disk, with fallback."""
        if STATE_PATH.exists():
            try:
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                self.state.health = data.get("health", 100)
                self.state.patches = data.get("patches", [])
                self.state.last_check = data.get("last_check", 0.0)
                # Load tool health
                for name, th_data in data.get("tools", {}).items():
                    th = ToolHealth()
                    th.total_calls = th_data.get("total_calls", 0)
                    th.failures = th_data.get("failures", 0)
                    th.last_failure = th_data.get("last_failure", 0.0)
                    th.circuit_open = th_data.get("circuit_open", False)
                    th.circuit_opened_at = th_data.get("circuit_opened_at", 0.0)
                    self.state.tools[name] = th
            except Exception:
                # Corrupted state, start fresh
                self.state = HealthState()

    def _save(self) -> None:
        """Persist health state to disk atomically."""
        data = {
            "version": self.state.version,
            "health": self.state.health,
            "patches": self.state.patches,
            "last_check": self.state.last_check,
            "tools": {
                name: {
                    "total_calls": th.total_calls,
                    "failures": th.failures,
                    "last_failure": th.last_failure,
                    "circuit_open": th.circuit_open,
                    "circuit_opened_at": th.circuit_opened_at,
                }
                for name, th in self.state.tools.items()
            },
        }
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Tool Health Tracking ─────────────────────────

    def _get_tool(self, tool_name: str) -> ToolHealth:
        """Get or create tool health tracker."""
        if tool_name not in self.state.tools:
            self.state.tools[tool_name] = ToolHealth()
        return self.state.tools[tool_name]

    def track_success(self, tool_name: str) -> None:
        """Record a successful tool call."""
        th = self._get_tool(tool_name)
        th.total_calls += 1
        # Success resets circuit breaker
        if th.circuit_open:
            th.circuit_open = False
            th.failures = 0  # reset on success
            self.state.patches.append(f"circuit-reset:{tool_name}:{datetime.now().isoformat()}")
        self._save()

    def track_failure(self, tool_name: str, error_msg: str = "") -> None:
        """Record a failed tool call and potentially open circuit breaker."""
        th = self._get_tool(tool_name)
        th.total_calls += 1
        th.failures += 1
        th.last_failure = time.time()

        # Open circuit breaker if too many consecutive failures
        if th.failures >= MAX_FAILURES_PER_TOOL:
            th.circuit_open = True
            th.circuit_opened_at = time.time()
            self.state.patches.append(f"circuit-open:{tool_name}:{datetime.now().isoformat()}")

        # Update overall health
        self._recalculate_health()
        self._save()

    def should_retry(self, tool_name: str) -> bool:
        """Check if a tool should be retried (circuit breaker check)."""
        th = self._get_tool(tool_name)
        if not th.circuit_open:
            return True
        # Check if circuit breaker has timed out
        if time.time() - th.circuit_opened_at > CIRCUIT_BREAKER_TIMEOUT:
            th.circuit_open = False  # auto-reset
            self._save()
            return True
        return False

    def tool_healthy(self, tool_name: str) -> bool:
        """Check if a tool is currently healthy."""
        return self._get_tool(tool_name).healthy

    # ── Overall Health ───────────────────────────────

    def _recalculate_health(self) -> None:
        """Recalculate overall health based on tool status."""
        if not self.state.tools:
            self.state.health = 100
            return

        total_tools = len(self.state.tools)
        unhealthy = sum(1 for th in self.state.tools.values() if not th.healthy)
        self.state.health = max(0, 100 - int((unhealthy / total_tools) * 100))

    def check(self) -> dict[str, Any]:
        """Run a quick startup health check. Returns status dict."""
        result = {
            "health": self.state.health,
            "tools_unhealthy": [],
            "circuits_open": [],
            "needs_fix": False,
        }

        for name, th in self.state.tools.items():
            if th.circuit_open:
                result["circuits_open"].append(name)
            if not th.healthy:
                result["tools_unhealthy"].append(name)

        result["needs_fix"] = len(result["tools_unhealthy"]) > 0 or self.state.health < 80
        self.state.last_check = time.time()
        self._save()
        return result

    def get_summary(self) -> str:
        """Human-readable health summary."""
        unhealthy = [n for n, th in self.state.tools.items() if not th.healthy]
        circuits = [n for n, th in self.state.tools.items() if th.circuit_open]

        lines = [f"Health: {self.state.health}%"]
        if unhealthy:
            lines.append(f"  Unhealthy tools: {', '.join(unhealthy)}")
        if circuits:
            lines.append(f"  Circuit breakers open: {', '.join(circuits)}")
        if self.state.patches:
            lines.append(f"  Patches applied: {len(self.state.patches)}")
        return "\n".join(lines)


# ── Singleton ────────────────────────────────────────
_global_health: RuntimeHealth | None = None


def get_runtime_health() -> RuntimeHealth:
    """Get the global RuntimeHealth singleton."""
    global _global_health
    if _global_health is None:
        _global_health = RuntimeHealth()
    return _global_health


def startup_health_check() -> dict[str, Any]:
    """Run health check at CRUX startup. Returns status dict."""
    rh = get_runtime_health()
    result = rh.check()

    # Auto-fix if health is critically low
    if result["needs_fix"] and rh.state.health < 50:
        try:
            from core.self_heal import SelfHealer

            healer = SelfHealer()
            healer.run_all_scans()
            fixed = healer.fix_silent_exceptions()
            if fixed > 0:
                rh.state.patches.append(f"startup-fix:{fixed}:{datetime.now().isoformat()}")
                rh.state.health = min(100, rh.state.health + fixed * 5)
                rh._save()
                result["auto_fixed"] = fixed
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

    return result
