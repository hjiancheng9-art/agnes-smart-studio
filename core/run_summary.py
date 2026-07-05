"""Run Summary 持久化与查询— 每次 multi_agent.execute 的结果可审计。

设计：
- RunSummary dataclass 结构化存储执行摘要
- JSONL 持久化到 output/runs/ 目录
- 按 root_trace_id 查询、最近 N 条查询、失败查询
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

from core.config import OUTPUT_DIR

RUNS_DIR = os.path.join(OUTPUT_DIR, "runs")
os.makedirs(RUNS_DIR, exist_ok=True)


@dataclass
class RunSummary:
    root_trace_id: str = ""
    goal: str = ""
    status: str = "unknown"
    total_tasks: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    timeout: int = 0
    cancelled: int = 0
    duration_ms: int = 0
    event_counts: dict[str, int] = field(default_factory=dict)
    longest_task: dict | None = None
    failure_reasons: dict[str, int] = field(default_factory=dict)
    quality_status: str = "unknown"
    quality_score: float = 0.0
    quality_flags: list[str] = field(default_factory=list)
    recommendation: str = ""
    created_at: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "RunSummary":
        return cls(
            root_trace_id=d.get("root_trace_id", ""),
            goal=d.get("goal", ""),
            status="failed" if d.get("tasks_failed", 0) > 0 else "done",
            total_tasks=d.get("tasks_total", 0),
            completed=d.get("tasks_done", 0),
            failed=d.get("tasks_failed", 0),
            skipped=d.get("tasks_skipped", 0),
            timeout=d.get("tasks_timeout", 0),
            cancelled=d.get("tasks_cancelled", 0),
            duration_ms=d.get("elapsed_ms", 0),
            event_counts=d.get("events", {}),
            longest_task=d.get("longest_task"),
            failure_reasons=d.get("failure_reasons", {}),
            created_at=time.time(),
            quality_status=d.get("quality_status", "unknown"),
            quality_score=d.get("quality_score", 0.0),
            quality_flags=d.get("quality_flags", []),
            recommendation=d.get("recommendation", ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def save_run(summary_dict: dict) -> str:
    """保存一次执行的摘要到 runs 目录。返回 root_trace_id。"""
    summary = RunSummary.from_dict(summary_dict)
    path = os.path.join(RUNS_DIR, f"{summary.root_trace_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary.to_dict(), f, ensure_ascii=False, indent=2)
    # 追加到索引
    index_path = os.path.join(RUNS_DIR, "_index.jsonl")
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "root_trace_id": summary.root_trace_id,
            "status": summary.status,
            "goal": summary.goal[:80],
            "total": summary.total_tasks,
            "failed": summary.failed,
            "duration_ms": summary.duration_ms,
            "created_at": summary.created_at,
        }, ensure_ascii=False) + "\n")
    return summary.root_trace_id


def get_run(root_trace_id: str) -> dict | None:
    """按 root_trace_id 查询一次执行的摘要。"""
    path = os.path.join(RUNS_DIR, f"{root_trace_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_recent_runs(limit: int = 10) -> list[dict]:
    """列出最近 N 次执行。"""
    index_path = os.path.join(RUNS_DIR, "_index.jsonl")
    if not os.path.exists(index_path):
        return []
    with open(index_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    runs = [json.loads(line) for line in lines if line.strip()]
    runs.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return runs[:limit]


def list_failed_runs(limit: int = 10) -> list[dict]:
    """列出最近 N 次失败执行。"""
    return [r for r in list_recent_runs(limit * 10) if r.get("status") == "failed"][:limit]
