# core/field_arena.py
"""P13: Reality Gap Closure / Field Arena.

Bridges the gap between benchmark tests and real-world usage.

Three subsystems:
1. FieldRecorder — captures real user sessions for replay
2. FieldReplayRunner — replays captured sessions through the current CRUX
3. FieldArena — orchestrates benchmark vs field comparison + dual release gate
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from core.benchmark.scorer import BenchmarkScorecard, ReleaseDecision, ReleaseGateResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 1. FieldRecorder — captures real sessions
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FieldTurn:
    """A single user-assistant turn recorded from a real session."""
    user_message: str = ""
    assistant_response: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    duration_ms: float = 0.0
    success: bool = True


@dataclass
class FieldSession:
    """A complete real-user session recording."""
    id: str = ""
    source: str = "manual"  # "manual", "trace", "telemetry"
    created_at: float = 0.0
    tags: list[str] = field(default_factory=list)
    turns: list[FieldTurn] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def total_turns(self) -> int:
        return len(self.turns)

    @property
    def total_duration_ms(self) -> float:
        return sum(t.duration_ms for t in self.turns)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "created_at": self.created_at,
            "tags": self.tags,
            "total_turns": self.total_turns,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "turns": [
                {
                    "user_message": t.user_message[:500],
                    "assistant_response": (t.assistant_response or "")[:500],
                    "tool_calls": t.tool_calls[:5],
                    "success": t.success,
                    "duration_ms": round(t.duration_ms, 1),
                }
                for t in self.turns
            ],
            "metadata": self.metadata,
        }


class FieldRecorder:
    """Records real user sessions for later replay and regression testing.

    Usage:
        recorder = FieldRecorder()
        session = recorder.new_session(tags=["debug", "auth"])
        session.turns.append(FieldTurn(user_message="read auth.py", ...))
        recorder.save(session)
    """

    def __init__(self, storage_dir: str = ".crux/field_sessions"):
        self.storage_dir = storage_dir
        self._current_session: FieldSession | None = None

    def new_session(self, source: str = "manual", tags: list[str] | None = None) -> FieldSession:
        """Start a new field session recording."""
        session = FieldSession(
            id=str(uuid.uuid4())[:8],
            source=source,
            created_at=time.time(),
            tags=tags or [],
        )
        self._current_session = session
        return session

    def record_turn(
        self,
        user_message: str,
        assistant_response: str = "",
        tool_calls: list[dict] | None = None,
        tool_results: list[dict] | None = None,
        duration_ms: float = 0.0,
        success: bool = True,
    ):
        """Record a turn in the current session."""
        if self._current_session is None:
            self.new_session()
        self._current_session.turns.append(FieldTurn(
            user_message=user_message,
            assistant_response=assistant_response,
            tool_calls=tool_calls or [],
            tool_results=tool_results or [],
            duration_ms=duration_ms,
            success=success,
        ))

    def finish_session(self) -> FieldSession | None:
        """Finish and return the current session."""
        session = self._current_session
        self._current_session = None
        return session

    def save(self, session: FieldSession) -> str:
        """Save a field session to disk."""
        os.makedirs(self.storage_dir, exist_ok=True)
        path = os.path.join(self.storage_dir, f"{session.id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        return path

    def load(self, session_id: str) -> FieldSession | None:
        """Load a field session from disk."""
        path = os.path.join(self.storage_dir, f"{session_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        session = FieldSession(
            id=data.get("id", session_id),
            source=data.get("source", "unknown"),
            created_at=data.get("created_at", 0.0),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
        for td in data.get("turns", []):
            session.turns.append(FieldTurn(
                user_message=td.get("user_message", ""),
                assistant_response=td.get("assistant_response", ""),
                tool_calls=td.get("tool_calls", []),
                tool_results=td.get("tool_results", []),
                duration_ms=td.get("duration_ms", 0.0),
                success=td.get("success", True),
            ))
        return session

    def list_sessions(self) -> list[dict]:
        """List all recorded field sessions."""
        if not os.path.exists(self.storage_dir):
            return []
        sessions = []
        for fname in sorted(os.listdir(self.storage_dir)):
            if not fname.endswith(".json"):
                continue
            try:
                path = os.path.join(self.storage_dir, fname)
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "id": data.get("id", fname.replace(".json", "")),
                    "source": data.get("source", "?"),
                    "turns": data.get("total_turns", 0),
                    "date": datetime.fromtimestamp(data.get("created_at", 0)).isoformat() if data.get("created_at") else "?",
                    "tags": data.get("tags", []),
                })
            except Exception:
                import logging; logging.getLogger('crux').debug('silent except', exc_info=True)
        return sessions


# ═══════════════════════════════════════════════════════════════════
# 2. FieldReplayRunner — replays sessions against CRUX
# ═══════════════════════════════════════════════════════════════════


LLMCallback = Callable[[str], str]
"""Callback: (user_message) -> assistant_response"""


@dataclass
class ReplayTurnResult:
    """Result of replaying a single field turn."""
    turn_index: int = 0
    user_message: str = ""
    original_response: str = ""
    replayed_response: str = ""
    match: bool = False
    similarity: float = 0.0
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "turn_index": self.turn_index,
            "match": self.match,
            "similarity": round(self.similarity, 3),
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class ReplaySessionResult:
    """Result of replaying an entire field session."""
    session_id: str = ""
    total_turns: int = 0
    matched_turns: int = 0
    match_rate: float = 0.0
    avg_similarity: float = 0.0
    total_duration_ms: float = 0.0
    turn_results: list[ReplayTurnResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return round(self.matched_turns / max(self.total_turns, 1) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "total_turns": self.total_turns,
            "matched_turns": self.matched_turns,
            "match_rate": self.pass_rate,
            "avg_similarity": round(self.avg_similarity, 3),
            "total_duration_ms": round(self.total_duration_ms, 1),
            "turns": [t.to_dict() for t in self.turn_results],
        }


class FieldReplayRunner:
    """Replays captured field sessions to measure real-world performance.

    Usage:
        runner = FieldReplayRunner(llm_callback=my_llm)
        result = runner.replay_session(session)
        print(f"Field match rate: {result.pass_rate}%")
    """

    def __init__(self, llm_callback: LLMCallback | None = None):
        self.llm_callback = llm_callback

    def replay_turn(self, turn: FieldTurn) -> ReplayTurnResult:
        """Replay a single field turn and compare responses."""
        result = ReplayTurnResult(
            turn_index=0,
            user_message=turn.user_message[:200],
            original_response=turn.assistant_response or "",
        )

        start = time.time()

        if self.llm_callback:
            try:
                replayed = self.llm_callback(turn.user_message)
                result.replayed_response = replayed
            except Exception as e:
                result.replayed_response = f"[replay error: {e}]"
        else:
            result.replayed_response = "(no LLM callback)"

        result.duration_ms = (time.time() - start) * 1000

        # Compare responses
        if result.original_response and result.replayed_response:
            result.similarity = self._text_similarity(
                result.original_response,
                result.replayed_response,
            )
            result.match = result.similarity >= 0.5
        elif not result.original_response and not result.replayed_response:
            result.match = True  # both empty

        return result

    def replay_session(self, session: FieldSession) -> ReplaySessionResult:
        """Replay all turns in a field session."""
        start = time.time()
        session_result = ReplaySessionResult(
            session_id=session.id,
            total_turns=session.total_turns,
        )

        for i, turn in enumerate(session.turns):
            turn_result = self.replay_turn(turn)
            turn_result.turn_index = i
            session_result.turn_results.append(turn_result)
            if turn_result.match:
                session_result.matched_turns += 1
            session_result.avg_similarity += turn_result.similarity

        if session_result.total_turns > 0:
            session_result.avg_similarity = round(
                session_result.avg_similarity / session_result.total_turns, 3
            )

        session_result.total_duration_ms = (time.time() - start) * 1000
        return session_result

    def replay_all(self, sessions: list[FieldSession]) -> list[ReplaySessionResult]:
        """Replay multiple field sessions."""
        return [self.replay_session(s) for s in sessions]

    def _text_similarity(self, a: str, b: str) -> float:
        """Simple text similarity based on word overlap."""
        if not a or not b:
            return 0.0
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)


# ═══════════════════════════════════════════════════════════════════
# 3. FieldArena — orchestrator
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FieldScorecard:
    """Combined scorecard from benchmark + field replay."""
    benchmark_scorecard: BenchmarkScorecard | None = None
    field_results: list[ReplaySessionResult] = field(default_factory=list)
    overall_field_pass_rate: float = 0.0
    overall_score: float = 0.0
    field_weight: float = 0.3  # weight of field vs benchmark in overall

    def compute(self):
        """Compute combined score."""
        # Field score
        if self.field_results:
            total_turns = sum(r.total_turns for r in self.field_results)
            matched_turns = sum(r.matched_turns for r in self.field_results)
            self.overall_field_pass_rate = round(
                matched_turns / max(total_turns, 1) * 100, 1
            )
        else:
            self.overall_field_pass_rate = 0.0

        # Combined overall
        bench_score = self.benchmark_scorecard.overall_score if self.benchmark_scorecard else 0.0
        self.overall_score = round(
            bench_score * (1 - self.field_weight) + self.overall_field_pass_rate * self.field_weight,
            1,
        )

    def summary(self) -> str:
        lines = [
            "🏟 Field Arena Scorecard",
            f"   Benchmark: {self.benchmark_scorecard.overall_score}/100" if self.benchmark_scorecard else "",
            f"   Field replay: {self.overall_field_pass_rate}% pass rate",
            f"   Combined: {self.overall_score}/100",
            "",
        ]
        if self.field_results:
            lines.append("   Field sessions:")
            for r in self.field_results:
                bar = "█" * int(r.pass_rate / 10) + "░" * (10 - int(r.pass_rate / 10))
                lines.append(f"     {r.session_id:20s} {bar} {r.pass_rate:5.1f}% ({r.matched_turns}/{r.total_turns})")
        return "\n".join([l for l in lines if l])


class FieldArena:
    """Orchestrates benchmark vs field comparison + dual release gate.

    Usage:
        arena = FieldArena()
        arena.record_session(session)
        arena.record_session(session2)
        sc = arena.evaluate(benchmark_scorecard)
        gate = arena.release_gate(sc)
    """

    def __init__(self, storage_dir: str = ".crux/field_sessions"):
        self.recorder = FieldRecorder(storage_dir=storage_dir)
        self.replay_runner = FieldReplayRunner()
        self._field_sessions: list[FieldSession] = []

    def add_session(self, session: FieldSession):
        """Add a field session for evaluation."""
        self._field_sessions.append(session)
        self.recorder.save(session)

    def load_sessions(self) -> list[FieldSession]:
        """Load all saved field sessions."""
        sessions = []
        for s in self.recorder.list_sessions():
            session = self.recorder.load(s["id"])
            if session:
                sessions.append(session)
        self._field_sessions = sessions
        return sessions

    def set_llm_callback(self, callback: LLMCallback):
        """Set the LLM callback for replay."""
        self.replay_runner.llm_callback = callback

    def evaluate(
        self,
        benchmark_scorecard: BenchmarkScorecard,
        field_weight: float = 0.3,
    ) -> FieldScorecard:
        """Run field replay and combine with benchmark score."""
        if not self._field_sessions:
            self.load_sessions()

        # Run replay on all field sessions
        field_results = self.replay_runner.replay_all(self._field_sessions)

        # Build combined scorecard
        sc = FieldScorecard(
            benchmark_scorecard=benchmark_scorecard,
            field_results=field_results,
            field_weight=field_weight,
        )
        sc.compute()
        return sc

    def release_gate(
        self,
        field_scorecard: FieldScorecard,
        min_benchmark_score: float = 70.0,
        min_field_pass_rate: float = 60.0,
    ) -> ReleaseGateResult:
        """Dual release gate: benchmark + field must both pass."""
        result = ReleaseGateResult()
        reasons = []

        # Benchmark check
        bench = field_scorecard.benchmark_scorecard
        if bench and bench.overall_score < min_benchmark_score:
            result.blocks.append(
                f"Benchmark score {bench.overall_score} < {min_benchmark_score}"
            )
        else:
            result.reasons.append(
                f"Benchmark score {bench.overall_score if bench else 'N/A'} >= {min_benchmark_score}"
            )

        # Field check
        if field_scorecard.overall_field_pass_rate < min_field_pass_rate:
            result.blocks.append(
                f"Field pass rate {field_scorecard.overall_field_pass_rate}% < {min_field_pass_rate}%"
            )
        else:
            result.reasons.append(
                f"Field pass rate {field_scorecard.overall_field_pass_rate}% >= {min_field_pass_rate}%"
            )

        # Combined check
        if field_scorecard.overall_score < (min_benchmark_score + min_field_pass_rate) / 2:
            result.warnings.append(
                f"Combined score {field_scorecard.overall_score} below threshold"
            )

        # Decision
        if result.blocks:
            result.decision = ReleaseDecision.BLOCK
        elif result.warnings:
            result.decision = ReleaseDecision.WARN
        else:
            result.decision = ReleaseDecision.PASS

        return result

    def compare(
        self,
        benchmark_before: BenchmarkScorecard,
        benchmark_after: BenchmarkScorecard,
    ) -> str:
        """A/B compare two benchmark runs (e.g., before/after change)."""
        lines = [
            "📊 Field Arena A/B Comparison:",
            f"  {'Metric':30s} {'Before':12s} {'After':12s} {'Δ':10s}",
            f"  {'-'*30} {'-'*12} {'-'*12} {'-'*10}",
        ]
        metrics = [
            ("Overall Score", benchmark_before.overall_score, benchmark_after.overall_score),
            ("Pass Rate", benchmark_before.pass_rate, benchmark_after.pass_rate),
        ]
        # Add dimension scores
        dims_before = {d.name: d for d in benchmark_before.dimensions}
        dims_after = {d.name: d for d in benchmark_after.dimensions}
        for name in set(list(dims_before.keys()) + list(dims_after.keys())):
            db = dims_before.get(name)
            da = dims_after.get(name)
            before_val = db.avg_score if db else 0
            after_val = da.avg_score if da else 0
            metrics.append((f"  {name} score", before_val, after_val))

        for name, before, after in metrics:
            delta = after - before
            arrow = "🔺" if delta > 1 else "🔻" if delta < -1 else "➡"
            lines.append(f"  {name:30s} {before:<12.1f} {after:<12.1f} {arrow} {delta:+7.1f}")

        return "\n".join(lines)
