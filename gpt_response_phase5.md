Phase 5 我建议从 “可信智能流水线”升级到“自进化智能系统”。你现在已经有 Route、Plan、Critic、Evidence、Trace、Eval，下一步不是继续加流程，而是让 CRUX 根据真实运行数据自动变强。

我给 3 个方向，最后给推荐。

方向 A：Adaptive Learning Loop / 自适应学习闭环
定位

让 CRUX 从每次任务中学习：

任务 → 路由 → 执行 → 证据 → 评分 → 失败归因 → 策略修正

你已经有：

Policy Memory
IntelligenceTrace
EvidenceGate
IntelligenceEval
Router Replay

Phase 5-A 就是把它们打通成一个闭环。

新增模块
core/intelligence_learning.py
core/failure_analyzer.py
core/policy_tuner.py
core/prompt_tuner.py
data/learning_rules.json
核心能力

每次任务结束后自动生成：

JSON
{
  "task_id": "...",
  "mode": "DEEP",
  "route_correct": true,
  "plan_gate_passed": true,
  "evidence_quality": "weak",
  "final_score": 0.62,
  "failure_type": "weak_evidence",
  "root_cause": "missing_test_result",
  "suggested_policy_change": {
    "require_tests": true,
    "for_modes": ["DEEP"]
  }
}
代码骨架
Python
运行
# core/failure_analyzer.py

from dataclasses import dataclass
from typing import Any


@dataclass
class FailureDiagnosis:
    failure_type: str
    root_cause: str
    severity: str
    suggested_action: str
    policy_patch: dict[str, Any]


class FailureAnalyzer:
    def analyze(self, trace: dict[str, Any], eval_result: dict[str, Any]) -> FailureDiagnosis | None:
        evidence = eval_result.get("evidence_quality")
        score = eval_result.get("score", 1.0)

        if score >= 0.8:
            return None

        if evidence in {"none", "weak"}:
            return FailureDiagnosis(
                failure_type="weak_evidence",
                root_cause="final answer lacked strong evidence",
                severity="high",
                suggested_action="tighten EvidenceGate and require test/tool evidence",
                policy_patch={
                    "require_evidence_gate_pass": True,
                    "require_tests_if_code_task": True,
                },
            )

        phases = {e.get("phase") for e in trace.get("events", [])}

        if "critic" not in phases:
            return FailureDiagnosis(
                failure_type="missing_critic",
                root_cause="critic phase did not run",
                severity="medium",
                suggested_action="force critic for DEEP/SAFE/RESEARCH",
                policy_patch={
                    "require_critic_round": True,
                },
            )

        if "repair" not in phases and eval_result.get("needs_fix"):
            return FailureDiagnosis(
                failure_type="missing_repair",
                root_cause="failed task did not enter repair loop",
                severity="high",
                suggested_action="increase max_repair_rounds",
                policy_patch={
                    "max_repair_rounds_delta": 1,
                },
            )

        return FailureDiagnosis(
            failure_type="unknown_low_score",
            root_cause="score below threshold but no known failure pattern matched",
            severity="medium",
            suggested_action="add manual review case",
            policy_patch={},
        )
Python
运行
# core/policy_tuner.py

from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyTuneSuggestion:
    id: str
    reason: str
    patch: dict[str, Any]
    confidence: float
    support_count: int


class PolicyTuner:
    def suggest(self, diagnoses: list[Any]) -> list[PolicyTuneSuggestion]:
        buckets: dict[str, list[Any]] = {}

        for d in diagnoses:
            buckets.setdefault(d.failure_type, []).append(d)

        suggestions: list[PolicyTuneSuggestion] = []

        for failure_type, items in buckets.items():
            if len(items) < 3:
                continue

            if failure_type == "weak_evidence":
                suggestions.append(
                    PolicyTuneSuggestion(
                        id="require_stronger_evidence_for_deep",
                        reason="Multiple DEEP tasks failed because evidence was weak.",
                        patch={
                            "DEEP": {
                                "require_evidence_gate_pass": True,
                                "min_evidence_quality": "strong",
                            }
                        },
                        confidence=0.8,
                        support_count=len(items),
                    )
                )

            if failure_type == "missing_repair":
                suggestions.append(
                    PolicyTuneSuggestion(
                        id="increase_repair_rounds",
                        reason="Tasks needing repair did not get enough repair attempts.",
                        patch={
                            "DEEP": {
                                "max_repair_rounds": 3,
                            }
                        },
                        confidence=0.7,
                        support_count=len(items),
                    )
                )

        return suggestions
