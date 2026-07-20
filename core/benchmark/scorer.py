# core/benchmark/scorer.py
"""BenchmarkScorer — multi-dimension scoring + Release Gate.

Takes raw BenchmarkResults and produces:
- Multi-dimension scores per category
- Trends over multiple runs (regression detection)
- Release Gate decisions (pass / warn / block)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.benchmark.runner import BenchmarkResult

logger = logging.getLogger(__name__)


# ── Score dimensions ────────────────────────────────────────────────


DIMENSION_WEIGHTS = {
    "code_gen": 0.25,
    "debug": 0.25,
    "qa": 0.10,
    "tool_use": 0.20,
    "multi_step": 0.20,
}


@dataclass
class DimensionScore:
    """Score for a single capability dimension."""

    name: str = ""
    pass_rate: float = 0.0
    avg_score: float = 0.0
    total_tasks: int = 0
    passed: int = 0
    weight: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "total_tasks": self.total_tasks,
            "passed": self.passed,
            "weight": self.weight,
        }


@dataclass
class BenchmarkScorecard:
    """Full scorecard from a benchmark run."""

    suite_name: str = ""
    timestamp: float = 0.0
    overall_score: float = 0.0
    pass_rate: float = 0.0
    dimensions: list[DimensionScore] = field(default_factory=list)
    raw: BenchmarkResult | None = None
    previous_score: float | None = None
    score_delta: float = 0.0

    def compute(self, result: BenchmarkResult) -> BenchmarkScorecard:
        """Compute multi-dimension scores from a benchmark result."""
        self.suite_name = result.suite_name
        self.timestamp = result.timestamp
        self.pass_rate = result.pass_rate
        self.raw = result

        by_cat = result.by_category()
        weighted_sum = 0.0
        total_weight = 0.0

        for cat, data in sorted(by_cat.items()):
            weight = DIMENSION_WEIGHTS.get(cat, 0.10)
            ds = DimensionScore(
                name=cat,
                pass_rate=data["pass_rate"],
                avg_score=data["avg_score"],
                total_tasks=data["total"],
                passed=data["passed"],
                weight=weight,
            )
            self.dimensions.append(ds)
            weighted_sum += ds.avg_score * weight
            total_weight += weight

        self.overall_score = round(weighted_sum / max(total_weight, 0.01), 1)

        # Delta from previous
        if self.previous_score is not None:
            self.score_delta = round(self.overall_score - self.previous_score, 1)

        return self

    def to_dict(self) -> dict:
        return {
            "suite_name": self.suite_name,
            "timestamp": self.timestamp,
            "overall_score": self.overall_score,
            "pass_rate": self.pass_rate,
            "score_delta": self.score_delta,
            "dimensions": [d.to_dict() for d in self.dimensions],
        }

    def summary(self) -> str:
        lines = [
            f"🏆 Scorecard: {self.suite_name}",
            f"   Overall: {self.overall_score}/100",
            f"   Pass rate: {self.pass_rate}%",
        ]
        if self.previous_score is not None:
            arrow = "🔺" if self.score_delta > 0 else "🔻" if self.score_delta < 0 else "➡"
            lines.append(f"   vs previous: {arrow} {self.score_delta:+.1f}")
        lines.append("")
        for d in self.dimensions:
            bar = "█" * int(d.pass_rate / 10) + "░" * (10 - int(d.pass_rate / 10))
            lines.append(f"  {d.name:15s} {bar} {d.pass_rate:5.1f}% score={d.avg_score:5.1f} (w={d.weight:.0%})")
        return "\n".join(lines)

    def trends(self, history: list[BenchmarkScorecard]) -> str:
        """Generate trend analysis from historical scorecards."""
        if len(history) < 2:
            return "Not enough data for trend analysis"

        lines = ["📈 Trends:"]
        for i, h in enumerate(history):
            lines.append(f"  Run {i + 1}: {h.overall_score}/100 ({h.pass_rate}%)")
        if len(history) >= 2:
            first = history[0].overall_score
            last = history[-1].overall_score
            delta = last - first
            arrow = "🔺" if delta > 0 else "🔻" if delta < 0 else "➡"
            lines.append(f"  Overall: {first} → {last} ({arrow} {delta:+.1f})")
        return "\n".join(lines)


# ── Release Gate ────────────────────────────────────────────────────


class ReleaseDecision(str):
    """Decision type for release gate."""

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class ReleaseGateResult:
    """Result of a release gate evaluation."""

    decision: str = ReleaseDecision.PASS
    scorecard: BenchmarkScorecard | None = None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)

    @property
    def can_release(self) -> bool:
        return self.decision != ReleaseDecision.BLOCK

    def summary(self) -> str:
        icon = {"pass": "✅", "warn": "⚠", "block": "❌"}.get(self.decision, "?")
        lines = [f"{icon} Release Gate: {self.decision.upper()}"]
        if self.reasons:
            lines.append(f"  Score: {self.scorecard.overall_score}/100" if self.scorecard else "")
        if self.blocks:
            for b in self.blocks:
                lines.append(f"  🚫 {b}")
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


class ReleaseGate:
    """Evaluates whether a benchmark result meets the release threshold.

    Configurable thresholds per dimension.
    Compares against previous run to detect regressions.
    """

    def __init__(
        self,
        min_overall_score: float = 70.0,
        min_per_dimension_score: float = 50.0,
        max_regression_delta: float = -5.0,
        regression_window: int = 3,
    ):
        self.min_overall_score = min_overall_score
        self.min_per_dimension_score = min_per_dimension_score
        self.max_regression_delta = max_regression_delta
        self.regression_window = regression_window

    def evaluate(
        self,
        scorecard: BenchmarkScorecard,
        history: list[BenchmarkScorecard] | None = None,
    ) -> ReleaseGateResult:
        """Evaluate whether the benchmark result passes the release gate."""
        result = ReleaseGateResult(scorecard=scorecard)

        # 1. Overall score check
        if scorecard.overall_score < self.min_overall_score:
            result.blocks.append(f"Overall score {scorecard.overall_score} < {self.min_overall_score}")
        else:
            result.reasons.append(f"Overall score {scorecard.overall_score} >= {self.min_overall_score}")

        # 2. Per-dimension minimum check
        for d in scorecard.dimensions:
            if d.avg_score < self.min_per_dimension_score:
                result.blocks.append(f"Dimension '{d.name}' score {d.avg_score} < min {self.min_per_dimension_score}")

        # 3. Regression check against history
        if history and len(history) >= 1:
            prev = history[-1]
            delta = scorecard.overall_score - prev.overall_score
            if delta < self.max_regression_delta:
                result.blocks.append(
                    f"Score regression: {prev.overall_score} → {scorecard.overall_score} ({delta:+.1f})"
                )
            elif delta < 0:
                result.warnings.append(
                    f"Slight score drop: {prev.overall_score} → {scorecard.overall_score} ({delta:+.1f})"
                )
            else:
                result.reasons.append(
                    f"Score improved: {prev.overall_score} → {scorecard.overall_score} ({delta:+.1f})"
                )

        # 4. Determine decision
        if result.blocks:
            result.decision = ReleaseDecision.BLOCK
        elif result.warnings:
            result.decision = ReleaseDecision.WARN
        else:
            result.decision = ReleaseDecision.PASS

        return result


# ── History manager ─────────────────────────────────────────────────


class BenchmarkHistory:
    """Manages historical benchmark results for trend analysis and regression detection."""

    def __init__(self, history_dir: str = ".crux/benchmark_history"):
        self.history_dir = history_dir

    def save(self, scorecard: BenchmarkScorecard):
        """Save a scorecard to history."""
        os.makedirs(self.history_dir, exist_ok=True)
        timestamp = datetime.fromtimestamp(scorecard.timestamp).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.history_dir, f"{scorecard.suite_name}_{timestamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(scorecard.to_dict(), f, indent=2, ensure_ascii=False)

    def load_all(self, suite_name: str | None = None) -> list[BenchmarkScorecard]:
        """Load all historical scorecards, optionally filtered by suite."""
        if not os.path.exists(self.history_dir):
            return []

        history = []
        for fname in sorted(os.listdir(self.history_dir)):
            if not fname.endswith(".json"):
                continue
            if suite_name and not fname.startswith(suite_name):
                continue
            try:
                with open(os.path.join(self.history_dir, fname), encoding="utf-8") as f:
                    data = json.load(f)
                sc = BenchmarkScorecard(
                    suite_name=data.get("suite_name", ""),
                    timestamp=data.get("timestamp", 0.0),
                    overall_score=data.get("overall_score", 0.0),
                    pass_rate=data.get("pass_rate", 0.0),
                )
                for dd in data.get("dimensions", []):
                    sc.dimensions.append(DimensionScore(**dd))
                history.append(sc)
            except Exception:
                import logging

                logging.getLogger(__name__).debug("silent except", exc_info=True)
        return history

    def last(self, suite_name: str) -> BenchmarkScorecard | None:
        """Get the most recent scorecard for a suite."""
        history = self.load_all(suite_name)
        return history[-1] if history else None
