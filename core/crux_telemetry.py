# core/crux_telemetry.py
"""Phase 6: Telemetry Tracker + Feature Flags + Eval Runner.

Three subsystems:

1. TelemetryTracker — event recording, phase hit rates, timing, aggregation
2. FeatureConfig — per-phase on/off switches with task-target awareness  
3. EvalRunner — replay recorded conversations for regression testing

Design: all data in-memory by default, optional JSON export.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. Telemetry Tracker
# ═══════════════════════════════════════════════════════════════════


class TelemetryEvent(str, Enum):
    TOOL_VALIDATION = "tool_validation"
    TOOL_VALIDATION_BLOCKED = "tool_validation_blocked"
    TOOL_VALIDATION_PASSED = "tool_validation_passed"
    RESULT_VALIDATION = "result_validation"
    RESULT_VALIDATION_FAILED = "result_validation_failed"
    CONSISTENCY_CHECK = "consistency_check"
    CONSISTENCY_ISSUE = "consistency_issue"
    DIFF_GUARD = "diff_guard"
    DIFF_SUSPICIOUS = "diff_suspicious"
    CONTEXT_COMPRESSION = "context_compression"
    CONTEXT_BUDGET_WARN = "context_budget_warn"
    REVIEWER_RUN = "reviewer_run"
    REVIEWER_ISSUE = "reviewer_issue"
    REVIEWER_CRITICAL = "reviewer_critical"
    DEBATE_RUN = "debate_run"
    TASK_DECOMPOSE = "task_decompose"
    SKILL_COMPILE = "skill_compile"
    PROMPT_COMPILE = "prompt_compile"


@dataclass
class TelemetryRecord:
    """A single telemetry event record."""
    event: str
    phase: str = ""
    tool_name: str = ""
    duration_ms: float = 0.0
    success: bool = True
    detail: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "phase": self.phase,
            "tool_name": self.tool_name,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "detail": self.detail[:200],
            "timestamp": self.timestamp,
        }


@dataclass
class PhaseStats:
    """Aggregated stats for a single phase."""
    total_calls: int = 0
    passed: int = 0
    blocked: int = 0
    total_duration_ms: float = 0.0
    last_event: str = ""

    @property
    def avg_duration_ms(self) -> float:
        return round(self.total_duration_ms / self.total_calls, 2) if self.total_calls > 0 else 0.0

    @property
    def block_rate(self) -> float:
        return round(self.blocked / self.total_calls * 100, 1) if self.total_calls > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "passed": self.passed,
            "blocked": self.blocked,
            "block_rate_pct": self.block_rate,
            "avg_duration_ms": self.avg_duration_ms,
            "last_event": self.last_event,
        }


class TelemetryTracker:
    """Records and aggregates telemetry events from all phases.

    Usage:
        tracker = TelemetryTracker()
        tracker.record("tool_validation", phase="p1", tool_name="read_file", duration_ms=12.3)
        report = tracker.summary()  # aggregated stats
        tracker.export("telemetry.json")
    """

    def __init__(self, max_records: int = 10000):
        self.records: list[TelemetryRecord] = []
        self.max_records = max_records
        self._start_time = time.time()

    def record(
        self,
        event: str,
        phase: str = "",
        tool_name: str = "",
        duration_ms: float = 0.0,
        success: bool = True,
        detail: str = "",
    ) -> TelemetryRecord:
        """Record a telemetry event."""
        rec = TelemetryRecord(
            event=event,
            phase=phase,
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=success,
            detail=detail,
            timestamp=time.time(),
        )
        self.records.append(rec)

        # Prune if over limit
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records:]

        return rec

    def record_duration(self, event: str, phase: str = "", tool_name: str = "") -> _TimerContext:
        """Context manager to record duration automatically.

        Usage:
            with tracker.record_duration("tool_validation", phase="p1", tool_name="read_file"):
                result = do_something()
        """
        return _TimerContext(self, event, phase, tool_name)

    def summary(self) -> dict[str, PhaseStats]:
        """Aggregate stats by phase."""
        phases: dict[str, PhaseStats] = {}
        for rec in self.records:
            key = rec.phase or "general"
            if key not in phases:
                phases[key] = PhaseStats()
            ps = phases[key]
            ps.total_calls += 1
            ps.total_duration_ms += rec.duration_ms
            ps.last_event = rec.event
            if rec.success:
                ps.passed += 1
            else:
                ps.blocked += 1
        return phases

    def by_event(self, event: str) -> list[TelemetryRecord]:
        """Filter records by event type."""
        return [r for r in self.records if r.event == event]

    def by_phase(self, phase: str) -> list[TelemetryRecord]:
        return [r for r in self.records if r.phase == phase]

    def report(self) -> str:
        """Human-readable summary report."""
        phases = self.summary()
        lines = [
            f"📊 Telemetry Report — {len(self.records)} events, {time.time()-self._start_time:.0f}s uptime",
            "",
        ]
        # Phase summary
        lines.append(f"  {'Phase':12s} {'Calls':8s} {'Blocked':10s} {'Block%':8s} {'Avg(ms)':10s}")
        lines.append(f"  {'-'*12} {'-'*8} {'-'*10} {'-'*8} {'-'*10}")
        for phase, ps in sorted(phases.items()):
            lines.append(f"  {phase:12s} {ps.total_calls:8d} {ps.blocked:10d} {ps.block_rate:7.1f}% {ps.avg_duration_ms:9.1f}")
        lines.append("")
        # Recent events
        lines.append("  Recent events:")
        for rec in self.records[-5:]:
            lines.append(f"    [{rec.event:30s}] {rec.tool_name:20s} {'OK' if rec.success else 'BLOCKED'} {rec.duration_ms:6.1f}ms")
        return "\n".join(lines)

    def export(self, path: str = "telemetry.json") -> str:
        """Export telemetry data to JSON file."""
        data = {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "total_events": len(self.records),
            "phases": {k: v.to_dict() for k, v in self.summary().items()},
            "recent_events": [r.to_dict() for r in self.records[-100:]],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    @property
    def total_events(self) -> int:
        return len(self.records)


class _TimerContext:
    """Context manager for recording durations."""

    def __init__(self, tracker: TelemetryTracker, event: str, phase: str, tool_name: str):
        self.tracker = tracker
        self.event = event
        self.phase = phase
        self.tool_name = tool_name
        self._start: float = 0.0
        self._success = True

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.time() - self._start) * 1000
        if exc_type is not None:
            self._success = False
        self.tracker.record(
            event=self.event,
            phase=self.phase,
            tool_name=self.tool_name,
            duration_ms=duration,
            success=self._success,
        )


# ═══════════════════════════════════════════════════════════════════
# 2. Feature Flags / Config
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FeatureConfig:
    """Per-phase feature flags with target awareness.

    Each phase can be:
    - enabled/disabled globally
    - enabled only for specific task targets (media/code/general)
    - throttled by a sample rate (0.0-1.0)

    Default: all phases enabled for all targets.
    """

    # Phase 1: Tool call validation
    p1_tool_validation: bool = True
    p1_max_retries: int = 3

    # Phase 2: Result validation
    p2_result_validation: bool = True
    p2_consistency_check: bool = True
    p2_diff_guard: bool = True

    # Phase 3: Context memory
    p3_budget_tracker: bool = True
    p3_memory_working: bool = True
    p3_memory_episodic: bool = True
    p3_memory_semantic: bool = True

    # Phase 4: Reviewer
    p4_reviewer: bool = True
    p4_debate: bool = False  # debate is expensive, off by default
    p4_task_decomposer: bool = True
    p4_reviewer_min_tokens: int = 500  # only review responses > 500 chars

    # Phase 5: Skill compiler
    p5_skill_compiler: bool = True
    p5_max_prompt_tokens: int = 32000

    # Phase 6: Telemetry
    p6_telemetry: bool = True
    p6_eval_logging: bool = True

    # Per-target overrides
    # If a phase is in disabled_for_targets, it won't run for that target
    disabled_for_targets: dict[str, list[str]] = field(default_factory=lambda: {
        "reviewer": ["general"],  # skip reviewer for simple chat
        "debate": ["general", "code"],  # only for complex media tasks
    })

    def is_enabled(self, phase_key: str, task_target: str = "general") -> bool:
        """Check if a phase is enabled for a given task target.

        Args:
            phase_key: One of "p1", "p2", "p3", "p4", "p5", "p6"
                      or specific feature names like "reviewer", "debate"
            task_target: "media", "code", "general"
        """
        # Check by phase key
        attr_map = {
            "p1": ("p1_tool_validation",),
            "p2": ("p2_result_validation", "p2_consistency_check"),
            "p3": ("p3_budget_tracker",),
            "p4": ("p4_reviewer",),
            "p5": ("p5_skill_compiler",),
            "p6": ("p6_telemetry",),
        }
        if phase_key in attr_map:
            for attr in attr_map[phase_key]:
                if not getattr(self, attr, True):
                    return False

        # Check per-target override
        disabled = self.disabled_for_targets.get(phase_key, [])
        if task_target in disabled:
            return False

        return True

    def disable_all(self):
        """Disable all phases (for testing)."""
        for attr in dir(self):
            if attr.startswith("p") and "_" in attr and isinstance(getattr(self, attr), bool):
                setattr(self, attr, False)

    def enable_all(self):
        """Enable all phases."""
        for attr in dir(self):
            if attr.startswith("p") and "_" in attr and isinstance(getattr(self, attr), bool):
                setattr(self, attr, True)

    def to_dict(self) -> dict:
        return {
            attr: getattr(self, attr)
            for attr in dir(self)
            if attr.startswith("p") and not attr.startswith("__")
        }


# Default global config
GLOBAL_CONFIG = FeatureConfig()


def get_config() -> FeatureConfig:
    """Get the global feature config."""
    return GLOBAL_CONFIG


# ═══════════════════════════════════════════════════════════════════
# 3. Eval Runner
# ═══════════════════════════════════════════════════════════════════


@dataclass
class EvalTurn:
    """A single turn in a recorded conversation."""
    user: str = ""
    assistant: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    expected_issues: int = 0  # 0 = expected to pass


@dataclass
class EvalSession:
    """A recorded conversation session for regression testing."""
    id: str = ""
    description: str = ""
    created_at: float = 0.0
    turns: list[EvalTurn] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "created_at": self.created_at,
            "tags": self.tags,
            "turns": [
                {"user": t.user[:500], "assistant": t.assistant[:500],
                 "tool_calls": t.tool_calls[:5], "tool_results": t.tool_results[:5],
                 "expected_issues": t.expected_issues}
                for t in self.turns
            ],
        }


@dataclass
class EvalResult:
    """Result of running an evaluation session."""
    session_id: str = ""
    passed: int = 0
    failed: int = 0
    details: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def pass_rate(self) -> float:
        return round(self.passed / self.total * 100, 1) if self.total > 0 else 0.0

    def summary(self) -> str:
        return f"Eval {self.session_id}: {self.passed}/{self.total} passed ({self.pass_rate}%)"


class EvalRunner:
    """Replay recorded conversations for regression testing.

    Runs each turn through ValidationLayer and checks:
    - P1: tool validation catches expected errors
    - P2: result validation catches expected failures
    - P4: reviewer catches expected issues

    Usage:
        runner = EvalRunner()
        runner.add_session(session)
        result = runner.run_all()
        print(result.summary())
    """

    def __init__(self):
        self.sessions: list[EvalSession] = []

    def add_session(self, session: EvalSession):
        self.sessions.append(session)

    def load(self, path: str) -> list[EvalSession]:
        """Load sessions from JSON file."""
        if not os.path.exists(path):
            logger.warning(f"Eval file not found: {path}")
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data:
            session = EvalSession(
                id=s.get("id", ""),
                description=s.get("description", ""),
                created_at=s.get("created_at", 0.0),
                tags=s.get("tags", []),
            )
            for t in s.get("turns", []):
                session.turns.append(EvalTurn(
                    user=t.get("user", ""),
                    assistant=t.get("assistant", ""),
                    tool_calls=t.get("tool_calls", []),
                    tool_results=t.get("tool_results", []),
                    expected_issues=t.get("expected_issues", 0),
                ))
            self.sessions.append(session)
        return self.sessions

    def save(self, path: str):
        """Save all sessions to JSON file."""
        data = [s.to_dict() for s in self.sessions]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def run_all(self) -> list[EvalResult]:
        """Run all sessions and return results."""
        return [self._run_session(s) for s in self.sessions]

    def _run_session(self, session: EvalSession) -> EvalResult:
        """Run a single session."""
        result = EvalResult(session_id=session.id)
        for turn in session.turns:
            # Run through validation checks
            issues_found = 0
            try:
                from core.tool_call_validator import ToolCallValidator
                schema_p = lambda n: None
                v = ToolCallValidator(schema_provider=schema_p)
                for tc in turn.tool_calls:
                    r = v.validate_llm_output(tc.get("raw_xml", str(tc)))
                    if not r.is_valid:
                        issues_found += len(r.issues)
            except Exception:
                logger.debug("Exception in crux_telemetry", exc_info=True)

            # Check if expectation matches
            if issues_found >= turn.expected_issues:
                result.passed += 1
            else:
                result.failed += 1
                result.details.append({
                    "user": turn.user[:100],
                    "expected": turn.expected_issues,
                    "found": issues_found,
                })

        return result


# ═══════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════

# Global telemetry tracker
_telemetry = TelemetryTracker()


def get_telemetry() -> TelemetryTracker:
    return _telemetry
