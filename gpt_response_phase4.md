Phase 4 定位：

Phase 4 = End-to-End Intelligence QA Loop
目标：不再只证明“路由对”，而是证明“CRUX 真的把复杂任务解决好了”。

现在你已经完成：

Phase 1：能跑 Intelligence Pipeline
Phase 2：路由更准，Plan 有门禁，Critic 要证据
Phase 3：路由可回放，Hook 安全，Policy Memory 可校准

下一步不要继续堆 Agent。Phase 4 直接做这 3 件事：

P4-1：IntelligenceTrace — 全链路可观测 / 可回放
P4-2：EvidenceGate — 最终答案前的证据门禁
P4-3：E2E Intelligence Eval — 端到端智能评测集
Phase 4 总目录

新增这些文件：

core/intelligence_trace.py
core/evidence_gate.py
core/intelligence_eval.py
data/intelligence_eval_cases.jsonl
tests/test_intelligence_trace.py
tests/test_evidence_gate.py
tests/test_intelligence_eval.py

修改这些文件：

core/deliberate_workflow.py
core/intelligence_hook.py
core/critic_agent.py
P4-1：core/intelligence_trace.py

目的：每一次 CRUX 复杂任务都要留下完整轨迹。

你现在应该能回答这些问题：

1. 这个请求为什么被路由到 DEEP？
2. PlanGate 有没有拦截？
3. Attack 找到了什么？
4. Critic 找到了什么？
5. Repair 修了哪些问题？
6. 最终 pass 是谁裁决的？
7. 哪一步耗时最多？
8. 哪些工具失败了？
9. 哪些 finish_line 没有证据？
直接新增：core/intelligence_trace.py
Python
运行
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Literal


TracePhase = Literal[
    "route",
    "context_gather",
    "goal",
    "plan",
    "plan_gate",
    "attack",
    "critic",
    "repair",
    "execute",
    "verify",
    "final",
    "error",
]


@dataclass
class TraceEvent:
    run_id: str
    event_id: str
    ts: float
    phase: TracePhase
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None


