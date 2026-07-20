# core/trace_debugger.py
"""P10: Trace-first Debugger / Run Inspector.

Records every decision CRUX makes during a session and provides
a human-readable diagnostic report explaining WHY things happened.

Key concepts:
  DecisionRecord — a single decision point (what was chosen and why)
  RunInspector   — assembles all decisions into a readable report
  TracePlayer    — replays a session turn-by-turn for debugging
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 1. Decision types
# ═══════════════════════════════════════════════════════════════════


class DecisionCategory(str, Enum):
    POLICY = "policy"  # P8: mode selection
    TOOL_VALIDATION = "tool_validation"  # P1: validation result
    TOOL_EXECUTION = "tool_execution"  # tool call success/fail
    RESULT_CHECK = "result_check"  # P2: result validation
    CONTEXT_COMPRESSION = "context_compression"  # P3: compression event
    REVIEWER = "reviewer"  # P4: review outcome
    SKILL_COMPILE = "skill_compile"  # P5: skill selection
    TELEMETRY = "telemetry"  # P6: metrics event
    EVAL = "eval"  # P7: scorecard event
    PROJECT_INDEX = "project_index"  # P9: project context
    OTHER = "other"


@dataclass
class DecisionRecord:
    """A single decision point during execution."""

    category: str
    decision: str
    reason: str
    alternatives: list[str] = field(default_factory=list)
    outcome: str = ""
    duration_ms: float = 0.0
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "decision": self.decision,
            "reason": self.reason,
            "alternatives": self.alternatives[:3],
            "outcome": self.outcome,
            "duration_ms": round(self.duration_ms, 1),
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════
# 2. Session-level recorder
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SessionRecord:
    """Full record of a single session's decisions."""

    session_id: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    decisions: list[DecisionRecord] = field(default_factory=list)
    summary: str = ""
    tags: list[str] = field(default_factory=list)

    def record(
        self,
        category: str,
        decision: str,
        reason: str,
        alternatives: list[str] | None = None,
        outcome: str = "",
        duration_ms: float = 0.0,
        metadata: dict | None = None,
    ):
        self.decisions.append(
            DecisionRecord(
                category=category,
                decision=decision,
                reason=reason,
                alternatives=alternatives or [],
                outcome=outcome,
                duration_ms=duration_ms,
                timestamp=time.time(),
                metadata=metadata or {},
            )
        )

    def close(self):
        self.end_time = time.time()

    @property
    def duration(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0

    @property
    def total_decisions(self) -> int:
        return len(self.decisions)

    def by_category(self, category: str) -> list[DecisionRecord]:
        return [d for d in self.decisions if d.category == category]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "duration": round(self.duration, 2),
            "total_decisions": self.total_decisions,
            "start_time": self.start_time,
            "tags": self.tags,
            "decisions": [d.to_dict() for d in self.decisions],
        }


# ═══════════════════════════════════════════════════════════════════
# 3. Run Inspector — build human-readable diagnostic report
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DiagnosticReport:
    """Human-readable report explaining what happened and why."""

    session_id: str = ""
    summary: str = ""
    policy_decision: str = ""
    tool_validation_summary: str = ""
    reviewer_summary: str = ""
    errors: list[dict] = field(default_factory=list)
    timeline: str = ""
    recommendations: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [
            f"🔍 Diagnostic Report: {self.session_id}",
            f"   {self.summary}",
            "",
        ]
        if self.policy_decision:
            lines.append(f"📋 Policy: {self.policy_decision}")
            lines.append("")
        if self.tool_validation_summary:
            lines.append(f"🔧 Tool Calls: {self.tool_validation_summary}")
            lines.append("")
        if self.reviewer_summary:
            lines.append(f"👁 Reviewer: {self.reviewer_summary}")
            lines.append("")
        if self.errors:
            lines.append(f"❌ Errors ({len(self.errors)}):")
            for e in self.errors[:5]:
                lines.append(f"   - {e.get('description', '')}")
            if len(self.errors) > 5:
                lines.append(f"   ... and {len(self.errors) - 5} more")
            lines.append("")
        if self.timeline:
            lines.append("⏱ Timeline:")
            lines.append(self.timeline)
            lines.append("")
        if self.recommendations:
            lines.append("💡 Recommendations:")
            for r in self.recommendations:
                lines.append(f"   - {r}")
        return "\n".join(lines)


