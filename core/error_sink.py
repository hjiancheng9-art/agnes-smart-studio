"""CRUX ErrorSink — 统一异常记录器

让所有 `except Exception:` 不再静默消失，而是：
1. 记录到 ErrorSink（内存 + SQLite）
2. 保留原始控制流（不抛中断）
3. 提供诊断接口：最近错误 / 按模块统计 / 按严重度过滤

用法:
    from core.error_sink import err
    err.record("module_name", "干啥失败了", e)
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════
# Data
# ═══════════════════════════════════════════════════════════


@dataclass
class ErrorRecord:
    timestamp: str
    module: str  # e.g. "cleanup_manager"
    operation: str  # e.g. "scan/_is_git_tracked"
    error_type: str  # e.g. "FileNotFoundError"
    message: str  # first 200 chars
    traceback: str  # last 500 chars
    context: dict  # extra info
    severity: str = "warning"  # debug / info / warning / error / critical


# ═══════════════════════════════════════════════════════════
# ErrorSink
# ═══════════════════════════════════════════════════════════


class ErrorSink:
    """线程安全的错误收集器。记录 + 统计 + 诊断，三合一。"""

    def __init__(self, db_path: str | Path | None = None):
        self._records: list[ErrorRecord] = []
        self._db_path: Path | None = None

        if db_path:
            self._db_path = Path(db_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_sink (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                module TEXT NOT NULL,
                operation TEXT NOT NULL,
                error_type TEXT,
                message TEXT,
                traceback TEXT,
                context TEXT,
                severity TEXT DEFAULT 'warning'
            )
        """)
        conn.commit()
        conn.close()

    def record(
        self,
        module: str,
        operation: str,
        error: BaseException | str,
        context: dict | None = None,
        severity: str = "warning",
    ) -> ErrorRecord:
        """记录一个错误/异常。不抛异常。"""
        now = datetime.datetime.now().isoformat()

        if isinstance(error, BaseException):
            error_type = type(error).__name__
            msg = str(error)[:300]
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            tb = tb[-1000:]  # keep last 1000 chars
        else:
            error_type = "string"
            msg = str(error)[:300]
            tb = ""

        record = ErrorRecord(
            timestamp=now,
            module=module,
            operation=operation,
            error_type=error_type,
            message=msg,
            traceback=tb,
            context=context or {},
            severity=severity,
        )

        self._records.append(record)
        self._persist(record)
        return record

    def _persist(self, record: ErrorRecord):
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                """INSERT INTO error_sink (timestamp, module, operation, error_type, message,
                   traceback, context, severity) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.timestamp,
                    record.module,
                    record.operation,
                    record.error_type,
                    record.message,
                    record.traceback,
                    json.dumps(record.context, ensure_ascii=False),
                    record.severity,
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # 不要因为记录错误本身再出问题

    # ── 查询 ──────────────────────────────────────────────

    def recent(self, n: int = 10, severity: str | None = None) -> list[ErrorRecord]:
        """最近 n 条错误"""
        records = self._records[-n:]
        if severity:
            records = [r for r in records if r.severity == severity]
        return records

    def by_module(self, module: str) -> list[ErrorRecord]:
        """按模块筛选"""
        return [r for r in self._records if r.module == module]

    def stats(self) -> dict:
        """各维度统计"""
        from collections import Counter

        by_module = Counter(r.module for r in self._records)
        by_severity = Counter(r.severity for r in self._records)
        by_type = Counter(r.error_type for r in self._records)

        return {
            "total": len(self._records),
            "by_module": dict(by_module.most_common(10)),
            "by_severity": dict(by_severity),
            "by_error_type": dict(by_type.most_common(10)),
        }

    def clear(self):
        """清空内存记录"""
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


# ═══════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════

# 默认使用项目 .crux/error_sink.sqlite
_default_path = Path(__file__).resolve().parent.parent / ".crux" / "error_sink.sqlite"

# 全局 ErrorSink 实例，所有模块共享
err = ErrorSink(db_path=_default_path)


# ═══════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════


def catch(
    error: BaseException | None,
    module: str,
    operation: str,
    context: dict | None = None,
    severity: str = "warning",
    fallback: Any = None,
) -> Any:
    """记录异常到 ErrorSink，返回 fallback 值。

    替代 `except Exception: pass` 的三行降级写法:

        except Exception as e:
            from core.error_sink import catch; catch(e, "module", "operation")
    """
    if error is not None:
        err.record(module, operation, error, context, severity)
    return fallback


def print_error_summary():
    """打印当前 ErrorSink 摘要"""
    stats = err.stats()
    print("\n=== ErrorSink 统计 ===")
    print(f"  总计: {stats['total']} 条")
    print(f"  按严重度: {stats['by_severity']}")
    print(f"  按类型: {stats['by_error_type']}")
    print("  按模块: ")
    for mod, cnt in stats["by_module"].items():
        print(f"    {mod}: {cnt}")
    print()

    if stats["total"] > 0:
        print("最近 5 条:")
        for r in err.recent(5):
            print(f"  [{r.severity}] {r.module}/{r.operation}: {r.error_type} — {r.message[:80]}")
