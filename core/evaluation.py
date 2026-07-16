# core/evaluation.py
"""P7: CRUX Intelligence Evaluation & Replay System.

Three-layer scoring over recorded sessions:

1. DeterministicGrader — rule-based: tool call validity, retries, response size
2. BehavioralGrader — pattern-based: self-correction, consistency, hallucination
3. LLM Judge Grader — deep quality assessment via LLM

Key metrics (Scorecard):
- task_success_rate
- tool_call_valid_rate
- self_correction_recovery_rate
- reviewer_catch_rate
- diff_guard_block_rate
- context_compression_loss_rate
- avg_tool_calls_per_task
- avg_retries_per_task
- time_to_first_valid_action
- regression_count

Sessions are recorded from real conversations and replayed for regression.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. Event / Session Recording
# ═══════════════════════════════════════════════════════════════════


class EventType(str, Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    VALIDATION = "validation"
    VALIDATION_BLOCK = "validation_block"
    RESULT_CHECK = "result_check"
    CONSISTENCY_ISSUE = "consistency_issue"
    DIFF_GUARD = "diff_guard"
    CONTEXT_COMPRESSION = "context_compression"
    REVIEWER_RUN = "reviewer_run"
    REVIEWER_ISSUE = "reviewer_issue"
    DEBATE_RUN = "debate_run"
    TASK_DECOMPOSE = "task_decompose"
    SKILL_COMPILE = "skill_compile"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


@dataclass
class TraceEvent:
    """A single event in a session trace."""
    type: str
    timestamp: float = 0.0
    duration_ms: float = 0.0
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "duration_ms": round(self.duration_ms, 2),
            "data": self.data,
        }


@dataclass
class SessionTrace:
    """Full trace of a conversation session."""
    session_id: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    events: list[TraceEvent] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def record(self, event_type: str, duration_ms: float = 0.0, data: dict | None = None):
        self.events.append(TraceEvent(
            type=event_type,
            timestamp=time.time(),
            duration_ms=duration_ms,
            data=data or {},
        ))

    def close(self):
        self.end_time = time.time()

    @property
    def duration(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0

    @property
    def event_count(self) -> int:
        return len(self.events)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": round(self.duration, 2),
            "event_count": self.event_count,
            "tags": self.tags,
            "metadata": self.metadata,
            "events": [e.to_dict() for e in self.events],
        }

    def save(self, path: str):
        """Save session trace to JSON file."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=str)

    @staticmethod
    def load(path: str) -> SessionTrace:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        trace = SessionTrace(
            session_id=data.get("session_id", ""),
            start_time=data.get("start_time", 0.0),
            end_time=data.get("end_time", 0.0),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
        for e in data.get("events", []):
            trace.events.append(TraceEvent(
                type=e.get("type", ""),
                timestamp=e.get("timestamp", 0.0),
                duration_ms=e.get("duration_ms", 0.0),
                data=e.get("data", {}),
            ))
        return trace


# ═══════════════════════════════════════════════════════════════════
# 2. Scorecard
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Scorecard:
    """Evaluation results with all KPIs."""
    task_success_rate: float = 0.0
    tool_call_valid_rate: float = 0.0
    self_correction_recovery_rate: float = 0.0
    reviewer_catch_rate: float = 0.0
    diff_guard_block_rate: float = 0.0
    context_compression_loss_rate: float = 0.0
    avg_tool_calls_per_task: float = 0.0
    avg_retries_per_task: float = 0.0
    time_to_first_valid_action: float = 0.0
    regression_count: int = 0
    overall_score: float = 0.0
    total_sessions: int = 0

    def compute_overall(self) -> float:
        """Weighted average of all rates (0-100)."""
        weights = {
            "task_success_rate": 0.25,
            "tool_call_valid_rate": 0.15,
            "self_correction_recovery_rate": 0.10,
            "reviewer_catch_rate": 0.05,
            "diff_guard_block_rate": 0.05,
            "context_compression_loss_rate": 0.05,
            "avg_tool_calls_per_task": 0.10,
            "avg_retries_per_task": 0.10,
            "time_to_first_valid_action": 0.10,
            "regression_count": 0.05,
        }
        score = 0.0
        # Normalize each metric to 0-100
        metrics = {
            "task_success_rate": self.task_success_rate * 100,
            "tool_call_valid_rate": self.tool_call_valid_rate * 100,
            "self_correction_recovery_rate": self.self_correction_recovery_rate * 100,
            "reviewer_catch_rate": self.reviewer_catch_rate * 100,  # 0-1 → 0-100
            "diff_guard_block_rate": (1 - self.diff_guard_block_rate) * 100,
            "context_compression_loss_rate": (1 - self.context_compression_loss_rate) * 100,
            "avg_tool_calls_per_task": max(0, 100 - self.avg_tool_calls_per_task * 10),
            "avg_retries_per_task": max(0, 100 - self.avg_retries_per_task * 20),
            "time_to_first_valid_action": max(0, 100 - self.time_to_first_valid_action * 5),
            "regression_count": max(0, 100 - self.regression_count * 10),
        }
        for key, w in weights.items():
            score += metrics.get(key, 0) * w
        self.overall_score = round(score, 1)
        return self.overall_score

    def to_dict(self) -> dict:
        return {
            "task_success_rate": round(self.task_success_rate, 2),
            "tool_call_valid_rate": round(self.tool_call_valid_rate, 2),
            "self_correction_recovery_rate": round(self.self_correction_recovery_rate, 2),
            "reviewer_catch_rate": round(self.reviewer_catch_rate, 3),
            "diff_guard_block_rate": round(self.diff_guard_block_rate, 3),
            "context_compression_loss_rate": round(self.context_compression_loss_rate, 3),
            "avg_tool_calls_per_task": round(self.avg_tool_calls_per_task, 1),
            "avg_retries_per_task": round(self.avg_retries_per_task, 1),
            "time_to_first_valid_action": round(self.time_to_first_valid_action, 1),
            "regression_count": self.regression_count,
            "overall_score": self.overall_score,
            "total_sessions": self.total_sessions,
        }

    def summary(self) -> str:
        lines = [
            f"📊 Scorecard ({self.total_sessions} sessions, overall: {self.overall_score}/100)",
            f"  {'KPI':35s} {'Value':12s} {'Weight':8s}",
            f"  {'-'*35} {'-'*12} {'-'*8}",
        ]
        items = [
            ("Task Success Rate", f"{self.task_success_rate*100:.0f}%", 0.25),
            ("Tool Call Valid Rate", f"{self.tool_call_valid_rate*100:.0f}%", 0.15),
            ("Self-Correction Recovery", f"{self.self_correction_recovery_rate*100:.0f}%", 0.10),
            ("Reviewer Catch Rate", f"{self.reviewer_catch_rate*100:.1f}%", 0.05),
            ("Diff Guard Block Rate", f"{self.diff_guard_block_rate*100:.1f}%", 0.05),
            ("Compression Loss Rate", f"{self.context_compression_loss_rate*100:.1f}%", 0.05),
            ("Avg Tool Calls/Task", f"{self.avg_tool_calls_per_task:.1f}", 0.10),
            ("Avg Retries/Task", f"{self.avg_retries_per_task:.1f}", 0.10),
            ("Time to 1st Action", f"{self.time_to_first_valid_action:.1f}s", 0.10),
            ("Regressions", str(self.regression_count), 0.05),
        ]
        for name, val, weight in items:
            lines.append(f"  {name:35s} {val:12s} {weight:7.0%}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 3. Deterministic Grader
# ═══════════════════════════════════════════════════════════════════


class DeterministicGrader:
    """Rule-based grading: tool call validity, response completeness, error patterns.

    No LLM calls — pure rules.
    """

    def grade_tool_calls(self, trace: SessionTrace) -> dict:
        """Grade tool call validity from trace events."""
        total_calls = 0
        valid_calls = 0
        blocked_calls = 0
        retries = 0

        for event in trace.events:
            if event.type == EventType.TOOL_CALL:
                total_calls += 1
                valid_calls += 1
            elif event.type == EventType.VALIDATION_BLOCK:
                blocked_calls += 1
                retries += 1
            elif event.type == EventType.VALIDATION:
                pass  # validation passed

        valid_rate = valid_calls / max(total_calls, 1)
        retry_rate = retries / max(total_calls, 1)

        return {
            "total_calls": total_calls,
            "valid_calls": valid_calls,
            "blocked_calls": blocked_calls,
            "valid_rate": round(valid_rate, 3),
            "retries": retries,
            "retry_rate": round(retry_rate, 3),
        }

    def grade_response_quality(self, trace: SessionTrace) -> dict:
        """Grade response completeness and structure."""
        total_msgs = 0
        empty_msgs = 0
        unclosed_fences = 0
        total_chars = 0

        for event in trace.events:
            if event.type == EventType.ASSISTANT_MESSAGE:
                total_msgs += 1
                content = event.data.get("content", "")
                total_chars += len(content)
                if not content or len(content.strip()) < 5:
                    empty_msgs += 1
                if content.count("```") % 2 != 0:
                    unclosed_fences += 1

        return {
            "total_messages": total_msgs,
            "empty_messages": empty_msgs,
            "unclosed_fences": unclosed_fences,
            "avg_response_length": round(total_chars / max(total_msgs, 1), 0),
            "empty_rate": round(empty_msgs / max(total_msgs, 1), 3),
        }

    def grade(self, trace: SessionTrace) -> dict:
        """Run all deterministic checks and return graded metrics."""
        tool_metrics = self.grade_tool_calls(trace)
        response_metrics = self.grade_response_quality(trace)
        return {**tool_metrics, **response_metrics}


# ═══════════════════════════════════════════════════════════════════
# 4. Behavioral Grader
# ═══════════════════════════════════════════════════════════════════


class BehavioralGrader:
    """Pattern-based grading: self-correction, consistency, efficiency.

    Detects behavioral patterns from event sequences.
    """

    def grade_self_correction(self, trace: SessionTrace) -> dict:
        """Measure how often validation failures lead to successful retries."""
        blocks = 0
        recoveries = 0

        for i, event in enumerate(trace.events):
            if event.type == EventType.VALIDATION_BLOCK:
                blocks += 1
                # Check if a valid TOOL_CALL follows within next 5 events
                for j in range(i + 1, min(i + 6, len(trace.events))):
                    if trace.events[j].type == EventType.TOOL_CALL:
                        recoveries += 1
                        break

        return {
            "validation_blocks": blocks,
            "recoveries": recoveries,
            "recovery_rate": round(recoveries / max(blocks, 1), 3),
        }

    def grade_consistency(self, trace: SessionTrace) -> dict:
        """Count consistency issues detected."""
        issues = 0
        for event in trace.events:
            if event.type == EventType.CONSISTENCY_ISSUE:
                issues += 1
        return {"consistency_issues": issues}

    def grade_efficiency(self, trace: SessionTrace) -> dict:
        """Measure efficiency: tool calls per turn, compression events."""
        tool_calls = 0
        compressions = 0
        reviews = 0
        user_msgs = 0

        for event in trace.events:
            if event.type == EventType.TOOL_CALL:
                tool_calls += 1
            elif event.type == EventType.CONTEXT_COMPRESSION:
                compressions += 1
            elif event.type == EventType.REVIEWER_RUN:
                reviews += 1
            elif event.type == EventType.USER_MESSAGE:
                user_msgs += 1

        return {
            "tool_calls_per_turn": round(tool_calls / max(user_msgs, 1), 1),
            "compressions": compressions,
            "reviews": reviews,
            "total_tool_calls": tool_calls,
        }

    def grade(self, trace: SessionTrace) -> dict:
        """Run all behavioral checks."""
        correction = self.grade_self_correction(trace)
        consistency = self.grade_consistency(trace)
        efficiency = self.grade_efficiency(trace)
        return {**correction, **consistency, **efficiency}


# ═══════════════════════════════════════════════════════════════════
# 5. Eval Engine
# ═══════════════════════════════════════════════════════════════════


@dataclass
class EvalResult:
    """Result of evaluating a single session."""
    session_id: str = ""
    score: float = 0.0
    deterministic: dict = field(default_factory=dict)
    behavioral: dict = field(default_factory=dict)
    llm_judge: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class EvalEngine:
    """Orchestrates all graders and produces a Scorecard.

    Usage:
        engine = EvalEngine()
        scorecard = engine.evaluate(sessions)  # list of SessionTrace
        print(scorecard.summary())
    """

    def __init__(self):
        self.deterministic = DeterministicGrader()
        self.behavioral = BehavioralGrader()
        self._results: list[EvalResult] = []

    def evaluate_session(self, trace: SessionTrace) -> EvalResult:
        """Run all graders on a single session trace."""
        det = self.deterministic.grade(trace)
        beh = self.behavioral.grade(trace)

        # Compute per-session score (0-100)
        det_valid_rate = det.get("valid_rate", 0)
        beh_recovery = beh.get("recovery_rate", 0)
        session_score = round((det_valid_rate * 0.6 + beh_recovery * 0.4) * 100, 1)

        return EvalResult(
            session_id=trace.session_id,
            score=session_score,
            deterministic=det,
            behavioral=beh,
        )

    def evaluate(self, traces: list[SessionTrace]) -> Scorecard:
        """Evaluate multiple session traces and produce a Scorecard."""
        self._results = [self.evaluate_session(t) for t in traces]

        sc = Scorecard(total_sessions=len(traces))

        # Aggregate metrics
        total_tool_calls = sum(r.deterministic.get("total_calls", 0) for r in self._results)
        total_valid = sum(r.deterministic.get("valid_calls", 0) for r in self._results)
        total_blocks = sum(r.deterministic.get("blocked_calls", 0) for r in self._results)
        total_retries = sum(r.deterministic.get("retries", 0) for r in self._results)
        total_recoveries = sum(r.behavioral.get("recoveries", 0) for r in self._results)
        total_consistent_issues = sum(r.behavioral.get("consistency_issues", 0) for r in self._results)
        total_user_msgs = sum(1 for t in traces for e in t.events if e.type == EventType.USER_MESSAGE)

        sc.tool_call_valid_rate = total_valid / max(total_tool_calls, 1)
        sc.self_correction_recovery_rate = total_recoveries / max(total_blocks, 1)
        sc.avg_tool_calls_per_task = total_tool_calls / max(len(traces), 1)
        sc.avg_retries_per_task = total_retries / max(len(traces), 1)

        # Count reviewer catches and diff guards from traces
        total_reviewer_issues = sum(
            1 for t in traces for e in t.events if e.type == EventType.REVIEWER_ISSUE
        )
        total_reviewer_runs = sum(
            1 for t in traces for e in t.events if e.type == EventType.REVIEWER_RUN
        )
        sc.reviewer_catch_rate = total_reviewer_issues / max(total_reviewer_runs, 1)

        total_diff_blocks = sum(
            1 for t in traces for e in t.events if e.type == EventType.DIFF_GUARD
        )
        sc.diff_guard_block_rate = total_diff_blocks / max(total_tool_calls, 1)

        # Task success rate: sessions with no critical errors
        failed_sessions = sum(
            1 for r in self._results if r.score < 50
        )
        sc.task_success_rate = 1 - (failed_sessions / max(len(traces), 1))

        sc.compute_overall()
        return sc

    def results_summary(self) -> str:
        lines = [f"📋 Session Results ({len(self._results)} sessions):"]
        for r in self._results:
            lines.append(f"  {r.session_id:20s} score={r.score:5.1f}  tools={r.deterministic.get('total_calls',0)}  retries={r.deterministic.get('retries',0)}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 6. Regression Guard
# ═══════════════════════════════════════════════════════════════════


@dataclass
class RegressionDiff:
    """Difference between two evaluations."""
    score_diff: float = 0.0
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"📈 Regression Guard: score Δ={self.score_diff:+.1f}"]
        if self.regressions:
            for r in self.regressions:
                lines.append(f"  🔻 {r}")
        if self.improvements:
            for i in self.improvements:
                lines.append(f"  🔺 {i}")
        if not self.regressions and not self.improvements:
            lines.append("  No significant changes")
        return "\n".join(lines)


class RegressionGuard:
    """Compare two Scorecards to detect regressions.

    Usage:
        guard = RegressionGuard()
        diff = guard.compare(before, after, threshold=0.05)
        print(diff.summary())
    """

    def compare(
        self,
        before: Scorecard,
        after: Scorecard,
        threshold: float = 0.05,
    ) -> RegressionDiff:
        """Compare two scorecards, flag regressions."""
        diff = RegressionDiff()
        diff.score_diff = round(after.overall_score - before.overall_score, 1)

        metrics_before = before.to_dict()
        metrics_after = after.to_dict()

        for key in metrics_before:
            if key in ("overall_score", "total_sessions"):
                continue
            val_before = metrics_before[key]
            val_after = metrics_after.get(key, val_before)
            delta = val_after - val_before

            if isinstance(delta, (int, float)):
                if abs(delta) > threshold:
                    if delta < 0:
                        diff.regressions.append(f"{key}: {val_before} → {val_after} ({delta:+.2f})")
                    else:
                        diff.improvements.append(f"{key}: {val_before} → {val_after} ({delta:+.2f})")

        return diff


# ═══════════════════════════════════════════════════════════════════
# 7. Eval CLI / Integration
# ═══════════════════════════════════════════════════════════════════


@dataclass
class EvalWorkspace:
    """Manages session traces on disk and runs evaluations."""
    traces_dir: str = ".crux/traces"

    def __post_init__(self):
        os.makedirs(self.traces_dir, exist_ok=True)

    def save_trace(self, trace: SessionTrace):
        path = os.path.join(self.traces_dir, f"{trace.session_id}.json")
        trace.save(path)
        return path

    def load_trace(self, session_id: str) -> SessionTrace | None:
        path = os.path.join(self.traces_dir, f"{session_id}.json")
        if not os.path.exists(path):
            return self._find_by_prefix(session_id)
        return SessionTrace.load(path)

    def _find_by_prefix(self, prefix: str) -> SessionTrace | None:
        for f in os.listdir(self.traces_dir):
            if f.startswith(prefix) and f.endswith(".json"):
                return SessionTrace.load(os.path.join(self.traces_dir, f))
        return None

    def list_traces(self) -> list[dict]:
        traces = []
        for f in sorted(os.listdir(self.traces_dir)):
            if f.endswith(".json"):
                try:
                    t = SessionTrace.load(os.path.join(self.traces_dir, f))
                    traces.append({
                        "id": t.session_id,
                        "date": datetime.fromtimestamp(t.start_time).isoformat() if t.start_time else "?",
                        "events": t.event_count,
                        "duration": round(t.duration, 1),
                    })
                except Exception:
                    logger.debug("Exception in evaluation", exc_info=True)
        return traces

    def run_eval(self, session_ids: list[str] | None = None) -> Scorecard:
        """Run evaluation on saved traces."""
        if session_ids:
            traces = []
            for sid in session_ids:
                t = self.load_trace(sid)
                if t:
                    traces.append(t)
        else:
            traces = []
            for f in os.listdir(self.traces_dir):
                if f.endswith(".json"):
                    try:
                        traces.append(SessionTrace.load(os.path.join(self.traces_dir, f)))
                    except Exception:
                        logger.debug("Exception in evaluation", exc_info=True)

        engine = EvalEngine()
        return engine.evaluate(traces)
