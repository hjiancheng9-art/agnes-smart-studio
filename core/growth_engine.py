"""GrowthEngine — adaptive routing that gets smarter with every call.

Every tool invocation through TRM feeds back into the engine:
  - Record success/failure + latency per (intent, tool) pair
  - Auto-demote tools after consecutive failures
  - Auto-restore probated tools after successful probes
  - Periodically recalculate optimal route order
  - Persist stats to disk so growth survives restarts

The engine is transparent: it observes, learns, and optimizes without
requiring any changes to existing tool call workflows.

Usage:
    from core.growth_engine import get_growth_engine

    ge = get_growth_engine()
    ge.record("search", "code_search", success=True, latency_ms=120)
    optimized = ge.get_route("search")  # → ["code_search", ...]
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
STATS_FILE = ROOT / ".crux_memory" / "growth.json"

# ── Demotion / probation rules ────────────────────────────
CONSECUTIVE_FAIL_THRESHOLD = 3  # auto-demote after this many failures in a row
PROBATION_PROBE_INTERVAL = 5  # try a demoted tool every N calls for that intent
PROBATION_SUCCESS_TO_RESTORE = 3  # successful probes needed to restore
RECALC_INTERVAL = 10  # recalculate weights every N total calls per intent


@dataclass
class ToolStats:
    tool: str
    source: str = ""
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    consecutive_failures: int = 0
    demoted: bool = False
    probation_successes: int = 0
    last_call_ts: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.calls == 0:
            return 0.5  # neutral prior
        return self.successes / self.calls

    @property
    def avg_latency_ms(self) -> float:
        if self.calls == 0:
            return 9999.0
        return self.total_latency_ms / self.calls

    @property
    def score(self) -> float:
        """Composite score: 70% success rate + 30% speed (normalized)."""
        speed_score = max(0, 1.0 - (self.avg_latency_ms / 30000.0))  # 30s max reference
        return self.success_rate * 0.7 + speed_score * 0.3

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "source": self.source,
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "total_latency_ms": self.total_latency_ms,
            "consecutive_failures": self.consecutive_failures,
            "demoted": self.demoted,
            "probation_successes": self.probation_successes,
            "last_call_ts": self.last_call_ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ToolStats:
        return cls(
            **{
                k: d.get(k, 0)
                for k in [
                    "tool",
                    "source",
                    "calls",
                    "successes",
                    "failures",
                    "total_latency_ms",
                    "consecutive_failures",
                    "demoted",
                    "probation_successes",
                    "last_call_ts",
                ]
            }
        )


@dataclass
class IntentStats:
    intent: str
    tools: dict[str, ToolStats] = field(default_factory=dict)
    total_calls: int = 0
    last_recalc_at: int = 0  # total_calls at last recalculation

    def ensure_tool(self, tool: str, source: str = "") -> ToolStats:
        if tool not in self.tools:
            self.tools[tool] = ToolStats(tool=tool, source=source)
        return self.tools[tool]

    @property
    def ordered_tools(self) -> list[ToolStats]:
        """Tools ordered by score (highest first), demoted tools at bottom."""
        active = [t for t in self.tools.values() if not t.demoted]
        demoted = [t for t in self.tools.values() if t.demoted]
        active.sort(key=lambda t: t.score, reverse=True)
        demoted.sort(key=lambda t: t.score, reverse=True)
        return active + demoted

    @property
    def tool_names(self) -> list[str]:
        return [t.tool for t in self.ordered_tools]

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "tools": {k: v.to_dict() for k, v in self.tools.items()},
            "total_calls": self.total_calls,
            "last_recalc_at": self.last_recalc_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> IntentStats:
        is_ = cls(intent=d.get("intent", ""))
        is_.tools = {k: ToolStats.from_dict(v) for k, v in d.get("tools", {}).items()}
        is_.total_calls = d.get("total_calls", 0)
        is_.last_recalc_at = d.get("last_recalc_at", 0)
        return is_


# ═══════════════════════════════════════════════════════════════
# Growth Engine
# ═══════════════════════════════════════════════════════════════


class GrowthEngine:
    """Adaptive routing optimizer — learns from every tool call.

    Lifecycle:
      1. record() is called after every TRM route invocation
      2. Stats accumulate per (intent, tool)
      3. Demotion / restoration happens automatically
      4. get_route() returns optimized tool order
      5. save() persists to disk periodically
    """

    def __init__(self) -> None:
        self.intents: dict[str, IntentStats] = {}
        self._dirty = False  # true when there are unsaved changes
        self._last_save = 0.0
        self._save_interval = 30.0  # auto-save at most every 30 seconds
        self._total_calls_ever = 0
        self.load()

    # ── Recording ──────────────────────────────────────────

    def record(self, intent: str, tool: str, *, success: bool, latency_ms: float = 0, source: str = "") -> ToolStats:
        """Record a tool call outcome. Returns updated ToolStats."""
        is_ = self._ensure_intent(intent)
        ts = is_.ensure_tool(tool, source)

        ts.calls += 1
        ts.total_latency_ms += latency_ms
        ts.last_call_ts = time.monotonic()

        if success:
            ts.successes += 1
            ts.consecutive_failures = 0

            # Probation recovery
            if ts.demoted:
                ts.probation_successes += 1
                if ts.probation_successes >= PROBATION_SUCCESS_TO_RESTORE:
                    ts.demoted = False
                    ts.probation_successes = 0
        else:
            ts.failures += 1
            ts.consecutive_failures += 1

            # Auto-demotion
            if not ts.demoted and ts.consecutive_failures >= CONSECUTIVE_FAIL_THRESHOLD:
                ts.demoted = True
                ts.probation_successes = 0

        is_.total_calls += 1
        self._total_calls_ever += 1
        self._dirty = True

        # Periodically recalculate
        if is_.total_calls - is_.last_recalc_at >= RECALC_INTERVAL:
            is_.last_recalc_at = is_.total_calls

        # Auto-save
        if time.monotonic() - self._last_save > self._save_interval:
            self.save()

        return ts

    # ── Routing ────────────────────────────────────────────

    def get_route(self, intent: str) -> list[str]:
        """Get optimized tool ordering for an intent.

        Returns tool names ordered by learned performance.
        Demoted tools are at the end but still included as fallbacks.
        Every PROBATION_PROBE_INTERVAL calls, a demoted tool gets promoted
        to position 0 for one call (probationary probe).
        """
        is_ = self.intents.get(intent)
        if is_ is None:
            return []

        ordered = is_.tool_names

        # Probation probe: periodically test a demoted tool
        demoted = [n for n in ordered if n in is_.tools and is_.tools[n].demoted]
        if demoted and is_.total_calls > 0 and is_.total_calls % PROBATION_PROBE_INTERVAL == 0:
            probe_tool = demoted[is_.total_calls // PROBATION_PROBE_INTERVAL % len(demoted)]
            ordered = [probe_tool] + [n for n in ordered if n != probe_tool]

        return ordered

    def get_tool_stats(self, intent: str, tool: str) -> ToolStats | None:
        """Get detailed stats for a specific (intent, tool) pair."""
        is_ = self.intents.get(intent)
        if is_ is None:
            return None
        return is_.tools.get(tool)

    def get_summary(self) -> str:
        """Human-readable growth summary."""
        lines = [
            f"Growth Engine — {self._total_calls_ever} total calls",
            f"Intents tracked: {len(self.intents)}",
        ]
        for intent, is_ in sorted(self.intents.items()):
            tools_str = ", ".join(f"{t.tool}({t.score:.2f}{' D' if t.demoted else ''})" for t in is_.ordered_tools)
            lines.append(f"  [{intent}] ({is_.total_calls} calls) -> {tools_str}")
        return "\n".join(lines)

    # ── Self-optimization (内秀优化) ──────────────────────────

    # Optimized routing overrides — written to disk and applied by TRM.
    # GrowthEngine is the source of truth; static CATEGORY_META is the fallback.
    optimized_routes: dict[str, list[str]] = {}

    def auto_tune(self, apply: bool = True) -> dict:
        """Analyze growth data and ACTUALLY modify routing parameters.

        When apply=True (default), this writes optimized config to disk.
        CRUX's TRM reads this config on next route() call.
        This is CRUX learning to be faster/stronger without human input.

        Returns a dict of changes made.
        """
        changes: dict[str, Any] = {"applied": [], "recommendations": []}
        if self._total_calls_ever < 10:
            return {"status": "insufficient data", "min_calls": 10}

        for intent, is_ in self.intents.items():
            if is_.total_calls < 5:
                continue

            ordered_names = is_.tool_names  # already scored+demoted
            active_names = [n for n in ordered_names if n in is_.tools and not is_.tools[n].demoted]

            # Remove dead tools (0% success over 10+ calls)
            cleaned = []
            for n in active_names:
                ts = is_.tools[n]
                if ts.calls >= 10 and ts.success_rate == 0.0:
                    changes["applied"].append(
                        {
                            "action": "remove_dead_tool",
                            "intent": intent,
                            "tool": n,
                            "reason": f"0% success over {ts.calls} calls",
                        }
                    )
                    continue
                cleaned.append(n)

            # Reorder: best performer → primary
            if len(cleaned) >= 2:
                sorted_by_score = sorted(cleaned, key=lambda n: is_.tools[n].score, reverse=True)
                if sorted_by_score != cleaned:
                    changes["applied"].append(
                        {
                            "action": "reorder_routing",
                            "intent": intent,
                            "old_order": list(cleaned),
                            "new_order": sorted_by_score,
                        }
                    )
                    cleaned = sorted_by_score

            # Store optimized route
            self.optimized_routes[intent] = cleaned

        # Auto-demote thresholds: if best tool's score changed significantly,
        # adjust demotion threshold
        for intent, is_ in self.intents.items():
            active = [t for t in is_.tools.values() if not t.demoted and t.calls >= 5]
            if active:
                avg_score = sum(t.score for t in active) / len(active)
                if avg_score > 0.85:
                    # Mesh is healthy — be stricter about demotion
                    changes["recommendations"].append(f"[{intent}] 网格健康 (均分 {avg_score:.2f})，可降低降级阈值")

        if apply:
            if changes["applied"]:
                self._write_optimized_config()
            self.save()

        changes["_analyzed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        changes["_total_calls"] = self._total_calls_ever
        return changes

    def _write_optimized_config(self) -> None:
        """Write optimized routing config that TRM reads at runtime."""
        config_path = STATS_FILE.parent / "optimized_routes.json"
        data = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_calls": self._total_calls_ever,
            "routes": self.optimized_routes,
            "demoted": {
                f"{intent}/{ts.tool}": {
                    "calls": ts.calls,
                    "success_rate": ts.success_rate,
                    "consecutive_failures": ts.consecutive_failures,
                }
                for intent, is_ in self.intents.items()
                for ts in is_.tools.values()
                if ts.demoted
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def detect_bottlenecks(self) -> list[dict]:
        """Identify performance bottlenecks in the mesh."""
        bottlenecks: list[dict] = []
        if self._total_calls_ever < 5:
            return bottlenecks

        for intent, is_ in self.intents.items():
            for ts in is_.tools.values():
                severity = 0
                reasons: list[str] = []
                if ts.calls >= 3 and ts.success_rate < 0.4:
                    severity += 3
                    reasons.append(f"Low success rate ({ts.success_rate:.0%})")
                if ts.calls >= 5 and ts.avg_latency_ms > 15000:
                    severity += 2
                    reasons.append(f"High latency ({ts.avg_latency_ms:.0f}ms avg)")
                if ts.consecutive_failures >= 2:
                    severity += 1
                    reasons.append(f"{ts.consecutive_failures} consecutive failures")
                if ts.demoted:
                    severity += 1
                    reasons.append("Demoted (auto)")
                if severity >= 3:
                    bottlenecks.append(
                        {
                            "intent": intent,
                            "tool": ts.tool,
                            "severity": severity,
                            "reasons": reasons,
                            "stats": {
                                "calls": ts.calls,
                                "success_rate": ts.success_rate,
                                "avg_latency_ms": ts.avg_latency_ms,
                            },
                        }
                    )
        bottlenecks.sort(key=lambda b: b["severity"], reverse=True)
        return bottlenecks

    def suggest_improvements(self) -> list[str]:
        """Generate actionable self-improvement suggestions."""
        suggestions: list[str] = []
        bottlenecks = self.detect_bottlenecks()
        for b in bottlenecks[:5]:
            if b["severity"] >= 5:
                suggestions.append(
                    f"[严重] {b['intent']}/{b['tool']}: 成功率 {b['stats']['success_rate']:.0%}, 需立即检查"
                )
        for intent, is_ in self.intents.items():
            if is_.total_calls >= 10:
                names = is_.tool_names
                if len(names) >= 2:
                    top = is_.tools[names[0]] if names else None
                    if top and top.calls > 0 and top.calls / max(is_.total_calls, 1) > 0.9:
                        suggestions.append(
                            f"[建议] {intent}: {top.tool} 占比 {top.calls / max(is_.total_calls, 1):.0%}, "
                            "其他工具未充分验证"
                        )
        if not suggestions:
            suggestions.append("当前配置运行良好。继续使用以获取更多优化数据。")
        return suggestions

    # ── Persistence ────────────────────────────────────────

    def save(self) -> None:
        """Persist growth stats to disk."""
        if not self._dirty:
            return
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total_calls_ever": self._total_calls_ever,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "intents": {k: v.to_dict() for k, v in self.intents.items()},
        }
        STATS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self._dirty = False
        self._last_save = time.monotonic()

    def load(self) -> None:
        """Load growth stats from disk."""
        if not STATS_FILE.exists():
            return
        try:
            data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
            self._total_calls_ever = data.get("total_calls_ever", 0)
            self.intents = {k: IntentStats.from_dict(v) for k, v in data.get("intents", {}).items()}
        except (json.JSONDecodeError, OSError, KeyError):
            pass  # corrupted file → start fresh

    # ── Internal ───────────────────────────────────────────

    def _ensure_intent(self, intent: str) -> IntentStats:
        if intent not in self.intents:
            self.intents[intent] = IntentStats(intent=intent)
        return self.intents[intent]

    def reset(self) -> None:
        """Reset all stats (dangerous, for testing)."""
        self.intents.clear()
        self._total_calls_ever = 0
        self._dirty = True
        if STATS_FILE.exists():
            STATS_FILE.unlink()


# ═══════════════════════════════════════════════════════════════
# Singleton + auto-hook
# ═══════════════════════════════════════════════════════════════

_instance: GrowthEngine | None = None


def get_growth_engine() -> GrowthEngine:
    global _instance
    if _instance is None:
        _instance = GrowthEngine()
    return _instance


def hook_trm_route(intent: str, tool: str, success: bool, latency_ms: float, source: str = "") -> ToolStats:
    """Convenience: record a TRM route call to the growth engine."""
    return get_growth_engine().record(
        intent=intent,
        tool=tool,
        success=success,
        latency_ms=latency_ms,
        source=source,
    )