class RunInspector:
    """Analyzes a SessionRecord and produces a DiagnosticReport.

    Answers questions like:
    - Why did we enter DEEP mode?
    - Why was the reviewer enabled?
    - Which tools failed and why?
    - Did self-correction fix anything?
    - What did DiffGuard block?
    """

    def inspect(self, record: SessionRecord) -> DiagnosticReport:
        """Analyze a session record and produce a diagnostic report."""
        report = DiagnosticReport(session_id=record.session_id)
        issues: list[dict] = []

        # 1. Policy decision analysis
        policy_decisions = record.by_category(DecisionCategory.POLICY.value)
        if policy_decisions:
            last_policy = policy_decisions[-1]
            report.policy_decision = f"{last_policy.decision} — {last_policy.reason}"
        else:
            report.policy_decision = "No policy routing recorded (using defaults)"

        # 2. Tool validation analysis
        tool_decisions = record.by_category(DecisionCategory.TOOL_VALIDATION.value)
        total_tools = len(tool_decisions)
        blocked = [d for d in tool_decisions if "block" in d.outcome.lower()]
        report.tool_validation_summary = f"{total_tools} calls, {len(blocked)} blocked"
        for b in blocked:
            issues.append(
                {
                    "type": "tool_blocked",
                    "description": f"Tool '{b.decision}' blocked: {b.reason}",
                }
            )

        # 3. Reviewer analysis
        reviewer_decisions = record.by_category(DecisionCategory.REVIEWER.value)
        if reviewer_decisions:
            issues_found = [d for d in reviewer_decisions if d.outcome == "issues_found"]
            report.reviewer_summary = f"{len(reviewer_decisions)} reviews, {len(issues_found)} with issues"
            for rf in issues_found[:3]:
                issues.append(
                    {
                        "type": "reviewer_caught",
                        "description": rf.reason[:200],
                    }
                )
        else:
            report.reviewer_summary = "Not enabled this session"

        # 4. Errors
        report.errors = issues

        # 5. Timeline
        if record.decisions:
            timeline_lines = []
            for d in record.decisions[:15]:
                t = datetime.fromtimestamp(d.timestamp).strftime("%H:%M:%S") if d.timestamp else "??:??"
                timeline_lines.append(f"   {t} [{d.category:18s}] {d.decision[:60]}")
            if len(record.decisions) > 15:
                timeline_lines.append(f"   ... ({len(record.decisions)} total decisions)")
            report.timeline = "\n".join(timeline_lines)

        # 6. Generate recommendations
        recs = []
        if blocked:
            recs.append(f"{len(blocked)} tool calls were blocked — check if tools need schema updates")
        if not policy_decisions:
            recs.append("Enable IntelligencePolicyRouter (P8) for automatic mode selection")
        session_tool_count = len(record.by_category(DecisionCategory.TOOL_EXECUTION.value))
        if session_tool_count > 15:
            recs.append(f"High tool count ({session_tool_count}) — consider TaskDecomposer")
        report.recommendations = recs

        report.summary = f"{record.total_decisions} decisions in {record.duration:.0f}s. {len(issues)} issues detected."
        return report


# ═══════════════════════════════════════════════════════════════════
# 4. Trace Player — replay decisions step by step
# ═══════════════════════════════════════════════════════════════════


