"""Session Task Tracker — SQLite 持久化任务追踪。

借鉴 Copilot CLI 的 SQL 会话数据库设计：
- todos 表（任务状态管理）
- todo_deps 表（任务依赖关系）
- inbox_entries 表（消息收件箱，类似 Copilot inbox）

与 session_mgr.py 互补：
- session_mgr.py → 保存完整对话历史（JSON）
- session_tracker.py → 追踪任务粒度状态（SQL）
"""

import contextlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "SESSION_TRACKER_TOOL_DEFS",
    "SESSION_TRACKER_EXECUTOR_MAP",
    "SessionTracker",
    "TodoStatus",
    "TodoItem",
    "get_tracker",
]

DB_DIR = Path(__file__).resolve().parent.parent / "output"
DB_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB = DB_DIR / "session_tracker.db"

# ── 状态枚举 ──

class TodoStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TodoItem:
    id: int = 0
    session_id: str = ""
    title: str = ""
    description: str = ""
    status: str = TodoStatus.PENDING
    priority: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    completed_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL
);

CREATE TABLE IF NOT EXISTS todo_deps (
    todo_id INTEGER NOT NULL,
    depends_on_id INTEGER NOT NULL,
    PRIMARY KEY (todo_id, depends_on_id),
    FOREIGN KEY (todo_id) REFERENCES todos(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_id) REFERENCES todos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inbox_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT DEFAULT 'user',
    created_at REAL NOT NULL,
    acknowledged INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_todos_session ON todos(session_id);
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
CREATE INDEX IF NOT EXISTS idx_inbox_session ON inbox_entries(session_id);
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
"""


class SessionTracker:
    """SQLite 会话任务追踪器 — 全局单例（线程安全）。"""

    _instance: "SessionTracker | None" = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = ""):
        self.db_path = str(db_path or DEFAULT_DB)
        self._local = threading.local()
        with self._get_conn() as conn:
            conn.executescript(_SCHEMA_SQL)

    @classmethod
    def get_instance(cls) -> "SessionTracker":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程本地连接。"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def close(self) -> None:
        """关闭线程本地的数据库连接。"""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            with contextlib.suppress(Exception):
                self._local.conn.close()
            self._local.conn = None

    # ── Todos CRUD ──

    def add_todo(
        self, session_id: str, title: str,
        description: str = "", priority: int = 0,
    ) -> int:
        now = time.time()
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO todos (session_id, title, description, status, priority, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (session_id, title, description, TodoStatus.PENDING, priority, now, now),
            )
            return cur.lastrowid  # pyright: ignore[reportReturnType]

    def get_todos(self, session_id: str = "", status: str = "") -> list[TodoItem]:
        with self._get_conn() as conn:
            if session_id and status:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE session_id=? AND status=? ORDER BY priority DESC, created_at",
                    (session_id, status),
                ).fetchall()
            elif session_id:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE session_id=? ORDER BY priority DESC, created_at",
                    (session_id,),
                ).fetchall()
            elif status:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE status=? ORDER BY priority DESC, created_at",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM todos ORDER BY priority DESC, created_at").fetchall()

            return [TodoItem(**dict(r)) for r in rows]

    def update_todo(self, todo_id: int, **kwargs) -> bool:
        allowed = {"title", "description", "status", "priority"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        updates["updated_at"] = time.time()
        if updates.get("status") in (TodoStatus.COMPLETED, TodoStatus.FAILED):
            updates["completed_at"] = time.time()

        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [todo_id]
        with self._get_conn() as conn:
            cur = conn.execute(f"UPDATE todos SET {set_clause} WHERE id=?", values)
            return cur.rowcount > 0

    def delete_todo(self, todo_id: int) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM todos WHERE id=?", (todo_id,))
            return cur.rowcount > 0

    # ── 依赖关系 ──

    def add_dep(self, todo_id: int, depends_on_id: int) -> bool:
        try:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO todo_deps (todo_id, depends_on_id) VALUES (?,?)",
                    (todo_id, depends_on_id),
                )
                return cur.rowcount > 0
        except sqlite3.IntegrityError:
            return False

    def get_blocked_todos(self, session_id: str) -> list[int]:
        """返回被未完成依赖阻塞的 todo ID。"""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT DISTINCT t.id FROM todos t
                JOIN todo_deps d ON t.id = d.todo_id
                JOIN todos dep ON d.depends_on_id = dep.id
                WHERE t.session_id = ?
                  AND t.status = 'pending'
                  AND dep.status NOT IN ('completed', 'cancelled')
            """, (session_id,)).fetchall()
            return [r[0] for r in rows]

    # ── 收件箱 ──

    def add_inbox(self, session_id: str, content: str, source: str = "user"):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO inbox_entries (session_id, content, source, created_at) VALUES (?,?,?,?)",
                (session_id, content, source, time.time()),
            )

    def get_unacknowledged(self, session_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM inbox_entries WHERE session_id=? AND acknowledged=0 ORDER BY created_at",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def ack_inbox(self, entry_id: int):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE inbox_entries SET acknowledged=1 WHERE id=?",
                (entry_id,),
            )

    # ── 统计 ──

    def stats(self, session_id: str = "") -> dict:
        with self._get_conn() as conn:
            if session_id:
                total = conn.execute("SELECT COUNT(*) FROM todos WHERE session_id=?", (session_id,)).fetchone()[0]
                by_status = {
                    r[0]: r[1]
                    for r in conn.execute(
                        "SELECT status, COUNT(*) FROM todos WHERE session_id=? GROUP BY status",
                        (session_id,),
                    ).fetchall()
                }
            else:
                total = conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0]
                by_status = {
                    r[0]: r[1]
                    for r in conn.execute("SELECT status, COUNT(*) FROM todos GROUP BY status").fetchall()
                }
            return {
                "total": total,
                "by_status": by_status,
                "blocked": len(self.get_blocked_todos(session_id)) if session_id else 0,
            }


