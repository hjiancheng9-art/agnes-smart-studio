"""工具调用日志 — 轻量 JSONL writer，给运行时评分提供数据源。

每次 ToolRegistry.execute() 追加一行到 output/tool_calls.jsonl：
    {"ts": 1719..., "tool": "read_file", "status": "ok",
     "duration_ms": 3.2, "args_keys": ["path"]}

设计原则：
    - 不记参数值（隐私/安全），只记参数 key 列表
    - 写入失败静默降级（日志不能阻塞工具执行）
    - 文件大小自限：超过 MAX_BYTES 自动 rotate（保留最近 N 条）
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from core.config import OUTPUT_DIR

__all__ = ["LOG_FILE", "MAX_BYTES", "MAX_LINES", "log_call", "load_recent", "clear_log"]

LOG_FILE: Path = OUTPUT_DIR / "tool_calls.jsonl"
MAX_BYTES = 5 * 1024 * 1024  # 5MB 上限，超过自动 rotate
MAX_LINES = 5000  # rotate 后保留最近这么多条

_write_lock = threading.Lock()


def log_call(name: str, status: str, duration_ms: float, args: dict[str, Any] | None = None) -> None:
    """追加一条调用记录。写入失败静默降级。

    Args:
        name: 工具名
        status: ok / arg_validation_failed / unknown_tool / exception
        duration_ms: 执行耗时（毫秒），失败时传 0.0
        args: 调用参数（只记 key 列表，不记 value）
    """
    record = {
        "ts": _now_ts(),
        "tool": name,
        "status": status,
        "duration_ms": round(float(duration_ms), 2),
        "args_keys": sorted(args.keys()) if isinstance(args, dict) else [],
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"
    try:
        with _write_lock:
            _maybe_rotate()
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(line)
    except OSError:
        # 日志失败绝不能影响工具执行
        pass


def load_recent(limit: int = 2000, tool_name: str | None = None) -> list[dict]:
    """读取最近的调用记录。

    Args:
        limit: 最多读多少条（从最新往前）
        tool_name: 可选，只读指定工具的记录

    Returns:
        list of dict，最新的在前。
    """
    if not LOG_FILE.exists():
        return []
    records: list[dict] = []
    try:
        with open(LOG_FILE, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if tool_name is not None and rec.get("tool") != tool_name:
            continue
        records.append(rec)
        if len(records) >= limit:
            break
    return records


def group_by_tool(limit: int = 2000) -> dict[str, list[dict]]:
    """读取最近调用并按工具名分组。

    Returns:
        {tool_name: [records]}，每个工具最多 limit 条。
    """
    all_records = load_recent(limit=limit * 10)  # 宽取再分组
    grouped: dict[str, list[dict]] = {}
    for rec in all_records:
        name = rec.get("tool", "")
        if not name:
            continue
        bucket = grouped.setdefault(name, [])
        if len(bucket) < limit:
            bucket.append(rec)
    return grouped


def clear_log() -> int:
    """清空日志文件，返回清除前的行数。"""
    cleared = 0
    try:
        with _write_lock:
            if LOG_FILE.exists():
                with open(LOG_FILE, encoding="utf-8") as fh:
                    cleared = sum(1 for _ in fh)
                LOG_FILE.write_text("", encoding="utf-8")
    except OSError:
        pass
    return cleared


# ── 内部 ────────────────────────────────────────────────────


def _now_ts() -> float:
    """当前时间戳（测试可 mock）。"""
    import time

    return time.time()


def _maybe_rotate() -> None:
    """文件过大时 rotate（保留最近 MAX_LINES 条）。调用方需持锁。"""
    try:
        if not LOG_FILE.exists():
            return
        if LOG_FILE.stat().st_size < MAX_BYTES:
            return
        # 读全部，保留尾部
        with open(LOG_FILE, encoding="utf-8") as fh:
            lines = fh.readlines()
        kept = lines[-MAX_LINES:]
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.writelines(kept)
    except OSError:
        pass