class TracePlayer:
    """Replays a session step-by-step for debugging.

    Usage:
        player = TracePlayer(record)
        for step in player.play():
            print(step)
    """

    def __init__(self, record: SessionRecord):
        self.record = record

    def play(self) -> list[str]:
        """Generate a turn-by-turn replay as text lines."""
        lines = [
            f"▶ Replay: {self.record.session_id}",
            f"   {self.record.total_decisions} decisions over {self.record.duration:.0f}s",
            "",
        ]
        for i, d in enumerate(self.record.decisions, 1):
            cat_icon = {
                DecisionCategory.POLICY.value: "🎯",
                DecisionCategory.TOOL_VALIDATION.value: "🔧",
                DecisionCategory.TOOL_EXECUTION.value: "⚙",
                DecisionCategory.REVIEWER.value: "👁",
                DecisionCategory.CONTEXT_COMPRESSION.value: "📦",
            }.get(d.category, "•")
            duration = f"({d.duration_ms:.0f}ms)" if d.duration_ms > 0 else ""
            lines.append(f"  {cat_icon} Step {i:3d}: {d.decision}")
            lines.append(f"       Why: {d.reason[:100]}")
            if d.outcome:
                lines.append(f"       → {d.outcome[:80]}")
            if duration:
                lines.append(f"       {duration}")
            if d.alternatives:
                alt = ", ".join(d.alternatives[:2])
                lines.append(f"       Alternatives: {alt}")

            # Group into pages of 10
            if i % 10 == 0 and i < len(self.record.decisions):
                lines.append(f"  --- page {i // 10} ---")

        return lines

    def search(self, query: str) -> list[DecisionRecord]:
        """Search decisions matching a text query."""
        q = query.lower()
        return [d for d in self.record.decisions if q in d.decision.lower() or q in d.reason.lower()]

    def summary_stats(self) -> dict:
        """Quick statistics about the session."""
        cats: dict[str, int] = {}
        total_ms = 0.0
        for d in self.record.decisions:
            cats[d.category] = cats.get(d.category, 0) + 1
            total_ms += d.duration_ms
        return {
            "total_decisions": self.record.total_decisions,
            "by_category": cats,
            "total_time_ms": round(total_ms, 1),
            "duration_s": round(self.record.duration, 1),
        }


# ═══════════════════════════════════════════════════════════════════
# 5. Global recorder (singleton-like)
# ═══════════════════════════════════════════════════════════════════


class DecisionRecorder:
    """Global decision recorder — records decisions across sessions.

    Usage:
        recorder = DecisionRecorder()
        session = recorder.new_session("session-123")
        session.record("policy", "Selected DEEP mode", "Complex architecture task")
        session.close()
        report = RunInspector().inspect(session)
        print(report.to_text())
    """

    def __init__(self):
        self.sessions: dict[str, SessionRecord] = {}
        self._current: SessionRecord | None = None

    def new_session(self, session_id: str = "", tags: list[str] | None = None) -> SessionRecord:
        """Start a new session record."""
        sid = session_id or f"sess-{int(time.time())}"
        record = SessionRecord(
            session_id=sid,
            start_time=time.time(),
            tags=tags or [],
        )
        self.sessions[sid] = record
        self._current = record
        return record

    @property
    def current(self) -> SessionRecord | None:
        return self._current

    def close_current(self):
        if self._current:
            self._current.close()
            self._current = None

    def get(self, session_id: str) -> SessionRecord | None:
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        return [
            {
                "id": s.session_id,
                "decisions": s.total_decisions,
                "duration": round(s.duration, 1),
                "tags": s.tags,
            }
            for s in self.sessions.values()
        ]

    def save(self, path: str):
        """Save all sessions to JSON."""
        data = {sid: s.to_dict() for sid, s in self.sessions.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self, path: str):
        """Load sessions from JSON."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for sid, sdata in data.items():
            record = SessionRecord(
                session_id=sdata.get("session_id", sid),
                start_time=sdata.get("start_time", 0.0),
                end_time=sdata.get("end_time", 0.0),
                tags=sdata.get("tags", []),
            )
            for dd in sdata.get("decisions", []):
                record.decisions.append(
                    DecisionRecord(
                        category=dd.get("category", ""),
                        decision=dd.get("decision", ""),
                        reason=dd.get("reason", ""),
                        alternatives=dd.get("alternatives", []),
                        outcome=dd.get("outcome", ""),
                        duration_ms=dd.get("duration_ms", 0.0),
                        timestamp=dd.get("timestamp", 0.0),
                    )
                )
            self.sessions[sid] = record


# Global recorder instance
_recorder = DecisionRecorder()


def get_recorder() -> DecisionRecorder:
    return _recorder


def reset_decision_recorder() -> None:
    """Reset decision recorder singleton (for test isolation)."""
    global _recorder
    _recorder = DecisionRecorder()
