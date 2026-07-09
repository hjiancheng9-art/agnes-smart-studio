"""
Learning Store — CRUX 学习记录存储
====================================
记录每次学习：从失败轨迹中提取的经验教训。

存储内容:
- episode_id: 学习周期 ID
- trace_run_id: 关联的轨迹 ID
- failure_type: 失败类型 (route_mismatch / plan_incomplete / critic_missed / repair_failed / verify_failed)
- diagnosis: 诊断结果
- policy_patch: 调参建议 (JSON)
- applied: 是否已应用
- effectiveness: 应用后的效果评分
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LearningRecord:
    """单条学习记录"""
    episode_id: str = ""
    trace_run_id: str = ""
    failure_type: str = ""   # route_mismatch / plan_incomplete / critic_missed / repair_failed / verify_failed
    request: str = ""
    routed_mode: str = ""
    expected_mode: str = ""
    diagnosis: str = ""       # 自然语言诊断
    severity: str = "medium"  # low / medium / high / critical
    root_cause: str = ""      # 根因一句话
    policy_patch: dict[str, Any] | None = None  # 调参建议
    applied: bool = False
    effectiveness: float = 0.0  # 0.0 ~ 1.0
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.episode_id:
            self.episode_id = str(uuid.uuid4())[:12]
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "trace_run_id": self.trace_run_id,
            "failure_type": self.failure_type,
            "request": self.request[:100],
            "routed_mode": self.routed_mode,
            "expected_mode": self.expected_mode,
            "diagnosis": self.diagnosis[:300],
            "severity": self.severity,
            "root_cause": self.root_cause[:200],
            "policy_patch": self.policy_patch,
            "applied": self.applied,
            "effectiveness": self.effectiveness,
        }


@dataclass
class LearningSummary:
    """学习汇总"""
    total_episodes: int = 0
    applied_count: int = 0
    failure_type_dist: dict[str, int] = field(default_factory=dict)
    avg_effectiveness: float = 0.0
    top_root_causes: list[tuple[str, int]] = field(default_factory=list)
    recent_improvement: float = 0.0  # 最近一周效果趋势


class LearningStore:
    """学习记录存储 — SQLite"""

    TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS learning_records (
        episode_id TEXT PRIMARY KEY,
        trace_run_id TEXT NOT NULL DEFAULT '',
        failure_type TEXT NOT NULL DEFAULT '',
        request TEXT NOT NULL DEFAULT '',
        routed_mode TEXT NOT NULL DEFAULT '',
        expected_mode TEXT NOT NULL DEFAULT '',
        diagnosis TEXT NOT NULL DEFAULT '',
        severity TEXT NOT NULL DEFAULT 'medium',
        root_cause TEXT NOT NULL DEFAULT '',
        policy_patch TEXT,
        applied INTEGER NOT NULL DEFAULT 0,
        effectiveness REAL NOT NULL DEFAULT 0.0,
        timestamp REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_learning_failure ON learning_records(failure_type);
    CREATE INDEX IF NOT EXISTS idx_learning_applied ON learning_records(applied);
    CREATE INDEX IF NOT EXISTS idx_learning_ts ON learning_records(timestamp);
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "learning_store.db"
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
            logger.warning(f"LearningStore DB 初始化失败: {e}")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, record: LearningRecord) -> str:
        """保存一条学习记录"""
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO learning_records
                   (episode_id, trace_run_id, failure_type, request,
                    routed_mode, expected_mode, diagnosis, severity,
                    root_cause, policy_patch, applied, effectiveness, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.episode_id,
                    record.trace_run_id,
                    record.failure_type,
                    record.request[:500],
                    record.routed_mode,
                    record.expected_mode,
                    record.diagnosis[:1000],
                    record.severity,
                    record.root_cause[:500],
                    json.dumps(record.policy_patch, ensure_ascii=False) if record.policy_patch else None,
                    int(record.applied),
                    record.effectiveness,
                    record.timestamp,
                ),
            )
            conn.commit()
            conn.close()
            return record.episode_id
        except Exception as e:
            logger.warning(f"LearningStore 记录失败: {e}")
            return record.episode_id

    def get(self, episode_id: str) -> LearningRecord | None:
        """获取单条学习记录"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM learning_records WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
            conn.close()
            if row:
                return self._row_to_record(row)
            return None
        except Exception:
            return None

    def query(self, failure_type: str | None = None,
              severity: str | None = None,
              applied: bool | None = None,
              limit: int = 50) -> list[LearningRecord]:
        """查询学习记录"""
        try:
            conn = self._get_conn()
            sql = "SELECT * FROM learning_records WHERE 1=1"
            params: list[Any] = []
            if failure_type:
                sql += " AND failure_type = ?"
                params.append(failure_type)
            if severity:
                sql += " AND severity = ?"
                params.append(severity)
            if applied is not None:
                sql += " AND applied = ?"
                params.append(int(applied))
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [self._row_to_record(r) for r in rows]
        except Exception:
            return []

    def mark_applied(self, episode_id: str, effectiveness: float = 0.0) -> bool:
        """标记调参已应用"""
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE learning_records SET applied = 1, effectiveness = ? WHERE episode_id = ?",
                (effectiveness, episode_id),
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def get_summary(self) -> LearningSummary:
        """获取学习汇总"""
        summary = LearningSummary()
        try:
            conn = self._get_conn()
            # Total
            summary.total_episodes = conn.execute(
                "SELECT COUNT(*) as c FROM learning_records"
            ).fetchone()["c"]
            # Applied
            summary.applied_count = conn.execute(
                "SELECT COUNT(*) as c FROM learning_records WHERE applied = 1"
            ).fetchone()["c"]
            # Failure type distribution
            rows = conn.execute(
                "SELECT failure_type, COUNT(*) as c FROM learning_records GROUP BY failure_type ORDER BY c DESC"
            ).fetchall()
            summary.failure_type_dist = {r["failure_type"]: r["c"] for r in rows if r["failure_type"]}
            # Avg effectiveness
            avg = conn.execute(
                "SELECT AVG(effectiveness) as avg FROM learning_records WHERE applied = 1 AND effectiveness > 0"
            ).fetchone()["avg"]
            summary.avg_effectiveness = round(avg or 0.0, 3)
            # Top root causes
            rows = conn.execute(
                "SELECT root_cause, COUNT(*) as c FROM learning_records WHERE root_cause != '' GROUP BY root_cause ORDER BY c DESC LIMIT 5"
            ).fetchall()
            summary.top_root_causes = [(r["root_cause"], r["c"]) for r in rows]
            conn.close()
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)
        return summary

    def clear(self) -> None:
        """清空所有记录"""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM learning_records")
            conn.commit()
            conn.close()
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)

    def _row_to_record(self, row: sqlite3.Row) -> LearningRecord:
        try:
            policy_patch_raw = row["policy_patch"]
        except (IndexError, KeyError):
            policy_patch_raw = None
        return LearningRecord(
            episode_id=row["episode_id"],
            trace_run_id=row["trace_run_id"] or "",
            failure_type=row["failure_type"] or "",
            request=row["request"] or "",
            routed_mode=row["routed_mode"] or "",
            expected_mode=row["expected_mode"] or "",
            diagnosis=row["diagnosis"] or "",
            severity=row["severity"] or "medium",
            root_cause=row["root_cause"] or "",
            policy_patch=json.loads(policy_patch_raw) if policy_patch_raw else None,
            applied=bool(row["applied"]),
            effectiveness=row["effectiveness"] or 0.0,
            timestamp=row["timestamp"],
        )
