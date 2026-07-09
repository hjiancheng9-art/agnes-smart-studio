Phase 7 定位
Phase 7 = Benchmark Arena / Learning Patch Release Gate

目标：
任何 PolicyAdapter / LearningLoop 生成的自动学习补丁，
都不能直接全量生效。
必须经过：

Patch → Arena Sandbox → RouterReplay → IntelligenceEval → Regression Gate → GradualRelease → Full Apply
1. Arena 核心数据结构

新增目录：

core/arena/
  __init__.py
  schemas.py
  benchmark_arena.py
  arena_gate.py
  patch_runner.py
  report_store.py
  release_bridge.py
core/arena/schemas.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import time
import uuid


class ArenaDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


class PatchRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PatchTarget(str, Enum):
    ROUTER_SIGNAL = "router_signal"
    POLICY_CONFIG = "policy_config"
    PLAN_CONFIG = "plan_config"
    REPAIR_CONFIG = "repair_config"
    PROMPT_TEMPLATE = "prompt_template"
    UNKNOWN = "unknown"


@dataclass
class ArenaVariant:
    """
    一次待验证的学习补丁。
    来源可以是 FailureAnalyzer / PolicyAdapter / 人工实验。
    """
    id: str
    name: str
    patch: dict[str, Any]
    target: PatchTarget = PatchTarget.UNKNOWN
    risk: PatchRisk = PatchRisk.MEDIUM
    source: str = "policy_adapter"
    source_record_ids: list[str] = field(default_factory=list)
    description: str = ""
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        patch: dict[str, Any],
        target: PatchTarget | str = PatchTarget.UNKNOWN,
        risk: PatchRisk | str = PatchRisk.MEDIUM,
        source: str = "policy_adapter",
        source_record_ids: list[str] | None = None,
        description: str = "",
    ) -> "ArenaVariant":
        return cls(
            id=f"var_{uuid.uuid4().hex[:12]}",
            name=name,
            patch=patch,
            target=PatchTarget(target),
            risk=PatchRisk(risk),
            source=source,
            source_record_ids=source_record_ids or [],
            description=description,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["target"] = self.target.value
        data["risk"] = self.risk.value
        return data


@dataclass
class ArenaGateConfig:
    """
    Arena 发布门槛。
    """
    min_router_acceptable_accuracy: float = 0.95
    min_router_full_accuracy: float = 0.90
    min_safe_recall: float = 1.00
    min_critical_recall: float = 0.95
    max_underroute_rate: float = 0.03

    min_eval_pass_rate: float = 0.80
    min_eval_avg_score: float = 0.70

    max_router_regressions: int = 0
    max_eval_regressions: int = 1

    require_no_safe_regression: bool = True
    require_no_critical_regression: bool = True


@dataclass
class ArenaMetricSnapshot:
    router_exact_accuracy: float = 0.0
    router_acceptable_accuracy: float = 0.0
    router_full_accuracy: float = 0.0
    safe_recall: float = 0.0
    critical_recall: float = 0.0
    underroute_rate: float = 0.0

    eval_pass_rate: float = 0.0
    eval_avg_score: float = 0.0

    router_failure_ids: list[str] = field(default_factory=list)
    eval_failure_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArenaReport:
    id: str
    variant: ArenaVariant
    decision: ArenaDecision
    baseline: ArenaMetricSnapshot
    candidate: ArenaMetricSnapshot
    reasons: list[str]
    router_report: dict[str, Any]
    eval_report: dict[str, Any]
    started_at: float
    ended_at: float
    duration_sec: float

    @classmethod
    def create(
        cls,
        *,
        variant: ArenaVariant,
        decision: ArenaDecision,
        baseline: ArenaMetricSnapshot,
        candidate: ArenaMetricSnapshot,
        reasons: list[str],
        router_report: dict[str, Any],
        eval_report: dict[str, Any],
        started_at: float,
    ) -> "ArenaReport":
        ended = time.time()
        return cls(
            id=f"arena_{uuid.uuid4().hex[:12]}",
            variant=variant,
            decision=decision,
            baseline=baseline,
            candidate=candidate,
            reasons=reasons,
            router_report=router_report,
            eval_report=eval_report,
            started_at=started_at,
            ended_at=ended,
            duration_sec=round(ended - started_at, 3),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "variant": self.variant.to_dict(),
            "decision": self.decision.value,
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict(),
            "reasons": self.reasons,
            "router_report": self.router_report,
            "eval_report": self.eval_report,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_sec": self.duration_sec,
        }
2. 文件清单和职责
core/arena/schemas.py
- ArenaVariant / ArenaReport / ArenaGateConfig / MetricSnapshot

core/arena/patch_runner.py
- 对 PolicyAdapter 做 snapshot / apply_patch / restore
- 保证 Arena 运行不污染主策略

core/arena/arena_gate.py
- 对 RouterReplay + IntelligenceEval 结果做准入裁决

core/arena/benchmark_arena.py
- 主编排器：跑 baseline、跑 candidate、生成报告

core/arena/report_store.py
- SQLite 存储 Arena 报告

core/arena/release_bridge.py
- Arena 通过后交给 GradualRelease
- Arena 失败后标记 PolicyAdapter patch rejected
3. PatchRunner：隔离补丁运行
core/arena/patch_runner.py
Python
运行
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


class ArenaPatchRunner:
    """
    Arena 补丁沙箱。
    所有候选补丁必须在 snapshot 里运行，结束后 restore。
    """

    def __init__(self, policy_adapter: Any) -> None:
        self.policy_adapter = policy_adapter

    @asynccontextmanager
    async def applied(self, patch: dict[str, Any]) -> AsyncIterator[None]:
        snapshot = self.policy_adapter.snapshot()

        try:
            self.policy_adapter.apply_patch(
                patch,
                source="benchmark_arena",
                temporary=True,
            )
            yield

        finally:
            self.policy_adapter.restore(snapshot)

你的 PolicyAdapter 需要有这三个方法：

Python
运行
class PolicyAdapter:
    def snapshot(self) -> dict:
        ...

    def restore(self, snapshot: dict) -> None:
        ...

    def apply_patch(self, patch: dict, *, source: str, temporary: bool = False) -> None:
        ...

没有就直接补：

Python
运行
def snapshot(self) -> dict:
    return {
        "signal_weights": dict(self.signal_weights),
        "plan_config": dict(self.plan_config),
        "repair_config": dict(self.repair_config),
    }


def restore(self, snapshot: dict) -> None:
    self.signal_weights.clear()
    self.signal_weights.update(snapshot.get("signal_weights", {}))

    self.plan_config.clear()
    self.plan_config.update(snapshot.get("plan_config", {}))

    self.repair_config.clear()
    self.repair_config.update(snapshot.get("repair_config", {}))


def apply_patch(self, patch: dict, *, source: str = "manual", temporary: bool = False) -> None:
    for name, delta in patch.get("signal_weight_delta", {}).items():
        self.signal_weights[name] = self.signal_weights.get(name, 0.0) + float(delta)

    for key, value in patch.get("plan_config", {}).items():
        self.plan_config[key] = value

    for key, value in patch.get("repair_config", {}).items():
        self.repair_config[key] = value

    if not temporary:
        self.mark_applied(patch, source=source)
4. ArenaGate：裁决候选补丁
core/arena/arena_gate.py
Python
运行
from __future__ import annotations

from core.arena.schemas import (
    ArenaDecision,
    ArenaGateConfig,
    ArenaMetricSnapshot,
)


class ArenaGate:
    def __init__(self, config: ArenaGateConfig | None = None) -> None:
        self.config = config or ArenaGateConfig()

    def decide(
        self,
        *,
        baseline: ArenaMetricSnapshot,
        candidate: ArenaMetricSnapshot,
    ) -> tuple[ArenaDecision, list[str]]:
        reasons: list[str] = []
        c = self.config

        if candidate.router_acceptable_accuracy < c.min_router_acceptable_accuracy:
            reasons.append(
                f"router acceptable accuracy too low: "
                f"{candidate.router_acceptable_accuracy:.3f} < {c.min_router_acceptable_accuracy:.3f}"
            )

        if candidate.router_full_accuracy < c.min_router_full_accuracy:
            reasons.append(
                f"router full accuracy too low: "
                f"{candidate.router_full_accuracy:.3f} < {c.min_router_full_accuracy:.3f}"
            )

        if candidate.safe_recall < c.min_safe_recall:
            reasons.append(
                f"SAFE recall regression: {candidate.safe_recall:.3f} < {c.min_safe_recall:.3f}"
            )

        if candidate.critical_recall < c.min_critical_recall:
            reasons.append(
                f"critical recall too low: {candidate.critical_recall:.3f} < {c.min_critical_recall:.3f}"
            )

        if candidate.underroute_rate > c.max_underroute_rate:
            reasons.append(
                f"underroute rate too high: {candidate.underroute_rate:.3f} > {c.max_underroute_rate:.3f}"
            )

        if candidate.eval_pass_rate < c.min_eval_pass_rate:
            reasons.append(
                f"eval pass rate too low: {candidate.eval_pass_rate:.3f} < {c.min_eval_pass_rate:.3f}"
            )

        if candidate.eval_avg_score < c.min_eval_avg_score:
            reasons.append(
                f"eval avg score too low: {candidate.eval_avg_score:.3f} < {c.min_eval_avg_score:.3f}"
            )

        router_regressions = self._new_failures(
            baseline.router_failure_ids,
            candidate.router_failure_ids,
        )

        eval_regressions = self._new_failures(
            baseline.eval_failure_ids,
            candidate.eval_failure_ids,
        )

        if len(router_regressions) > c.max_router_regressions:
            reasons.append(
                f"router regressions too many: {len(router_regressions)} > {c.max_router_regressions}; "
                f"new={router_regressions}"
            )

        if len(eval_regressions) > c.max_eval_regressions:
            reasons.append(
                f"eval regressions too many: {len(eval_regressions)} > {c.max_eval_regressions}; "
                f"new={eval_regressions}"
            )

        if candidate.router_acceptable_accuracy < baseline.router_acceptable_accuracy - 0.02:
            reasons.append("router acceptable accuracy dropped by more than 2%")

        if candidate.eval_avg_score < baseline.eval_avg_score - 0.05:
            reasons.append("eval avg score dropped by more than 0.05")

        if reasons:
            return ArenaDecision.FAIL, reasons

        return ArenaDecision.PASS, ["candidate passed Arena gate"]

    def _new_failures(self, baseline_ids: list[str], candidate_ids: list[str]) -> list[str]:
        return sorted(set(candidate_ids) - set(baseline_ids))
5. BenchmarkArena 主编排器
core/arena/benchmark_arena.py
Python
运行
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.arena.arena_gate import ArenaGate
from core.arena.patch_runner import ArenaPatchRunner
from core.arena.schemas import (
    ArenaGateConfig,
    ArenaMetricSnapshot,
    ArenaReport,
    ArenaVariant,
)


class BenchmarkArena:
    def __init__(
        self,
        *,
        router_replay: Any,
        intelligence_eval: Any,
        policy_adapter: Any,
        report_store: Any | None = None,
        gate: ArenaGate | None = None,
        router_cases_path: str | Path = "data/router_golden_cases.jsonl",
        eval_cases_path: str | Path = "data/intelligence_eval_cases.jsonl",
    ) -> None:
        self.router_replay = router_replay
        self.intelligence_eval = intelligence_eval
        self.policy_adapter = policy_adapter
        self.patch_runner = ArenaPatchRunner(policy_adapter)
        self.report_store = report_store
        self.gate = gate or ArenaGate(ArenaGateConfig())
        self.router_cases_path = Path(router_cases_path)
        self.eval_cases_path = Path(eval_cases_path)

    async def run_variant(self, variant: ArenaVariant) -> ArenaReport:
        started = time.time()

        baseline = await self._run_snapshot()

        async with self.patch_runner.applied(variant.patch):
            candidate = await self._run_snapshot()

        decision, reasons = self.gate.decide(
            baseline=baseline["metrics"],
            candidate=candidate["metrics"],
        )

        report = ArenaReport.create(
            variant=variant,
            decision=decision,
            baseline=baseline["metrics"],
            candidate=candidate["metrics"],
            reasons=reasons,
            router_report=candidate["router_report"],
            eval_report=candidate["eval_report"],
            started_at=started,
        )

        if self.report_store:
            self.report_store.save(report)

        return report

    async def _run_snapshot(self) -> dict[str, Any]:
        router_report_obj = await self.router_replay.run_file(self.router_cases_path)
        eval_report_obj = await self.intelligence_eval.run_file(self.eval_cases_path)

        router_report = self._to_dict(router_report_obj)
        eval_report = self._to_dict(eval_report_obj)

        metrics = ArenaMetricSnapshot(
            router_exact_accuracy=float(router_report.get("exact_accuracy", 0.0)),
            router_acceptable_accuracy=float(router_report.get("acceptable_accuracy", 0.0)),
            router_full_accuracy=float(router_report.get("full_accuracy", 0.0)),
            safe_recall=float(router_report.get("safe_recall", 0.0)),
            critical_recall=float(router_report.get("critical_recall", 0.0)),
            underroute_rate=float(router_report.get("underroute_rate", 1.0)),

            eval_pass_rate=float(eval_report.get("pass_rate", 0.0)),
            eval_avg_score=float(eval_report.get("avg_score", 0.0)),

            router_failure_ids=self._failure_ids(router_report),
            eval_failure_ids=self._failure_ids(eval_report),
        )

        return {
            "metrics": metrics,
            "router_report": router_report,
            "eval_report": eval_report,
        }

    def _to_dict(self, obj: Any) -> dict[str, Any]:
        if isinstance(obj, dict):
            return obj

        if hasattr(obj, "to_dict"):
            return obj.to_dict()

        raise TypeError(f"Unsupported report object: {type(obj)!r}")

    def _failure_ids(self, report: dict[str, Any]) -> list[str]:
        out: list[str] = []

        for f in report.get("failures", []) or []:
            case_id = (
                f.get("case_id")
                or f.get("id")
                or f.get("eval_case_id")
            )
            if case_id:
                out.append(str(case_id))

        return sorted(out)
6. Arena 报告存储
core/arena/report_store.py
Python
运行
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.arena.schemas import ArenaReport


class ArenaReportStore:
    def __init__(self, db_path: str | Path = "data/benchmark_arena.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS arena_reports (
                    id TEXT PRIMARY KEY,
                    variant_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    target TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    duration_sec REAL NOT NULL,
                    created_at REAL NOT NULL,
                    report_json TEXT NOT NULL
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_arena_variant ON arena_reports(variant_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_arena_decision ON arena_reports(decision)")

    def save(self, report: ArenaReport) -> None:
        payload = report.to_dict()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO arena_reports
                (id, variant_id, decision, target, risk, duration_sec, created_at, report_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.variant.id,
                    report.decision.value,
                    report.variant.target.value,
                    report.variant.risk.value,
                    report.duration_sec,
                    report.started_at,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def get(self, report_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM arena_reports WHERE id = ?",
                (report_id,),
            ).fetchone()

        if not row:
            return None

        return json.loads(row[0])

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT report_json FROM arena_reports
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [json.loads(r[0]) for r in rows]
7. 与 GradualRelease + PolicyAdapter 集成

Phase 7 的关键：PolicyAdapter 不再直接 apply 高置信补丁，而是 submit 到 Arena。

集成协议

你现在的发布链改成：

FailureAnalyzer
  ↓
PolicyAdapter 生成 patch
  ↓
BenchmarkArena.run_variant()
  ↓
Arena PASS?
  ├─ yes → GradualRelease.create_release()
  └─ no  → PolicyAdapter.mark_rejected()
core/arena/release_bridge.py
Python
运行
from __future__ import annotations

from typing import Any

from core.arena.schemas import ArenaDecision, ArenaReport, ArenaVariant


class ArenaReleaseBridge:
    """
    Arena 与 GradualRelease / PolicyAdapter 的桥。
    """

    def __init__(
        self,
        *,
        arena: Any,
        gradual_release: Any,
        policy_adapter: Any,
    ) -> None:
        self.arena = arena
        self.gradual_release = gradual_release
        self.policy_adapter = policy_adapter

    async def validate_and_release(self, variant: ArenaVariant) -> dict[str, Any]:
        report: ArenaReport = await self.arena.run_variant(variant)

        if report.decision != ArenaDecision.PASS:
            self._mark_rejected(variant, report)
            return {
                "status": "rejected",
                "variant_id": variant.id,
                "arena_report_id": report.id,
                "reasons": report.reasons,
            }

        release = self._create_gradual_release(variant, report)
        self._mark_arena_passed(variant, report, release)

        return {
            "status": "released_to_canary",
            "variant_id": variant.id,
            "arena_report_id": report.id,
            "release_id": self._release_id(release),
            "reasons": report.reasons,
        }

    def _create_gradual_release(self, variant: ArenaVariant, report: ArenaReport) -> Any:
        """
        适配你已有的 GradualRelease。
        推荐 GradualRelease 暴露 create_release()。
        """
        if hasattr(self.gradual_release, "create_release"):
            return self.gradual_release.create_release(
                patch=variant.patch,
                source="benchmark_arena",
                metadata={
                    "variant_id": variant.id,
                    "arena_report_id": report.id,
                    "target": variant.target.value,
                    "risk": variant.risk.value,
                    "candidate_metrics": report.candidate.to_dict(),
                },
            )

        if hasattr(self.gradual_release, "submit"):
            return self.gradual_release.submit(
                variant.patch,
                metadata={
                    "variant_id": variant.id,
                    "arena_report_id": report.id,
                },
            )

        raise RuntimeError("GradualRelease must expose create_release() or submit()")

    def _mark_rejected(self, variant: ArenaVariant, report: ArenaReport) -> None:
        if hasattr(self.policy_adapter, "mark_rejected"):
            self.policy_adapter.mark_rejected(
                patch_id=variant.id,
                reason="arena_failed",
                metadata={
                    "arena_report_id": report.id,
                    "reasons": report.reasons,
                },
            )

    def _mark_arena_passed(self, variant: ArenaVariant, report: ArenaReport, release: Any) -> None:
        if hasattr(self.policy_adapter, "mark_arena_passed"):
            self.policy_adapter.mark_arena_passed(
                patch_id=variant.id,
                metadata={
                    "arena_report_id": report.id,
                    "release_id": self._release_id(release),
                },
            )

    def _release_id(self, release: Any) -> str | None:
        if isinstance(release, dict):
            return release.get("id") or release.get("release_id")

        return getattr(release, "id", None) or getattr(release, "release_id", None)
PolicyAdapter 要增加这几个方法
Python
运行
class PolicyAdapter:
    def submit_patch_to_arena(self, patch: dict, *, source_record_ids: list[str]) -> ArenaVariant:
        return ArenaVariant.create(
            name=patch.get("name", "learning_patch"),
            patch=patch,
            target=patch.get("target", "policy_config"),
            risk=patch.get("risk", "medium"),
            source="policy_adapter",
            source_record_ids=source_record_ids,
            description=patch.get("description", ""),
        )

    def mark_rejected(self, patch_id: str, reason: str, metadata: dict) -> None:
        # 写入你的学习补丁队列 / SQLite
        ...

    def mark_arena_passed(self, patch_id: str, metadata: dict) -> None:
        # 标记为 arena_passed，等待 GradualRelease canary
        ...

原来的自动应用逻辑改掉：

Python
运行
# 旧：不要这样
if diagnosis.confidence >= 0.7:
    policy_adapter.apply_patch(patch)

# 新：这样做
if diagnosis.confidence >= 0.7:
    variant = policy_adapter.submit_patch_to_arena(
        patch,
        source_record_ids=[diagnosis.record_id],
    )
    await arena_release_bridge.validate_and_release(variant)
8. 最小可落地版本

先不要做并发、不要做复杂实验矩阵。MVP 只做 1 个候选补丁跑完整 Arena。

MVP 文件
core/arena/schemas.py
core/arena/patch_runner.py
core/arena/arena_gate.py
core/arena/benchmark_arena.py
core/arena/release_bridge.py
tests/test_benchmark_arena.py

report_store.py 第二步再加。

tests/test_benchmark_arena.py
Python
运行
import pytest

from core.arena.benchmark_arena import BenchmarkArena
from core.arena.schemas import ArenaVariant, PatchTarget, PatchRisk


class FakeRouterReport:
    def __init__(self, acceptable=0.96, full=0.92, safe=1.0, critical=0.96, under=0.01):
        self.acceptable = acceptable
        self.full = full
        self.safe = safe
        self.critical = critical
        self.under = under

    def to_dict(self):
        return {
            "exact_accuracy": 0.85,
            "acceptable_accuracy": self.acceptable,
            "full_accuracy": self.full,
            "safe_recall": self.safe,
            "critical_recall": self.critical,
            "underroute_rate": self.under,
            "failures": [],
        }


class FakeEvalReport:
    def __init__(self, pass_rate=0.85, avg_score=0.75):
        self.pass_rate = pass_rate
        self.avg_score = avg_score

    def to_dict(self):
        return {
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "failures": [],
        }


class FakeRouterReplay:
    async def run_file(self, path):
        return FakeRouterReport()


class FakeIntelligenceEval:
    async def run_file(self, path):
        return FakeEvalReport()


class FakePolicyAdapter:
    def __init__(self):
        self.state = {"weight": 1.0}
        self.applied = False
        self.restored = False

    def snapshot(self):
        return dict(self.state)

    def restore(self, snapshot):
        self.state = dict(snapshot)
        self.restored = True

    def apply_patch(self, patch, *, source, temporary=False):
        self.applied = True
        self.state["weight"] += patch.get("delta", 0)


@pytest.mark.asyncio
async def test_arena_passes_good_patch_and_restores_policy():
    adapter = FakePolicyAdapter()

    arena = BenchmarkArena(
        router_replay=FakeRouterReplay(),
        intelligence_eval=FakeIntelligenceEval(),
        policy_adapter=adapter,
    )

    variant = ArenaVariant.create(
        name="increase_debug_signal",
        patch={"delta": 0.1},
        target=PatchTarget.ROUTER_SIGNAL,
        risk=PatchRisk.LOW,
    )

    report = await arena.run_variant(variant)

    assert report.decision.value == "pass"
    assert adapter.applied is True
    assert adapter.restored is True
    assert adapter.state == {"weight": 1.0}


class BadRouterReplay:
    async def run_file(self, path):
        return FakeRouterReport(acceptable=0.80, full=0.70, safe=0.90, critical=0.80, under=0.20)


@pytest.mark.asyncio
async def test_arena_rejects_bad_router_patch():
    adapter = FakePolicyAdapter()

    arena = BenchmarkArena(
        router_replay=BadRouterReplay(),
        intelligence_eval=FakeIntelligenceEval(),
        policy_adapter=adapter,
    )

    variant = ArenaVariant.create(
        name="bad_patch",
        patch={"delta": 10.0},
        target=PatchTarget.ROUTER_SIGNAL,
        risk=PatchRisk.HIGH,
    )

    report = await arena.run_variant(variant)

    assert report.decision.value == "fail"
    assert report.reasons
    assert adapter.state == {"weight": 1.0}
9. CLI：手动跑 Arena

新增：

scripts/run_arena_variant.py
Python
运行
import argparse
import asyncio
import json
from pathlib import Path

from core.arena.schemas import ArenaVariant
from core.bootstrap import build_benchmark_arena


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patch", required=True)
    parser.add_argument("--name", default="manual_patch")
    parser.add_argument("--target", default="policy_config")
    parser.add_argument("--risk", default="medium")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    patch = json.loads(Path(args.patch).read_text(encoding="utf-8"))

    variant = ArenaVariant.create(
        name=args.name,
        patch=patch,
        target=args.target,
        risk=args.risk,
        source="manual_cli",
    )

    arena = build_benchmark_arena()
    report = await arena.run_variant(variant)

    payload = report.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)

    if report.decision.value != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
10. Bootstrap

新增到 core/bootstrap.py：

Python
运行
def build_benchmark_arena():
    from core.router_replay import RouterReplay
    from core.intelligence_eval import IntelligenceEvalRunner
    from core.arena.benchmark_arena import BenchmarkArena
    from core.arena.report_store import ArenaReportStore

    policy_router = build_intelligence_policy_router()
    workflow = build_intelligence_workflow()

    router_replay = RouterReplay(policy_router)
    intelligence_eval = IntelligenceEvalRunner(
        workflow,
        trace_store=getattr(workflow, "trace_store", None),
    )

    policy_adapter = build_policy_adapter()

    return BenchmarkArena(
        router_replay=router_replay,
        intelligence_eval=intelligence_eval,
        policy_adapter=policy_adapter,
        report_store=ArenaReportStore(),
    )


def build_arena_release_bridge():
    from core.arena.release_bridge import ArenaReleaseBridge

    return ArenaReleaseBridge(
        arena=build_benchmark_arena(),
        gradual_release=build_gradual_release(),
        policy_adapter=build_policy_adapter(),
    )
11. GradualRelease 集成策略

你的发布阶段改成：

Stage 0: pending
- PolicyAdapter 生成补丁

Stage 1: arena
- BenchmarkArena 验证

Stage 2: canary
- GradualRelease 低比例启用

Stage 3: monitored
- 收集 Trace / Eval / LearningStore 反馈

Stage 4: full
- 全量应用

Stage 5: rollback
- 指标下降自动回滚

GradualRelease 的最小接口：

Python
运行
class GradualRelease:
    def create_release(self, patch: dict, *, source: str, metadata: dict) -> dict:
        release_id = self._new_id()

        self.store.insert({
            "id": release_id,
            "patch": patch,
            "source": source,
            "stage": "canary",
            "percent": 0.05,
            "metadata": metadata,
        })

        return {
            "id": release_id,
            "stage": "canary",
            "percent": 0.05,
        }
12. Phase 7 验收标准
P7-1:
ArenaVariant 能表示 PolicyAdapter 生成的补丁。

P7-2:
BenchmarkArena 能对同一套 RouterReplay + IntelligenceEval 先跑 baseline，再跑 candidate。

P7-3:
候选补丁运行后 PolicyAdapter 状态必须 restore。

P7-4:
ArenaGate 能拒绝：
- SAFE recall 下降
- critical recall 下降
- underroute_rate 超标
- eval pass_rate 低于门槛
- eval avg_score 低于门槛
- 新增回归过多

P7-5:
Arena 通过后，ReleaseBridge 调用 GradualRelease.create_release()。

P7-6:
Arena 失败后，PolicyAdapter.mark_rejected() 被调用。

P7-7:
所有自动学习补丁不得绕过 Arena。
13. CI 加这两条
Bash
pytest tests/test_benchmark_arena.py
python scripts/run_arena_variant.py --patch data/test_patch.json --name ci_test_patch --target router_signal --risk low

data/test_patch.json：

JSON
{
  "signal_weight_delta": {
    "is_deep_investigation": 0.1
  },
  "description": "CI smoke test patch"
}
最小落地顺序
第一步：
实现 schemas.py / patch_runner.py / arena_gate.py / benchmark_arena.py

第二步：
加 tests/test_benchmark_arena.py，确认补丁会 restore

第三步：
接 PolicyAdapter，把自动补丁改成 submit_patch_to_arena()

第四步：
接 GradualRelease，Arena PASS 后进入 canary

第五步：
加 report_store.py，保存每次 Arena 结果

一句话：

Phase 7 的核心不是“多跑几个 benchmark”，而是把 Arena 变成自动学习补丁的强制发布闸门。