价值

这是最像 “o 系列系统” 的方向，因为它让 CRUX 不只是执行，而是：

失败 → 归因 → 调参 → 回放验证 → 固化策略
方向 B：Capability Runtime / 能力分层运行时
定位

把 CRUX 的能力分成不同运行时，而不是所有任务都走同一个大流程。

现在你的模式是：

FAST / BALANCED / DEEP / SAFE / RESEARCH / CREATIVE

Phase 5-B 可以升级成：

CodingRuntime
DebugRuntime
ResearchRuntime
CreativeRuntime
SecurityRuntime
RefactorRuntime

每个 Runtime 有自己的：

ContextGather
PlanGate
Critic
EvidenceGate
Eval
RepairLoop
新增模块
core/runtime/base_runtime.py
core/runtime/coding_runtime.py
core/runtime/debug_runtime.py
core/runtime/research_runtime.py
core/runtime/creative_runtime.py
core/runtime/security_runtime.py
core/runtime/runtime_router.py
代码骨架
Python
运行
# core/runtime/base_runtime.py

from abc import ABC, abstractmethod
from typing import Any


class BaseRuntime(ABC):
    name: str = "base"

    def __init__(self, toolbus, trace_store, evidence_gate, critic_agent):
        self.toolbus = toolbus
        self.trace_store = trace_store
        self.evidence_gate = evidence_gate
        self.critic_agent = critic_agent

    @abstractmethod
    async def run(self, request: str, goal: dict[str, Any], policy: Any, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
Python
运行
# core/runtime/debug_runtime.py

from core.runtime.base_runtime import BaseRuntime


class DebugRuntime(BaseRuntime):
    name = "debug"

    async def run(self, request, goal, policy, context):
        context_pack = await self.toolbus.call("trm_route", {
            "intent": "search",
            "scope": "local_repo",
            "request": request,
            "focus": [
                "error logs",
                "call chain",
                "recent changes",
                "tests",
                "reproduction path",
            ],
        })

        plan = await self.toolbus.call("execute_plan", {
            "mode": "plan_only",
            "goal": goal,
            "context_pack": context_pack,
            "debug_required": True,
        })

        attack = await self.toolbus.call("multi_agent", {
            "mode": "parallel_attack",
            "agents": [
                "RootCauseHunter",
                "RegressionHunter",
                "ReproDesigner",
                "TestGapFinder",
            ],
            "goal": goal,
            "plan": plan,
            "context_pack": context_pack,
        })

        critique = await self.critic_agent.review(
            goal=goal,
            plan=plan,
            attack_report=attack,
            context_pack=context_pack,
            policy=policy.to_dict(),
        )

        result = await self.toolbus.call("execute_plan", {
            "mode": "execute",
            "goal": goal,
            "plan": plan,
            "critique": critique,
            "require_repro": True,
            "require_tests": True,
        })

        evidence = self.evidence_gate.evaluate(
            goal=goal,
            result=result,
            policy=policy.to_dict(),
            critique_report=critique,
        )

        result.setdefault("metadata", {})
        result["metadata"]["runtime"] = self.name
        result["metadata"]["evidence_gate"] = evidence.to_dict()

        return result
价值

这个方向会让 CRUX 的工程结构更干净：

DeliberateWorkflow 不再无限膨胀
不同任务有不同最佳实践
后续技能包可以挂到具体 Runtime
风险

它会引入较多文件和抽象。你现在刚完成 Phase 4，马上做 Runtime 分裂，容易让系统变复杂。

方向 C：Production Reliability OS / 生产级可靠性
定位

把 CRUX 从“本地智能助手”升级成“长期稳定运行的本地 AI OS”。

重点不是更聪明，而是：

不卡死
不中断
可取消
可恢复
可限流
可回滚
可观测
新增模块
core/runtime_guard.py
core/cancellation.py
core/resource_budget.py
core/rollback_manager.py
core/task_queue.py
core/healthcheck.py
必做能力
1. 统一 Cancellation Token
Python
运行
# core/cancellation.py

from dataclasses import dataclass
import asyncio


@dataclass
class CancellationToken:
    cancelled: bool = False
    reason: str | None = None

    def cancel(self, reason: str = "cancelled by user") -> None:
        self.cancelled = True
        self.reason = reason

    def throw_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError(self.reason or "cancelled")
2. Resource Budget
Python
运行
# core/resource_budget.py

from dataclasses import dataclass
import time


@dataclass
class ResourceBudget:
    max_tool_calls: int = 30
    max_runtime_sec: float = 300
    max_repair_rounds: int = 3
    max_web_fetches: int = 8

    tool_calls: int = 0
    web_fetches: int = 0
    started_at: float = time.time()

    def check(self) -> None:
        if self.tool_calls > self.max_tool_calls:
            raise RuntimeError("tool call budget exceeded")

        if self.web_fetches > self.max_web_fetches:
            raise RuntimeError("web fetch budget exceeded")

        if time.time() - self.started_at > self.max_runtime_sec:
            raise RuntimeError("runtime budget exceeded")

    def count_tool(self, name: str) -> None:
        self.tool_calls += 1
        if name in {"web_search", "web_fetch", "pw_navigate"}:
            self.web_fetches += 1
        self.check()
3. Rollback Manager
Python
运行
# core/rollback_manager.py

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import time


@dataclass
class FileSnapshot:
    path: str
    backup_path: str
    ts: float


class RollbackManager:
    def __init__(self, backup_dir: str = ".crux/rollback"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots: list[FileSnapshot] = []

    def snapshot_file(self, path: str) -> None:
        src = Path(path)
        if not src.exists() or not src.is_file():
            return

        backup = self.backup_dir / f"{int(time.time())}_{src.name}.bak"
        shutil.copy2(src, backup)

        self.snapshots.append(
            FileSnapshot(
                path=str(src),
                backup_path=str(backup),
                ts=time.time(),
            )
        )

    def rollback_all(self) -> None:
        for snap in reversed(self.snapshots):
            shutil.copy2(snap.backup_path, snap.path)
价值

这个方向最适合你要长期使用 CRUX 的情况。尤其你现在有：

execute_plan
multi_agent
agent_swarm
CDP 浏览器
文件修改
代码执行

这些都需要预算、取消、回滚。

风险

这个方向提升稳定性，但不会直接提升“看起来更聪明”的效果。

我的推荐：Phase 5 做方向 A
最推荐
Phase 5 = Adaptive Learning Loop

原因：

1. 你 Phase 1-4 的所有基础设施都已经为它准备好了
2. 它能最大化复用 PolicyMemory / Trace / EvidenceGate / Eval
3. 它会让 CRUX 从“可观测”进入“自校准”
4. 它比 Runtime 分裂更稳，比 Reliability OS 更直接提升智能质量

Phase 5 不应该大改主链路，而应该加一个后处理学习器：

DeliberateWorkflow 完成
   ↓
TraceStore 记录
   ↓
EvidenceGate 评分
   ↓
IntelligenceEval / 用户反馈
   ↓
FailureAnalyzer 归因
   ↓
PolicyTuner / PromptTuner 生成建议
   ↓
RouterReplay / IntelligenceEval 验证
   ↓
人工确认后固化规则

注意：不要让 CRUX 自动修改自己的核心策略。Phase 5 只生成建议，必须经过 replay 验证后再固化。

Phase 5 具体落地计划
P5-1：Learning Record

新增：

core/intelligence_learning.py
Python
运行
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


@dataclass
class LearningRecord:
    id: str
    ts: float
    trace_run_id: str
    request_sample: str
    mode: str
    score: float
    outcome: str
    failure_type: str | None = None
    root_cause: str | None = None
    suggested_patch: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class IntelligenceLearningStore:
    def __init__(self, db_path: str | Path = "data/intelligence_learning.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS learning_records (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    trace_run_id TEXT NOT NULL,
                    request_sample TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    score REAL NOT NULL,
                    outcome TEXT NOT NULL,
                    failure_type TEXT,
                    root_cause TEXT,
                    suggested_patch_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
            """)

    def add(self, record: LearningRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_records
                (id, ts, trace_run_id, request_sample, mode, score, outcome,
                 failure_type, root_cause, suggested_patch_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.ts,
                    record.trace_run_id,
                    record.request_sample,
                    record.mode,
                    record.score,
                    record.outcome,
                    record.failure_type,
                    record.root_cause,
                    json.dumps(record.suggested_patch, ensure_ascii=False),
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )

    def recent(self, limit: int = 100) -> list[LearningRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, trace_run_id, request_sample, mode, score, outcome,
                       failure_type, root_cause, suggested_patch_json, metadata_json
                FROM learning_records
                ORDER BY ts DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            LearningRecord(
                id=r[0],
                ts=r[1],
                trace_run_id=r[2],
                request_sample=r[3],
                mode=r[4],
                score=r[5],
                outcome=r[6],
                failure_type=r[7],
                root_cause=r[8],
                suggested_patch=json.loads(r[9]),
                metadata=json.loads(r[10]),
            )
            for r in rows
        ]


class IntelligenceLearningLoop:
    def __init__(self, store: IntelligenceLearningStore, failure_analyzer):
        self.store = store
        self.failure_analyzer = failure_analyzer

    def learn_from_run(
        self,
        *,
        trace: dict[str, Any],
        final_result: dict[str, Any],
        eval_result: dict[str, Any] | None = None,
    ) -> LearningRecord:
        metadata = final_result.get("metadata", {})
        evidence_gate = metadata.get("evidence_gate", {})
        score = self._score(final_result, eval_result, evidence_gate)

        diagnosis = self.failure_analyzer.analyze(
            trace=trace,
            eval_result={
                "score": score,
                "evidence_quality": evidence_gate.get("evidence_quality"),
                "needs_fix": score < 0.8,
            },
        )

        outcome = "success" if score >= 0.8 and diagnosis is None else "failure"

        record = LearningRecord(
            id=f"learn_{uuid.uuid4().hex[:16]}",
            ts=time.time(),
            trace_run_id=trace.get("run_id", ""),
            request_sample=trace.get("user_request", "")[:500],
            mode=trace.get("mode") or metadata.get("mode", "unknown"),
            score=score,
            outcome=outcome,
            failure_type=diagnosis.failure_type if diagnosis else None,
            root_cause=diagnosis.root_cause if diagnosis else None,
            suggested_patch=diagnosis.policy_patch if diagnosis else {},
            metadata={
                "evidence_gate": evidence_gate,
                "eval_result": eval_result or {},
            },
        )

        self.store.add(record)
        return record

    def _score(self, final_result, eval_result, evidence_gate) -> float:
        if eval_result and "score" in eval_result:
            return float(eval_result["score"])

        if "score" in evidence_gate:
            return float(evidence_gate["score"])

        return 0.5
P5-2：FailureAnalyzer

新增：

core/failure_analyzer.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FailureDiagnosis:
    failure_type: str
    root_cause: str
    severity: str
    suggested_action: str
    policy_patch: dict[str, Any]


class FailureAnalyzer:
    def analyze(self, trace: dict[str, Any], eval_result: dict[str, Any]) -> FailureDiagnosis | None:
        score = float(eval_result.get("score", 1.0))
        if score >= 0.8:
            return None

        phases = [e.get("phase") for e in trace.get("events", [])]
        phase_set = set(phases)
        evidence_quality = eval_result.get("evidence_quality")

        if evidence_quality in {"none", "weak"}:
            return FailureDiagnosis(
                failure_type="weak_evidence",
                root_cause="final answer lacked strong supporting evidence",
                severity="high",
                suggested_action="require stronger evidence before final answer",
                policy_patch={
                    "require_evidence_gate_pass": True,
                    "min_evidence_quality": "strong",
                },
            )

        if "context_gather" not in phase_set:
            return FailureDiagnosis(
                failure_type="missing_context",
                root_cause="workflow skipped context gathering",
                severity="high",
                suggested_action="force ContextGather for BALANCED+ tasks",
                policy_patch={
                    "BALANCED.require_context_gather": True,
                    "DEEP.require_context_gather": True,
                },
            )

        if "critic" not in phase_set and trace.get("mode") in {"DEEP", "SAFE", "RESEARCH"}:
            return FailureDiagnosis(
                failure_type="missing_critic",
                root_cause="high-risk mode skipped critic phase",
                severity="high",
                suggested_action="force critic for high-risk modes",
                policy_patch={
                    "DEEP.require_critic_round": True,
                    "SAFE.require_critic_round": True,
                    "RESEARCH.require_critic_round": True,
                },
            )

        if "repair" not in phase_set and eval_result.get("needs_fix"):
            return FailureDiagnosis(
                failure_type="missing_repair",
                root_cause="task needed fix but repair phase did not run",
                severity="medium",
                suggested_action="trigger repair when EvidenceGate returns needs_fix",
                policy_patch={
                    "repair_on_evidence_needs_fix": True,
                },
            )

        error_events = [
            e for e in trace.get("events", [])
            if e.get("status") in {"error", "failed"}
        ]

        if error_events:
            return FailureDiagnosis(
                failure_type="tool_or_runtime_failure",
                root_cause="one or more tool/runtime phases failed",
                severity="medium",
                suggested_action="add fallback or retry for failed phase",
                policy_patch={
                    "tool_retry_on_failure": True,
                },
            )

        return FailureDiagnosis(
            failure_type="unknown_failure",
            root_cause="low score without matched known failure pattern",
            severity="low",
            suggested_action="add eval case and manual review",
            policy_patch={},
        )
P5-3：PolicyTuner

新增：

core/policy_tuner.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TuneSuggestion:
    id: str
    kind: str
    patch: dict[str, Any]
    reason: str
    support_count: int
    confidence: float


class PolicyTuner:
    def suggest(self, records: list[Any]) -> list[TuneSuggestion]:
        failures = [r for r in records if r.outcome == "failure"]
        buckets: dict[str, list[Any]] = {}

        for r in failures:
            if not r.failure_type:
                continue
            buckets.setdefault(r.failure_type, []).append(r)

        suggestions: list[TuneSuggestion] = []

        for failure_type, xs in buckets.items():
            if len(xs) < 3:
                continue

            if failure_type == "weak_evidence":
                suggestions.append(TuneSuggestion(
                    id="tighten_evidence_gate",
                    kind="policy_patch",
                    patch={
                        "DEEP": {
                            "require_evidence_gate_pass": True,
                            "min_evidence_score": 0.75,
                        },
                        "RESEARCH": {
                            "require_web_source": True,
                            "min_evidence_score": 0.8,
                        },
                    },
                    reason=f"{len(xs)} recent failures were caused by weak evidence.",
                    support_count=len(xs),
                    confidence=0.85,
                ))

            elif failure_type == "missing_context":
                suggestions.append(TuneSuggestion(
                    id="force_context_gather",
                    kind="policy_patch",
                    patch={
                        "BALANCED": {
                            "require_context_gather": True,
                        },
                        "DEEP": {
                            "require_context_gather": True,
                        },
                    },
                    reason=f"{len(xs)} recent failures skipped context gathering.",
                    support_count=len(xs),
                    confidence=0.8,
                ))

            elif failure_type == "tool_or_runtime_failure":
                suggestions.append(TuneSuggestion(
                    id="tool_retry_policy",
                    kind="policy_patch",
                    patch={
                        "tool_retry": {
                            "max_attempts": 2,
                            "backoff_ms": 300,
                        }
                    },
                    reason=f"{len(xs)} recent failures came from tool/runtime errors.",
                    support_count=len(xs),
                    confidence=0.7,
                ))

        return suggestions
Phase 5 验收标准
1. 每次复杂任务结束后写入 LearningRecord
2. 低分任务能被 FailureAnalyzer 分类
3. PolicyTuner 能从最近 N 条失败中生成建议
4. 所有建议必须经过 RouterReplay / IntelligenceEval 验证后才能固化
5. Phase 5 不允许自动修改核心策略文件

CI 新增：

Bash
python -m core.router_replay --cases data/router_golden_cases.jsonl
python -m core.intelligence_eval --cases data/intelligence_eval_cases.jsonl --min-pass-rate 0.80 --min-avg-score 0.70
python -m core.learning_report --limit 100
三个方向最终排序
第一推荐：方向 A — Adaptive Learning Loop
收益最大，最贴合你现有 Phase 1-4。

第二推荐：方向 C — Production Reliability OS
等学习闭环稳定后做，保证长期运行不炸。

第三推荐：方向 B — Capability Runtime
等系统规模更大后再拆 Runtime，避免现在过早抽象。

我的明确建议：

Phase 5 做 Adaptive Learning Loop。
Phase 6 做 Production Reliability OS。
Phase 7 再做 Capability Runtime。

一句话：

Phase 5 不要继续让 CRUX “多想一步”，而是让它“每次做完都学到一点”。