# ── 全局实例 ──

def get_tracker() -> SessionTracker:
    return SessionTracker.get_instance()


# ── ToolRegistry 兼容定义 ──

def _exec_todo_add(args: dict) -> str:
    t = get_tracker()
    sid = args.get("session_id", "default")
    tid = t.add_todo(
        sid,
        args.get("title", ""),
        args.get("description", ""),
        args.get("priority", 0),
    )
    return json.dumps({"ok": True, "todo_id": tid})


def _exec_todo_list(args: dict) -> str:
    t = get_tracker()
    todos = t.get_todos(
        args.get("session_id", ""),
        args.get("status", ""),
    )
    return json.dumps({"ok": True, "todos": [td.to_dict() for td in todos]}, ensure_ascii=False)


def _exec_todo_update(args: dict) -> str:
    t = get_tracker()
    todo_id = args.get("todo_id", 0)
    kwargs = {}
    for k in ("title", "description", "status", "priority"):
        if k in args:
            kwargs[k] = args[k]
    ok = t.update_todo(todo_id, **kwargs)
    return json.dumps({"ok": ok})


def _exec_todo_delete(args: dict) -> str:
    t = get_tracker()
    ok = t.delete_todo(args.get("todo_id", 0))
    return json.dumps({"ok": ok})


def _exec_todo_dep(args: dict) -> str:
    t = get_tracker()
    ok = t.add_dep(args.get("todo_id", 0), args.get("depends_on_id", 0))
    return json.dumps({"ok": ok})


def _exec_todo_blocked(args: dict) -> str:
    t = get_tracker()
    blocked = t.get_blocked_todos(args.get("session_id", "default"))
    return json.dumps({"blocked": blocked})


def _exec_todo_stats(args: dict) -> str:
    t = get_tracker()
    s = t.stats(args.get("session_id", ""))
    return json.dumps(s)


SESSION_TRACKER_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "todo_add",
            "description": "创建新任务。借鉴 Copilot CLI 的 SQL todos 表设计，持久化到 SQLite。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID（默认 default）"},
                    "title": {"type": "string", "description": "任务标题"},
                    "description": {"type": "string", "description": "任务描述"},
                    "priority": {"type": "integer", "description": "优先级（越大越优先，默认0）"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_list",
            "description": "列出任务。可按会话ID和状态过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID过滤（空=所有）"},
                    "status": {"type": "string", "description": "状态过滤：pending|in_progress|completed|failed|cancelled"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_update",
            "description": "更新任务状态/标题/优先级。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer", "description": "任务ID"},
                    "status": {"type": "string", "description": "新状态"},
                    "title": {"type": "string", "description": "新标题"},
                    "priority": {"type": "integer", "description": "新优先级"},
                },
                "required": ["todo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_delete",
            "description": "删除任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer", "description": "任务ID"},
                },
                "required": ["todo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_dep",
            "description": "添加任务依赖关系。todo_id 依赖 depends_on_id 完成后才能开始。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer", "description": "任务ID"},
                    "depends_on_id": {"type": "integer", "description": "依赖的任务ID"},
                },
                "required": ["todo_id", "depends_on_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_blocked",
            "description": "列出被阻塞的任务（依赖未完成）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID（默认 default）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_stats",
            "description": "任务统计：按状态汇总 + 阻塞计数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID过滤（空=全局）"},
                },
            },
        },
    },
]

SESSION_TRACKER_EXECUTOR_MAP = {
    "todo_add": lambda **kw: _exec_todo_add(kw),
    "todo_list": lambda **kw: _exec_todo_list(kw),
    "todo_update": lambda **kw: _exec_todo_update(kw),
    "todo_delete": lambda **kw: _exec_todo_delete(kw),
    "todo_dep": lambda **kw: _exec_todo_dep(kw),
    "todo_blocked": lambda **kw: _exec_todo_blocked(kw),
    "todo_stats": lambda **kw: _exec_todo_stats(kw),
}
