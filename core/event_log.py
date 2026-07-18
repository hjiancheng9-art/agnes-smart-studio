"""EventLog — CRUX 可观测性地基（基于 GPT 架构审计建议）

设计决策（ADR-0003）：
- EventLog 先行（非 Metrics 先行）：EventLog 是 raw data，metrics/trace 是它的 projection
- 存储：内存 ring buffer (1000条) + 异步批量写 SQLite（每 5s 或 100 条 flush）
- 避免热路径阻塞：emit() 只写 ring buffer，flush 在后台线程
- Schema: event_id / timestamp / session_id / intent / tool / status / duration_ms / error_type / metadata

后续从 EventLog 可构建：
- Metrics（成功率、延迟分布、工具使用频次）
- Trace correlation（同一次请求的多工具调用链）
- Self-heal 假修复检测（pre/post state comparison）
- TRM 成长引擎冷启动数据
"""

import json
import os
import sqlite3
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Constants ──────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "crux_event_log.sqlite")
RING_BUFFER_SIZE = 1000
FLUSH_INTERVAL_SEC = 5
FLUSH_BATCH_SIZE = 100


# ── Data Model ─────────────────────────────────────────────
@dataclass
class EventRecord:
    """Single event in the CRUX event log."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: str = ""
    intent: str = ""  # search | review | execute | think | generate | status
    tool: str = ""  # tool name
    status: str = ""  # success | failure | fallback | timeout
    duration_ms: int = 0
    error_type: str = ""
    metadata: dict = field(default_factory=dict)

    def to_row(self) -> tuple:
        return (
            self.event_id,
            self.timestamp,
            self.session_id,
            self.intent,
            self.tool,
            self.status,
            self.duration_ms,
            self.error_type,
            json.dumps(self.metadata, ensure_ascii=False),
        )


# ── EventLog Engine ────────────────────────────────────────
class EventLog:
    """Thread-safe event log with ring buffer + async SQLite flush.

    Usage:
        log = EventLog(session_id="abc123")
        log.record(intent="generate", tool="generate_image",
                   status="success", duration_ms=2340,
                   metadata={"model": "deepseek-v4-flash"})

        # Metrics query:
        stats = log.query_metrics(intent="generate", hours=24)
    """

    def __init__(self, session_id: str = ""):
        self._session_id = session_id
        self._buffer: deque[EventRecord] = deque(maxlen=RING_BUFFER_SIZE)
        self._lock = threading.Lock()
        self._flush_thread: threading.Thread | None = None
        self._running = False
        self._db_ready = False

        os.makedirs(DATA_DIR, exist_ok=True)
        self._init_db()
        self._start_flush_thread()

    # ── DB Init ─────────────────────────────────────────
    def _init_db(self):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS event_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT UNIQUE NOT NULL,
                        timestamp TEXT NOT NULL,
                        session_id TEXT DEFAULT '',
                        intent TEXT DEFAULT '',
                        tool TEXT DEFAULT '',
                        status TEXT DEFAULT '',
                        duration_ms INTEGER DEFAULT 0,
                        error_type TEXT DEFAULT '',
                        metadata TEXT DEFAULT '{}',
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_event_log_session
                    ON event_log(session_id, timestamp)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_event_log_tool
                    ON event_log(tool, status, timestamp)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_event_log_intent
                    ON event_log(intent, timestamp)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_event_log_timestamp
                    ON event_log(timestamp)
                """)
            self._db_ready = True
        except Exception as e:
            print(f"[EventLog] DB init failed: {e}")
            self._db_ready = False

    # ── Flush Thread ────────────────────────────────────
    def _start_flush_thread(self):
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def _flush_loop(self):
        while self._running:
            time.sleep(FLUSH_INTERVAL_SEC)
            self._flush()

    def _flush(self):
        """Drain ring buffer to SQLite. Thread-safe."""
        if not self._db_ready:
            return

        with self._lock:
            if not self._buffer:
                return
            # Take up to FLUSH_BATCH_SIZE records
            batch = []
            while self._buffer and len(batch) < FLUSH_BATCH_SIZE:
                batch.append(self._buffer.popleft())

        if batch:
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.executemany(
                        """INSERT OR IGNORE INTO event_log
                           (event_id, timestamp, session_id, intent, tool, status,
                            duration_ms, error_type, metadata)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        [r.to_row() for r in batch],
                    )
            except Exception as e:
                print(f"[EventLog] flush error: {e}")

    def force_flush(self):
        """Force immediate flush (call before shutdown)."""
        self._flush()

    # ── Record ──────────────────────────────────────────
    def record(self, **kwargs):
        """Record an event. Lightweight — just appends to ring buffer.

        Args:
            intent: search|review|execute|think|generate|status
            tool: tool name
            status: success|failure|fallback|timeout
            duration_ms: execution time in ms
            error_type: exception type if failed
            metadata: extra context dict
        """
        event = EventRecord(
            session_id=self._session_id,
            intent=kwargs.get("intent", ""),
            tool=kwargs.get("tool", ""),
            status=kwargs.get("status", ""),
            duration_ms=kwargs.get("duration_ms", 0),
            error_type=kwargs.get("error_type", ""),
            metadata=kwargs.get("metadata", {}),
        )
        with self._lock:
            self._buffer.append(event)

        # Auto-flush if buffer is full
        if len(self._buffer) >= FLUSH_BATCH_SIZE:
            self._flush()

    # ── Query ───────────────────────────────────────────
    def query_metrics(self, intent: str = "", tool: str = "", hours: int = 24) -> dict:
        """Aggregate metrics from EventLog."""
        self._flush()  # ensure recent data is flushed

        if not self._db_ready:
            return {"error": "db not ready"}

        conditions = ["timestamp >= datetime('now', ?)"]
        params: list[Any] = [f"-{hours} hours"]

        if intent:
            conditions.append("intent = ?")
            params.append(intent)
        if tool:
            conditions.append("tool = ?")
            params.append(tool)

        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row

                # Basic stats
                row = conn.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success_count,
                        SUM(CASE WHEN status='failure' THEN 1 ELSE 0 END) as failure_count,
                        SUM(CASE WHEN status='fallback' THEN 1 ELSE 0 END) as fallback_count,
                        SUM(CASE WHEN status='timeout' THEN 1 ELSE 0 END) as timeout_count,
                        AVG(duration_ms) as avg_duration_ms,
                        MIN(duration_ms) as min_duration_ms,
                        MAX(duration_ms) as max_duration_ms
                    FROM event_log WHERE {where}""",
                    params,
                ).fetchone()

                # Per-tool breakdown
                tool_rows = conn.execute(
                    """SELECT tool, COUNT(*) as cnt,
                        SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate,
                        AVG(duration_ms) as avg_ms
                    FROM event_log WHERE {where}
                    GROUP BY tool ORDER BY cnt DESC LIMIT 20""",
                    params,
                ).fetchall()

                # Per-intent breakdown
                intent_rows = conn.execute(
                    """SELECT intent, COUNT(*) as cnt,
                        SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate,
                        AVG(duration_ms) as avg_ms
                    FROM event_log WHERE {where}
                    GROUP BY intent ORDER BY cnt DESC""",
                    params,
                ).fetchall()

                return {
                    "total": row["total"],
                    "success_count": row["success_count"],
                    "failure_count": row["failure_count"],
                    "fallback_count": row["fallback_count"],
                    "timeout_count": row["timeout_count"],
                    "success_rate": round(row["success_count"] / max(row["total"], 1) * 100, 1),
                    "avg_duration_ms": round(row["avg_duration_ms"] or 0, 1),
                    "min_duration_ms": row["min_duration_ms"],
                    "max_duration_ms": row["max_duration_ms"],
                    "by_tool": [dict(r) for r in tool_rows],
                    "by_intent": [dict(r) for r in intent_rows],
                }
        except Exception as e:
            return {"error": str(e)}

    def query_events(
        self, session_id: str = "", intent: str = "", tool: str = "", status: str = "", limit: int = 50
    ) -> list[dict]:
        """Query raw events."""
        self._flush()

        conditions = ["1=1"]
        params: list[Any] = []
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if intent:
            conditions.append("intent = ?")
            params.append(intent)
        if tool:
            conditions.append("tool = ?")
            params.append(tool)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions)

        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"""SELECT * FROM event_log WHERE {where}
                    ORDER BY timestamp DESC LIMIT ?""",  # nosec B608 — values are parameterized
                    [*params, limit],
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            return [{"error": str(e)}]

    def recent_failures(self, hours: int = 1) -> list[dict]:
        """Get recent failures for self-heal analysis."""
        self._flush()
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT * FROM event_log
                    WHERE status = 'failure'
                    AND timestamp >= datetime('now', ?)
                    ORDER BY timestamp DESC LIMIT 30""",
                    [f"-{hours} hours"],
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            return [{"error": str(e)}]

    def shutdown(self):
        """Graceful shutdown: flush and stop thread."""
        self._running = False
        self._flush()
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=3)

    @property
    def buffer_size(self) -> int:
        with self._lock:
            return len(self._buffer)


# ── Singleton ────────────────────────────────────────────
_event_log_instance: EventLog | None = None


def get_event_log(session_id: str = "") -> EventLog:
    """Get or create the global EventLog instance."""
    global _event_log_instance
    if _event_log_instance is None:
        _event_log_instance = EventLog(session_id=session_id)
    return _event_log_instance


def record_event(**kwargs):
    """Convenience: record an event to the global log."""
    get_event_log().record(**kwargs)
