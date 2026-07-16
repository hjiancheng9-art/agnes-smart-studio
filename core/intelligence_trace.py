"""
Intelligence Trace — CRUX 全链路可观测 / 可回放
=============================================
记录每次复杂任务的完整轨迹：路由决策 → 各步骤输入输出 → 失败/成功。

每条轨迹包含:
- run_id: 唯一标识
- user_request: 原始请求
- mode: 路由模式
- status: 最终状态 (pass/fail/partial)
- started_at / ended_at: 时间
- steps: 每一步的 name / status / duration / input_summary / output_summary / error
- critique_report: 审查报告摘要
- trace_json: 完整轨迹 JSON（用于回放分析）

存储: SQLite，支持 query / replay / export
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TraceStep:
    """轨迹中的单步"""
    name: str
    status: str = "pending"
    duration: float = 0.0
    input_summary: str = ""
    output_summary: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration": round(self.duration, 3),
            "input_summary": self.input_summary[:200],
            "output_summary": self.output_summary[:500],
            "error": self.error[:300] if self.error else "",
        }


@dataclass
class TraceRecord:
    """完整轨迹记录"""
    user_request: str
    mode: str
    run_id: str = ""
    status: str = "running"  # running / pass / fail / partial
    steps: list[TraceStep] = field(default_factory=list)
    critique_summary: str = ""
    signal_scores: dict[str, float] | None = None
    started_at: float = 0.0
    ended_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.run_id:
            self.run_id = str(uuid.uuid4())[:12]
        if not self.started_at:
            self.started_at = time.time()

    @property
    def total_duration(self) -> float:
        if self.ended_at and self.started_at:
            return self.ended_at - self.started_at
        return 0.0

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def failed_steps(self) -> list[TraceStep]:
        return [s for s in self.steps if s.status == "failed"]

    @property
    def success_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "success")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "user_request": self.user_request[:200],
            "mode": self.mode,
            "status": self.status,
            "total_duration": round(self.total_duration, 2),
            "step_count": self.step_count,
            "success_count": self.success_count,
            "failed_count": len(self.failed_steps),
            "critique_summary": self.critique_summary[:300],
            "signal_scores": self.signal_scores,
            "steps": [s.to_dict() for s in self.steps],
            "started_at": datetime.fromtimestamp(self.started_at).isoformat(),
            "ended_at": datetime.fromtimestamp(self.ended_at).isoformat() if self.ended_at else "",
            "metadata": self.metadata,
        }


class TraceStore:
    """轨迹存储 — SQLite"""

    TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS intelligence_traces (
        run_id TEXT PRIMARY KEY,
        user_request TEXT NOT NULL,
        mode TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        started_at REAL NOT NULL,
        ended_at REAL,
        total_duration REAL,
        step_count INTEGER DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        failed_count INTEGER DEFAULT 0,
        critique_summary TEXT,
        trace_json TEXT,
        metadata_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_traces_status ON intelligence_traces(status);
    CREATE INDEX IF NOT EXISTS idx_traces_mode ON intelligence_traces(mode);
    CREATE INDEX IF NOT EXISTS idx_traces_started ON intelligence_traces(started_at);
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "intelligence_traces.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(self.TABLE_SQL)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"TraceStore DB 初始化失败: {e}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, trace: TraceRecord) -> str:
        """保存一条轨迹"""
        try:
            conn = self._connect()
            conn.execute(
                """INSERT OR REPLACE INTO intelligence_traces
                   (run_id, user_request, mode, status, started_at, ended_at,
                    total_duration, step_count, success_count, failed_count,
                    critique_summary, trace_json, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace.run_id,
                    trace.user_request[:500],
                    trace.mode,
                    trace.status,
                    trace.started_at,
                    trace.ended_at or 0,
                    trace.total_duration,
                    trace.step_count,
                    trace.success_count,
                    len(trace.failed_steps),
                    trace.critique_summary[:500],
                    json.dumps(trace.to_dict(), ensure_ascii=False),
                    json.dumps(trace.metadata, ensure_ascii=False) if trace.metadata else None,
                ),
            )
            conn.commit()
            conn.close()
            return trace.run_id
        except Exception as e:
            logger.warning(f"TraceStore 记录失败: {e}")
            return trace.run_id

    def get(self, run_id: str) -> dict[str, Any] | None:
        """获取单条轨迹"""
        try:
            conn = self._connect()
            row = conn.execute(
                "SELECT trace_json FROM intelligence_traces WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            conn.close()
            if row and row["trace_json"]:
                return json.loads(row["trace_json"])
            return None
        except Exception:
            return None

    def query(self, status: str | None = None, mode: str | None = None,
              limit: int = 50) -> list[dict[str, Any]]:
        """查询轨迹"""
        try:
            conn = self._connect()
            sql = "SELECT trace_json FROM intelligence_traces WHERE 1=1"
            params: list[Any] = []
            if status:
                sql += " AND status = ?"
                params.append(status)
            if mode:
                sql += " AND mode = ?"
                params.append(mode)
            sql += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            results = []
            for row in rows:
                if row["trace_json"]:
                    results.append(json.loads(row["trace_json"]))
            return results
        except Exception:
            return []

    def get_stats(self) -> dict[str, Any]:
        """获取轨迹统计"""
        try:
            conn = self._connect()
            total = conn.execute("SELECT COUNT(*) as c FROM intelligence_traces").fetchone()["c"]
            passed = conn.execute(
                "SELECT COUNT(*) as c FROM intelligence_traces WHERE status = 'pass'"
            ).fetchone()["c"]
            failed = conn.execute(
                "SELECT COUNT(*) as c FROM intelligence_traces WHERE status = 'fail'"
            ).fetchone()["c"]
            avg_duration = conn.execute(
                "SELECT AVG(total_duration) as avg FROM intelligence_traces WHERE total_duration > 0"
            ).fetchone()["avg"] or 0
            conn.close()
            return {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": round(passed / total * 100, 1) if total else 0,
                "avg_duration": round(avg_duration, 2),
            }
        except Exception:
            return {"total": 0, "passed": 0, "failed": 0}

    def export(self, limit: int = 100) -> list[dict[str, Any]]:
        """导出轨迹列表"""
        return self.query(limit=limit)

    def clear(self) -> None:
        """清空"""
        try:
            conn = self._connect()
            conn.execute("DELETE FROM intelligence_traces")
            conn.commit()
            conn.close()
        except Exception:
            logger.debug("Exception in intelligence_trace", exc_info=True)


# ── 全局单例 ──
_default_store: TraceStore | None = None


def get_trace_store() -> TraceStore:
    global _default_store
    if _default_store is None:
        _default_store = TraceStore()
    return _default_store
