"""Run Replay — 离线复盘失败执行路径。"""

import json
import os
import time
from typing import Any

from core.config import OUTPUT_DIR

REPLAY_DIR = os.path.join(OUTPUT_DIR, "replays")
os.makedirs(REPLAY_DIR, exist_ok=True)


def save_run_replay(root_trace_id: str, summary: dict, log: list, tasks: list[dict]) -> str:
    """保存一次完整 run 的快照用于复盘。"""
    replay = {
        "root_trace_id": root_trace_id,
        "saved_at": time.time(),
        "summary": summary,
        "log": log[-100:],
        "tasks": [
            {
                "id": t.get("id", ""),
                "status": t.get("status", ""),
                "trace_id": t.get("trace_id", ""),
                "result_preview": (t.get("result", "") or "")[:200],
                "started_at": t.get("started_at", 0),
                "finished_at": t.get("finished_at", 0),
            }
            for t in tasks
        ],
    }
    path = os.path.join(REPLAY_DIR, f"{root_trace_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(replay, f, ensure_ascii=False, indent=2)
    return path


def load_replay(root_trace_id: str) -> dict | None:
    """加载指定 run 的复盘数据。"""
    path = os.path.join(REPLAY_DIR, f"{root_trace_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_replays(limit: int = 10) -> list[dict]:
    """列出最近保存的复盘记录。"""
    if not os.path.exists(REPLAY_DIR):
        return []
    files = sorted(os.listdir(REPLAY_DIR), reverse=True)[:limit]
    replays = []
    for fname in files:
        if not fname.endswith(".json"):
            continue
        path = os.path.join(REPLAY_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            replays.append(
                {
                    "root_trace_id": data.get("root_trace_id", fname),
                    "saved_at": data.get("saved_at", 0),
                    "status": data.get("summary", {}).get("quality_status", "unknown"),
                    "failed": data.get("summary", {}).get("tasks_failed", 0),
                    "total": data.get("summary", {}).get("tasks_total", 0),
                    "policy": data.get("summary", {}).get("policy_action", ""),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue
    return replays


def get_failure_timeline(root_trace_id: str) -> list[dict]:
    """获取失败时间线：按时间顺序排列的关键事件。"""
    replay = load_replay(root_trace_id)
    if not replay:
        return []

    timeline = []
    log = replay.get("log", [])
    for entry in log:
        event = entry.get("event", "")
        if event in ("task_failed", "task_timeout", "dag_deadlock", "wave_timeout", "task_start", "task_done"):
            timeline.append(
                {
                    "time": entry.get("timestamp", 0) or entry.get("time", 0),
                    "event": event,
                    "task": entry.get("task", ""),
                    "detail": entry.get("error", "") or entry.get("deadlock", "") or entry.get("result_preview", ""),
                    "trace": entry.get("trace_id", ""),
                    "root_trace": entry.get("root_trace_id", ""),
                }
            )

    timeline.sort(key=lambda x: x["time"])
    return timeline


def format_timeline(timeline: list[dict]) -> str:
    """格式化失败时间线为可读文本。"""
    if not timeline:
        return "无事件记录。"
    lines = []
    for evt in timeline:
        icon = {
            "task_start": "START",
            "task_done": "DONE",
            "task_failed": "FAIL",
            "task_timeout": "TIMEOUT",
            "dag_deadlock": "DEADLOCK",
            "wave_timeout": "WAVE_TIMEOUT",
        }.get(evt["event"], evt["event"])
        detail = evt.get("detail", "")[:80]
        task = evt.get("task", "")[:20]
        lines.append(f"  [{icon:12s}] task={task:20s} detail={detail}")
    return "\n".join(lines)