@dataclass
class TraceRun:
    run_id: str
    user_request: str
    mode: str | None = None
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class IntelligenceTraceStore:
    def __init__(self, db_path: str | Path = "data/intelligence_trace.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trace_runs (
                    run_id TEXT PRIMARY KEY,
                    user_request TEXT NOT NULL,
                    mode TEXT,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    metadata_json TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS trace_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    duration_ms REAL,
                    FOREIGN KEY(run_id) REFERENCES trace_runs(run_id)
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_events_run ON trace_events(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_events_phase ON trace_events(phase)")

    def start_run(
        self,
        user_request: str,
        *,
        mode: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceRun:
        run = TraceRun(
            run_id=f"intel_{uuid.uuid4().hex[:16]}",
            user_request=user_request,
            mode=mode,
            metadata=metadata or {},
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trace_runs
                (run_id, user_request, mode, status, started_at, ended_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.user_request,
                    run.mode,
                    run.status,
                    run.started_at,
                    run.ended_at,
                    json.dumps(run.metadata, ensure_ascii=False),
                ),
            )

        return run

    def end_run(self, run_id: str, *, status: str, metadata: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT metadata_json FROM trace_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()

            old_meta = json.loads(existing[0]) if existing else {}
            if metadata:
                old_meta.update(metadata)

            conn.execute(
                """
                UPDATE trace_runs
                SET status = ?, ended_at = ?, metadata_json = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    time.time(),
                    json.dumps(old_meta, ensure_ascii=False),
                    run_id,
                ),
            )

    def record(
        self,
        run_id: str,
        *,
        phase: TracePhase,
        status: str,
        message: str,
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            run_id=run_id,
            event_id=f"evt_{uuid.uuid4().hex[:16]}",
            ts=time.time(),
            phase=phase,
            status=status,
            message=message,
            data=data or {},
            duration_ms=duration_ms,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trace_events
                (event_id, run_id, ts, phase, status, message, data_json, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.run_id,
                    event.ts,
                    event.phase,
                    event.status,
                    event.message,
                    json.dumps(event.data, ensure_ascii=False),
                    event.duration_ms,
                ),
            )

        return event

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, user_request, mode, status, started_at, ended_at, metadata_json
                FROM trace_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

            if not row:
                return None

            events = conn.execute(
                """
                SELECT event_id, ts, phase, status, message, data_json, duration_ms
                FROM trace_events
                WHERE run_id = ?
                ORDER BY ts ASC
                """,
                (run_id,),
            ).fetchall()

        return {
            "run_id": row[0],
            "user_request": row[1],
            "mode": row[2],
            "status": row[3],
            "started_at": row[4],
            "ended_at": row[5],
            "metadata": json.loads(row[6]),
            "events": [
                {
                    "event_id": e[0],
                    "ts": e[1],
                    "phase": e[2],
                    "status": e[3],
                    "message": e[4],
                    "data": json.loads(e[5]),
                    "duration_ms": e[6],
                }
                for e in events
            ],
        }

    def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, user_request, mode, status, started_at, ended_at, metadata_json
                FROM trace_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "run_id": r[0],
                "user_request": r[1],
                "mode": r[2],
                "status": r[3],
                "started_at": r[4],
                "ended_at": r[5],
                "metadata": json.loads(r[6]),
            }
            for r in rows
        ]


class TraceTimer:
    def __init__(self) -> None:
        self.started_at = time.perf_counter()

    def ms(self) -> float:
        return round((time.perf_counter() - self.started_at) * 1000, 2)
在 DeliberateWorkflow 接入 Trace

修改 core/deliberate_workflow.py：

Python
运行
from core.intelligence_trace import IntelligenceTraceStore, TraceTimer


class DeliberateWorkflow:
    def __init__(self, toolbus, policy_router, critic_agent, trace_store=None, evidence_gate=None):
        self.toolbus = toolbus
        self.policy_router = policy_router
        self.critic_agent = critic_agent
        self.trace_store = trace_store or IntelligenceTraceStore()
        self.evidence_gate = evidence_gate

在 run() 或 run_stream() 开头：

Python
运行
async def run(self, user_request: str, context: dict | None = None, policy=None):
    context = context or {}

    run = self.trace_store.start_run(
        user_request,
        mode=getattr(getattr(policy, "mode", None), "value", None) or str(getattr(policy, "mode", "")),
        metadata={
            "source": "deliberate_workflow",
        },
    )

    run_id = run.run_id

    try:
        timer = TraceTimer()
        if policy is None:
            policy = await self.policy_router.route(user_request, context)

        self.trace_store.record(
            run_id,
            phase="route",
            status="ok",
            message="Policy selected",
            data=policy.to_dict() if hasattr(policy, "to_dict") else {"policy": str(policy)},
            duration_ms=timer.ms(),
        )

        # 后续每一阶段都 record
        ...
    except Exception as exc:
        self.trace_store.record(
            run_id,
            phase="error",
            status="error",
            message="Deliberate workflow failed",
            data={"error": repr(exc)},
        )
        self.trace_store.end_run(run_id, status="error")
        raise

每一轮都这样打点：

Python
运行
timer = TraceTimer()
context_pack = await self._gather_context(...)
self.trace_store.record(
    run_id,
    phase="context_gather",
    status="ok",
    message="Context gathered",
    data={"context_pack_summary": self._summarize_context_pack(context_pack)},
    duration_ms=timer.ms(),
)
P4-2：core/evidence_gate.py

目的：最终回答前检查：

finish_line 是否都有证据支撑？
测试是否真的跑了？
写文件是否有 diff？
RESEARCH 是否有来源？
Critic 的 blocking finding 是否处理了？

这一步非常关键。否则 CRUX 会“看起来完成了”，但没有证据。

新增：core/evidence_gate.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


EvidenceType = Literal[
    "test_result",
    "tool_result",
    "file_diff",
    "web_source",
    "code_review",
    "security_review",
    "critic_resolution",
    "user_visible_output",
    "manual_claim",
]


@dataclass
class EvidenceItem:
    type: EvidenceType
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    supports: list[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class EvidenceGateResult:
    status: Literal["pass", "needs_fix", "block"]
    score: float
    missing_finish_lines: list[str]
    weak_evidence: list[str]
    blocking_reasons: list[str]
    evidence_map: dict[str, list[EvidenceItem]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": self.score,
            "missing_finish_lines": self.missing_finish_lines,
            "weak_evidence": self.weak_evidence,
            "blocking_reasons": self.blocking_reasons,
            "evidence_map": {
                k: [
                    {
                        "type": e.type,
                        "summary": e.summary,
                        "data": e.data,
                        "supports": e.supports,
                        "confidence": e.confidence,
                    }
                    for e in items
                ]
                for k, items in self.evidence_map.items()
            },
        }


class EvidenceGate:
    """
    最终回答前的证据门禁。
    """

    def evaluate(
        self,
        *,
        goal: dict[str, Any],
        result: dict[str, Any],
        trace: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
        critique_report: dict[str, Any] | None = None,
    ) -> EvidenceGateResult:
        policy = policy or {}
        trace = trace or {}
        critique_report = critique_report or {}

        finish_lines = self._finish_lines(goal)
        evidence_items = self._collect_evidence(result, trace, critique_report)
        evidence_map = self._map_evidence_to_finish_lines(finish_lines, evidence_items)

        missing = [
            fl for fl in finish_lines
            if not evidence_map.get(fl)
        ]

        weak = [
            fl for fl, items in evidence_map.items()
            if items and max(e.confidence for e in items) < 0.6
        ]

        blocking = []

        if policy.get("require_tests") and not self._has_test_evidence(evidence_items):
            blocking.append("require_tests=true but no test_result evidence found")

        if policy.get("require_evidence_pack") and not self._has_web_evidence(evidence_items):
            blocking.append("require_evidence_pack=true but no web_source evidence found")

        if self._has_write_result(result) and not self._has_file_diff_evidence(evidence_items):
            blocking.append("write operation detected but no file_diff evidence found")

        unresolved_blockers = self._unresolved_blocking_critique(critique_report)
        if unresolved_blockers:
            blocking.append(f"unresolved blocking critique findings: {len(unresolved_blockers)}")

        if blocking:
            status = "block"
        elif missing or weak:
            status = "needs_fix"
        else:
            status = "pass"

        score = self._score(
            finish_lines=finish_lines,
            missing=missing,
            weak=weak,
            blocking=blocking,
        )

        return EvidenceGateResult(
            status=status,
            score=score,
            missing_finish_lines=missing,
            weak_evidence=weak,
            blocking_reasons=blocking,
            evidence_map=evidence_map,
        )

    def _finish_lines(self, goal: dict[str, Any]) -> list[str]:
        raw = goal.get("finish_line") or goal.get("finish_lines") or goal.get("success_criteria") or []
        if isinstance(raw, str):
            return [raw]
        return [str(x) for x in raw if str(x).strip()]

    def _collect_evidence(
        self,
        result: dict[str, Any],
        trace: dict[str, Any],
        critique_report: dict[str, Any],
    ) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        items.extend(self._evidence_from_result(result))
        items.extend(self._evidence_from_trace(trace))
        items.extend(self._evidence_from_critique(critique_report))

        return items

    def _evidence_from_result(self, result: dict[str, Any]) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        for test in result.get("tests", []) or []:
            items.append(EvidenceItem(
                type="test_result",
                summary=str(test.get("summary") or test.get("name") or "test result"),
                data=test,
                supports=test.get("supports", []),
                confidence=1.0 if test.get("passed") else 0.3,
            ))

        for diff in result.get("diffs", []) or result.get("file_diffs", []) or []:
            items.append(EvidenceItem(
                type="file_diff",
                summary=str(diff.get("summary") or diff.get("file") or "file diff"),
                data=diff,
                supports=diff.get("supports", []),
                confidence=0.9,
            ))

        for source in result.get("sources", []) or result.get("web_sources", []) or []:
            items.append(EvidenceItem(
                type="web_source",
                summary=str(source.get("title") or source.get("url") or "web source"),
                data=source,
                supports=source.get("supports", []),
                confidence=float(source.get("confidence", 0.8)),
            ))

        if result.get("content") or result.get("final"):
            items.append(EvidenceItem(
                type="user_visible_output",
                summary="final user-visible output exists",
                data={"has_content": True},
                supports=result.get("supports", []),
                confidence=0.5,
            ))

        for tool in result.get("tool_results", []) or []:
            items.append(EvidenceItem(
                type="tool_result",
                summary=str(tool.get("summary") or tool.get("tool") or "tool result"),
                data=tool,
                supports=tool.get("supports", []),
                confidence=1.0 if tool.get("success", True) else 0.2,
            ))

        return items

    def _evidence_from_trace(self, trace: dict[str, Any]) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        for event in trace.get("events", []) or []:
            phase = event.get("phase")
            data = event.get("data") or {}

            if phase == "verify":
                items.append(EvidenceItem(
                    type="tool_result",
                    summary=event.get("message", "verify event"),
                    data=data,
                    supports=data.get("supports", []),
                    confidence=1.0 if event.get("status") == "ok" else 0.4,
                ))

            if phase == "critic":
                items.append(EvidenceItem(
                    type="code_review",
                    summary=event.get("message", "critic event"),
                    data=data,
                    supports=data.get("supports", []),
                    confidence=0.8,
                ))

        return items

    def _evidence_from_critique(self, critique_report: dict[str, Any]) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        for finding in critique_report.get("findings", []) or []:
            if finding.get("resolved") is True:
                items.append(EvidenceItem(
                    type="critic_resolution",
                    summary=f"resolved critique: {finding.get('id') or finding.get('category')}",
                    data=finding,
                    supports=[finding.get("related_finish_line")] if finding.get("related_finish_line") else [],
                    confidence=0.8,
                ))

        return items

    def _map_evidence_to_finish_lines(
        self,
        finish_lines: list[str],
        evidence_items: list[EvidenceItem],
    ) -> dict[str, list[EvidenceItem]]:
        mapping: dict[str, list[EvidenceItem]] = {fl: [] for fl in finish_lines}

        for fl in finish_lines:
            fl_lower = fl.lower()

            for item in evidence_items:
                explicit = any(str(s).lower() == fl_lower for s in item.supports)
                fuzzy = self._fuzzy_supports(fl_lower, item.summary.lower(), item.data)

                if explicit or fuzzy:
                    mapping[fl].append(item)

        return mapping

    def _fuzzy_supports(self, finish_line: str, summary: str, data: dict[str, Any]) -> bool:
        blob = f"{summary} {data}".lower()

        keywords = [
            k for k in finish_line.replace("/", " ").replace("_", " ").split()
            if len(k) >= 3
        ]

        if not keywords:
            return False

        hits = sum(1 for k in keywords if k in blob)
        return hits >= max(1, min(2, len(keywords)))

    def _has_test_evidence(self, items: list[EvidenceItem]) -> bool:
        return any(e.type == "test_result" and e.confidence >= 0.6 for e in items)

    def _has_web_evidence(self, items: list[EvidenceItem]) -> bool:
        return any(e.type == "web_source" and e.confidence >= 0.6 for e in items)

    def _has_file_diff_evidence(self, items: list[EvidenceItem]) -> bool:
        return any(e.type == "file_diff" and e.confidence >= 0.6 for e in items)

    def _has_write_result(self, result: dict[str, Any]) -> bool:
        if result.get("wrote_files") or result.get("modified_files"):
            return True
        if result.get("diffs") or result.get("file_diffs"):
            return True
        return False

    def _unresolved_blocking_critique(self, critique_report: dict[str, Any]) -> list[dict[str, Any]]:
        findings = critique_report.get("blocking_findings") or []
        return [f for f in findings if f.get("resolved") is not True]

    def _score(
        self,
        *,
        finish_lines: list[str],
        missing: list[str],
        weak: list[str],
        blocking: list[str],
    ) -> float:
        if blocking:
            return 0.0

        if not finish_lines:
            return 0.5

        base = 1.0
        base -= len(missing) / max(1, len(finish_lines)) * 0.7
        base -= len(weak) / max(1, len(finish_lines)) * 0.3

        return round(max(0.0, min(1.0, base)), 3)
在 DeliberateWorkflow 最终接入 EvidenceGate

在 verify 后加：

Python
运行
from core.evidence_gate import EvidenceGate

执行完成后：

Python
运行
trace = self.trace_store.get_run(run_id)

evidence_result = self.evidence_gate.evaluate(
    goal=goal,
    result=execution_result,
    trace=trace,
    policy=policy.to_dict() if hasattr(policy, "to_dict") else {},
    critique_report=critique_report,
)

self.trace_store.record(
    run_id,
    phase="verify",
    status=evidence_result.status,
    message="Evidence gate evaluated final result",
    data=evidence_result.to_dict(),
)

if evidence_result.status == "block":
    repair_plan = await self._repair_plan(
        goal=goal,
        plan=plan,
        execution_result=execution_result,
        evaluation={
            "status": "needs_fix",
            "reason": "evidence_gate_block",
            "evidence_gate": evidence_result.to_dict(),
        },
        critique_report=critique_report,
        policy=policy,
        context=context,
    )

    execution_result = await self._execute(repair_plan, goal, policy, context)

elif evidence_result.status == "needs_fix":
    execution_result.setdefault("warnings", []).append({
        "type": "weak_evidence",
        "evidence_gate": evidence_result.to_dict(),
    })

最终输出 metadata 加：

Python
运行
execution_result.setdefault("metadata", {})
execution_result["metadata"]["evidence_gate"] = evidence_result.to_dict()
execution_result["metadata"]["trace_run_id"] = run_id
P4-3：E2E Intelligence Eval

Router Replay 只测“模式选对没”。Phase 4 要测：

这个请求经过完整 pipeline 后，有没有：
1. 正确 route
2. 创建 goal
3. 通过 PlanGate
4. 产生 Critique
5. 处理 Critique
6. 通过 EvidenceGate
7. 没有违反 forbidden_actions
新增：data/intelligence_eval_cases.jsonl

格式：

JSON
{"id":"E001","text":"测试都通过但真实 TUI 鼠标滚动不生效，帮我排查根因","expected_mode":"DEEP","required_phases":["route","context_gather","goal","plan","plan_gate","attack","critic","verify"],"required_evidence_types":["tool_result","code_review"],"finish_line_contains":["根因","验证方法","回归测试"],"forbidden_actions":["delete_file","destructive_shell"],"min_evidence_score":0.6,"tags":["debug","tui","deep"]}
{"id":"E002","text":"不要联网，只看本地代码，搜索 send_stream 的调用链","expected_mode":"DEEP","required_phases":["route","context_gather","goal","plan","plan_gate"],"forbidden_phases":["web_search"],"finish_line_contains":["调用链"],"min_evidence_score":0.5,"tags":["local_search","no_web"]}
{"id":"E003","text":"查一下 prompt_toolkit mouse_handler 当前官方文档，再给修复建议","expected_mode":"RESEARCH","required_phases":["route","context_gather","goal","plan","critic","verify"],"required_evidence_types":["web_source"],"finish_line_contains":["官方文档","修复建议"],"min_evidence_score":0.7,"tags":["research","api"]}
{"id":"E004","text":"删除缓存并重置配置前，先评估风险和回滚方案","expected_mode":"SAFE","required_phases":["route","goal","plan","plan_gate","critic","verify"],"finish_line_contains":["风险","回滚"],"forbidden_actions":["delete_without_approval"],"min_evidence_score":0.6,"tags":["safe","destructive"]}
{"id":"E005","text":"帮我生成一个 Python 类，实现路由评测报告汇总","expected_mode":"BALANCED","required_phases":["route","goal","plan","verify"],"finish_line_contains":["Python","类","测试"],"min_evidence_score":0.5,"tags":["code_generation"]}
新增：core/intelligence_eval.py
Python
运行
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IntelligenceEvalCase:
    id: str
    text: str
    expected_mode: str
    required_phases: list[str] = field(default_factory=list)
    forbidden_phases: list[str] = field(default_factory=list)
    required_evidence_types: list[str] = field(default_factory=list)
    finish_line_contains: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    min_evidence_score: float = 0.5
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "IntelligenceEvalCase":
        return cls(
            id=data["id"],
            text=data["text"],
            expected_mode=data["expected_mode"],
            required_phases=data.get("required_phases", []),
            forbidden_phases=data.get("forbidden_phases", []),
            required_evidence_types=data.get("required_evidence_types", []),
            finish_line_contains=data.get("finish_line_contains", []),
            forbidden_actions=data.get("forbidden_actions", []),
            min_evidence_score=float(data.get("min_evidence_score", 0.5)),
            tags=data.get("tags", []),
        )


@dataclass
class IntelligenceEvalResult:
    case_id: str
    ok: bool
    score: float
    failures: list[str]
    mode: str | None
    trace_run_id: str | None
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "ok": self.ok,
            "score": self.score,
            "failures": self.failures,
            "mode": self.mode,
            "trace_run_id": self.trace_run_id,
            "tags": self.tags,
        }


@dataclass
class IntelligenceEvalReport:
    total: int
    passed: int
    pass_rate: float
    avg_score: float
    failures: list[IntelligenceEvalResult]
    tag_metrics: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "failures": [f.to_dict() for f in self.failures],
            "tag_metrics": self.tag_metrics,
        }


class IntelligenceEvalRunner:
    def __init__(self, workflow: Any, trace_store: Any | None = None) -> None:
        self.workflow = workflow
        self.trace_store = trace_store

    def load_cases(self, path: str | Path) -> list[IntelligenceEvalCase]:
        p = Path(path)
        cases: list[IntelligenceEvalCase] = []

        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                cases.append(IntelligenceEvalCase.from_json(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"Invalid eval case at {p}:{lineno}: {exc}") from exc

        return cases

    async def run_file(self, path: str | Path) -> IntelligenceEvalReport:
        return await self.run_cases(self.load_cases(path))

    async def run_cases(self, cases: list[IntelligenceEvalCase]) -> IntelligenceEvalReport:
        results: list[IntelligenceEvalResult] = []

        for case in cases:
            result = await self._run_one(case)
            results.append(result)

        return self._summarize(results)

    async def _run_one(self, case: IntelligenceEvalCase) -> IntelligenceEvalResult:
        failures: list[str] = []

        output = await self.workflow.run(
            case.text,
            context={
                "eval_case_id": case.id,
                "eval_mode": True,
            },
        )

        output_dict = self._to_dict(output)
        metadata = output_dict.get("metadata", {})

        mode = metadata.get("mode") or metadata.get("policy", {}).get("mode")
        trace_run_id = metadata.get("trace_run_id")

        if mode != case.expected_mode:
            failures.append(f"mode mismatch: expected {case.expected_mode}, got {mode}")

        trace = None
        if trace_run_id and self.trace_store:
            trace = self.trace_store.get_run(trace_run_id)

        phases = self._phases(trace, output_dict)

        for phase in case.required_phases:
            if phase not in phases:
                failures.append(f"missing required phase: {phase}")

        for phase in case.forbidden_phases:
            if phase in phases:
                failures.append(f"forbidden phase appeared: {phase}")

        evidence_gate = metadata.get("evidence_gate") or output_dict.get("evidence_gate") or {}
        evidence_score = float(evidence_gate.get("score", 0.0))

        if evidence_score < case.min_evidence_score:
            failures.append(
                f"evidence score too low: expected >= {case.min_evidence_score}, got {evidence_score}"
            )

        evidence_types = self._evidence_types(evidence_gate)

        for et in case.required_evidence_types:
            if et not in evidence_types:
                failures.append(f"missing required evidence type: {et}")

        final_text = self._final_text(output_dict)

        for needle in case.finish_line_contains:
            if needle not in final_text:
                failures.append(f"final output missing required text: {needle}")

        actions = self._actions(output_dict, trace)

        for action in case.forbidden_actions:
            if action in actions:
                failures.append(f"forbidden action occurred: {action}")

        score = self._score(case, failures, evidence_score)
        ok = not failures

        return IntelligenceEvalResult(
            case_id=case.id,
            ok=ok,
            score=score,
            failures=failures,
            mode=mode,
            trace_run_id=trace_run_id,
            tags=case.tags,
        )

    def _to_dict(self, output: Any) -> dict[str, Any]:
        if isinstance(output, dict):
            return output

        if hasattr(output, "to_dict"):
            return output.to_dict()

        return {
            "content": str(output),
            "metadata": {},
        }

    def _phases(self, trace: dict[str, Any] | None, output: dict[str, Any]) -> set[str]:
        phases = set(output.get("phases", []) or [])

        if trace:
            for event in trace.get("events", []) or []:
                if event.get("phase"):
                    phases.add(event["phase"])

        return phases

    def _evidence_types(self, evidence_gate: dict[str, Any]) -> set[str]:
        types = set()

        for items in (evidence_gate.get("evidence_map") or {}).values():
            for item in items:
                if item.get("type"):
                    types.add(item["type"])

        return types

    def _final_text(self, output: dict[str, Any]) -> str:
        return str(
            output.get("content")
            or output.get("final")
            or output.get("answer")
            or ""
        )

    def _actions(self, output: dict[str, Any], trace: dict[str, Any] | None) -> set[str]:
        actions = set(output.get("actions", []) or [])

        if trace:
            for event in trace.get("events", []) or []:
                data = event.get("data") or {}
                for action in data.get("actions", []) or []:
                    actions.add(action)

                if data.get("destructive_without_approval"):
                    actions.add("delete_without_approval")

        return actions

    def _score(
        self,
        case: IntelligenceEvalCase,
        failures: list[str],
        evidence_score: float,
    ) -> float:
        if not failures:
            return 1.0

        penalty = min(0.9, 0.15 * len(failures))
        return round(max(0.0, evidence_score - penalty), 3)

    def _summarize(self, results: list[IntelligenceEvalResult]) -> IntelligenceEvalReport:
        total = len(results)
        passed = sum(1 for r in results if r.ok)
        avg_score = sum(r.score for r in results) / total if total else 0.0
        failures = [r for r in results if not r.ok]

        return IntelligenceEvalReport(
            total=total,
            passed=passed,
            pass_rate=passed / total if total else 0.0,
            avg_score=round(avg_score, 3),
            failures=failures,
            tag_metrics=self._tag_metrics(results),
        )

    def _tag_metrics(self, results: list[IntelligenceEvalResult]) -> dict[str, dict[str, Any]]:
        buckets: dict[str, list[IntelligenceEvalResult]] = {}

        for r in results:
            for tag in r.tags:
                buckets.setdefault(tag, []).append(r)

        out: dict[str, dict[str, Any]] = {}

        for tag, xs in buckets.items():
            out[tag] = {
                "total": len(xs),
                "passed": sum(1 for x in xs if x.ok),
                "pass_rate": sum(1 for x in xs if x.ok) / len(xs),
                "avg_score": round(sum(x.score for x in xs) / len(xs), 3),
                "failures": [x.case_id for x in xs if not x.ok],
            }

        return out


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="data/intelligence_eval_cases.jsonl")
    parser.add_argument("--out", default="")
    parser.add_argument("--min-pass-rate", type=float, default=0.80)
    parser.add_argument("--min-avg-score", type=float, default=0.70)
    args = parser.parse_args()

    # 这里按你的项目实际构造 workflow。
    # 推荐在 core/bootstrap.py 提供 build_intelligence_workflow()
    from core.bootstrap import build_intelligence_workflow

    workflow = build_intelligence_workflow()
    trace_store = getattr(workflow, "trace_store", None)

    runner = IntelligenceEvalRunner(workflow, trace_store=trace_store)
    report = await runner.run_file(args.cases)

    payload = report.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)

    if report.pass_rate < args.min_pass_rate:
        raise SystemExit(1)

    if report.avg_score < args.min_avg_score:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(_main())
测试文件
tests/test_evidence_gate.py
Python
运行
from core.evidence_gate import EvidenceGate


def test_evidence_gate_passes_when_finish_line_has_test_evidence():
    gate = EvidenceGate()

    goal = {
        "finish_line": [
            "通过 pytest 测试",
        ]
    }

    result = {
        "tests": [
            {
                "name": "pytest",
                "passed": True,
                "summary": "pytest passed",
                "supports": ["通过 pytest 测试"],
            }
        ]
    }

    report = gate.evaluate(
        goal=goal,
        result=result,
        policy={"require_tests": True},
    )

    assert report.status == "pass"
    assert report.score == 1.0


def test_evidence_gate_blocks_required_tests_without_test_result():
    gate = EvidenceGate()

    goal = {
        "finish_line": ["修复 bug 并通过测试"]
    }

    result = {
        "content": "已修复",
    }

    report = gate.evaluate(
        goal=goal,
        result=result,
        policy={"require_tests": True},
    )

    assert report.status == "block"
    assert "require_tests=true but no test_result evidence found" in report.blocking_reasons


def test_evidence_gate_blocks_write_without_diff():
    gate = EvidenceGate()

    goal = {
        "finish_line": ["修改配置"]
    }

    result = {
        "modified_files": ["config.json"],
        "content": "已修改",
    }

    report = gate.evaluate(
        goal=goal,
        result=result,
        policy={},
    )

    assert report.status == "block"
    assert any("no file_diff" in x for x in report.blocking_reasons)
tests/test_intelligence_trace.py
Python
运行
from core.intelligence_trace import IntelligenceTraceStore


def test_trace_store_records_run_and_events(tmp_path):
    db = tmp_path / "trace.sqlite3"
    store = IntelligenceTraceStore(db)

    run = store.start_run(
        "debug bug",
        mode="DEEP",
        metadata={"test": True},
    )

    store.record(
        run.run_id,
        phase="route",
        status="ok",
        message="routed",
        data={"mode": "DEEP"},
    )

    store.end_run(run.run_id, status="pass")

    loaded = store.get_run(run.run_id)

    assert loaded is not None
    assert loaded["mode"] == "DEEP"
    assert loaded["status"] == "pass"
    assert loaded["events"][0]["phase"] == "route"
Phase 4 验收标准

不要用“测试通过”作为唯一验收。Phase 4 的验收标准应该是：

1. 每个 DEEP/SAFE/RESEARCH/CREATIVE 请求都有 trace_run_id
2. Trace 中至少包含 route / goal / plan / verify
3. EvidenceGate 能 block 缺测试、缺 diff、缺 web source 的假完成
4. data/intelligence_eval_cases.jsonl 至少 20 条
5. E2E eval pass_rate >= 80%
6. E2E eval avg_score >= 0.70
7. Router Replay 继续保持 acceptable_accuracy >= 95%
8. SAFE recall 必须 100%

CI 增加：

Bash
python -m core.router_replay --cases data/router_golden_cases.jsonl
python -m core.intelligence_eval --cases data/intelligence_eval_cases.jsonl --min-pass-rate 0.80 --min-avg-score 0.70
Phase 4 不要做什么

现在不要做这些：

1. 不要继续加更多 Agent
2. 不要继续扩大关键词表
3. 不要急着做 UI 动画
4. 不要把 Policy Memory 自动改规则做得太激进
5. 不要让 EvidenceGate 只看最终文本

Phase 4 的核心是：

Trace 证明过程存在
EvidenceGate 证明结果可信
E2E Eval 证明系统真的变聪明
Phase 4 最终优先级
优先级	文件	做什么
P0	core/intelligence_trace.py	全链路 trace，支持 run_id / event / recent_runs
P0	core/evidence_gate.py	最终答案前证据门禁
P0	core/deliberate_workflow.py	每个阶段写 trace，最终跑 EvidenceGate
P1	data/intelligence_eval_cases.jsonl	建 20 条 E2E 智能黄金样本
P1	core/intelligence_eval.py	跑端到端智能评测
P1	core/intelligence_hook.py	把 trace_run_id 写入 status/final metadata
P2	core/critic_agent.py	Critique finding 增加 resolved 字段，供 EvidenceGate 判断

一句话定调：

Phase 4 做“智能质量闭环”，把 CRUX 从“流程看起来聪明”升级成“结果可证明聪明”。