"""
Policy Memory — CRUX 路由记忆与校准
===================================
记录历史路由决策、用户纠正、失败案例，用于校准信号权重。

功能:
1. 记录每次路由决策到 SQLite
2. 查询历史失败案例
3. 校准信号权重（基于历史准确率）
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RouteRecord:
    """单条路由记录"""
    request: str
    routed_mode: str
    expected_mode: str | None = None  # 用户纠正后的模式
    signal_scores: dict[str, float] | None = None
    latency: float = 0.0
    user_corrected: bool = False
    success: bool | None = None  # True=成功, False=失败, None=未确认
    timestamp: float = 0.0
    tags: list[str] | None = None
    error: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class PolicyMemory:
    """路由记忆存储 — 基于 SQLite"""

    TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS route_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request TEXT NOT NULL,
        routed_mode TEXT NOT NULL,
        expected_mode TEXT,
        signal_scores TEXT,
        latency REAL DEFAULT 0,
        user_corrected INTEGER DEFAULT 0,
        success INTEGER,
        timestamp REAL NOT NULL,
        tags TEXT,
        error TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_route_records_timestamp ON route_records(timestamp);
    CREATE INDEX IF NOT EXISTS idx_route_records_mode ON route_records(routed_mode);
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "policy_memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(self.TABLE_SQL)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PolicyMemory DB 初始化失败: {e}")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── 写入 ──

    def record(self, record: RouteRecord) -> int:
        """记录一条路由决策"""
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO route_records
                   (request, routed_mode, expected_mode, signal_scores,
                    latency, user_corrected, success, timestamp, tags, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.request[:500],
                    record.routed_mode,
                    record.expected_mode,
                    json.dumps(record.signal_scores, ensure_ascii=False) if record.signal_scores else None,
                    record.latency,
                    int(record.user_corrected),
                    int(record.success) if record.success is not None else None,
                    record.timestamp,
                    json.dumps(record.tags, ensure_ascii=False) if record.tags else None,
                    record.error[:500],
                ),
            )
            conn.commit()
            row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return row_id or 0
        except Exception as e:
            logger.warning(f"PolicyMemory 记录失败: {e}")
            return 0

    def record_route(
        self,
        request: str,
        routed_mode: str,
        signal_scores: dict[str, float] | None = None,
        latency: float = 0.0,
        tags: list[str] | None = None,
    ) -> int:
        """快捷记录路由"""
        return self.record(RouteRecord(
            request=request,
            routed_mode=routed_mode,
            signal_scores=signal_scores,
            latency=latency,
            tags=tags,
        ))

    def record_correction(self, request: str, routed_mode: str, expected_mode: str) -> int:
        """记录用户纠正"""
        return self.record(RouteRecord(
            request=request,
            routed_mode=routed_mode,
            expected_mode=expected_mode,
            user_corrected=True,
            success=False,
            tags=["user_correction"],
        ))

    def record_success(self, request: str, routed_mode: str) -> int:
        """记录路由成功"""
        return self.record(RouteRecord(
            request=request,
            routed_mode=routed_mode,
            success=True,
        ))

    # ── 读取 ──

    def load_failures(self, top_n: int = 50) -> list[RouteRecord]:
        """加载失败记录"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """SELECT * FROM route_records
                   WHERE success = 0 OR user_corrected = 1
                   ORDER BY timestamp DESC LIMIT ?""",
                (top_n,),
            ).fetchall()
            conn.close()
            return [self._row_to_record(r) for r in rows]
        except Exception as e:
            logger.warning(f"PolicyMemory 读取失败: {e}")
            return []

    def load_recent(self, top_n: int = 100) -> list[RouteRecord]:
        """加载最近记录"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM route_records ORDER BY timestamp DESC LIMIT ?",
                (top_n,),
            ).fetchall()
            conn.close()
            return [self._row_to_record(r) for r in rows]
        except Exception as e:
            logger.warning(f"PolicyMemory 读取失败: {e}")
            return []

    def get_accuracy(self, mode: str | None = None) -> float:
        """获取指定模式的历史准确率"""
        try:
            conn = self._get_conn()
            if mode:
                row = conn.execute(
                    """SELECT
                        CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS REAL)
                        / COUNT(*) as accuracy
                       FROM route_records
                       WHERE routed_mode = ? AND success IS NOT NULL""",
                    (mode,),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT
                        CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS REAL)
                        / COUNT(*) as accuracy
                       FROM route_records
                       WHERE success IS NOT NULL""",
                ).fetchone()
            conn.close()
            return row["accuracy"] if row and row["accuracy"] else 0.0
        except Exception:
            return 0.0

    def get_mode_distribution(self) -> dict[str, int]:
        """获取模式分布统计"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT routed_mode, COUNT(*) as cnt FROM route_records GROUP BY routed_mode"
            ).fetchall()
            conn.close()
            return {r["routed_mode"]: r["cnt"] for r in rows}
        except Exception:
            return {}

    def _row_to_record(self, row: sqlite3.Row) -> RouteRecord:
        return RouteRecord(
            request=row["request"],
            routed_mode=row["routed_mode"],
            expected_mode=row["expected_mode"],
            signal_scores=json.loads(row["signal_scores"]) if row["signal_scores"] else None,
            latency=row["latency"],
            user_corrected=bool(row["user_corrected"]),
            success=bool(row["success"]) if row["success"] is not None else None,
            timestamp=row["timestamp"],
            tags=json.loads(row["tags"]) if row["tags"] else None,
            error=row["error"] or "",
        )

    # ── 校准 ──

    def get_underperforming_modes(self, threshold: float = 0.7) -> list[tuple[str, float]]:
        """获取表现不佳的模式（准确率低于阈值）"""
        modes = ["FAST", "BALANCED", "DEEP", "SAFE", "RESEARCH", "CREATIVE"]
        result: list[tuple[str, float]] = []
        for m in modes:
            acc = self.get_accuracy(m)
            if 0 < acc < threshold:
                result.append((m, acc))
        return result

    def calibrate(self, router: Any) -> dict[str, Any]:
        """基于历史数据校准路由（输出建议，不自动修改权重）"""
        failures = self.load_failures(top_n=100)
        mode_dist = self.get_mode_distribution()

        # 分析失败模式
        correction_map: dict[str, int] = {}
        for f in failures:
            if f.expected_mode:
                key = f"{f.routed_mode}→{f.expected_mode}"
                correction_map[key] = correction_map.get(key, 0) + 1

        # 找出最常见的错误路由方向
        top_corrections = sorted(correction_map.items(), key=lambda x: -x[1])[:5]

        return {
            "total_records": sum(mode_dist.values()),
            "mode_distribution": mode_dist,
            "top_corrections": top_corrections,
            "underperforming_modes": self.get_underperforming_modes(),
        }

    def clear(self) -> None:
        """清空所有记录"""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM route_records")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"PolicyMemory 清空失败: {e}")
