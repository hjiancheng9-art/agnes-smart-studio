"""Quest 模式 — 长时间运行任务状态机 + 自动编排

方法论第5章: 长时间运行任务、周期执行、状态持久化、依赖链、自动编排。
比 task_launch 多: 状态持久化、依赖管理、自动触发下一步、复盘数据收集。
"""

import json
import time
import threading
from pathlib import Path
from datetime import datetime, timezone
from collections.abc import Callable

QUESTS_DIR = Path("output/quests")
QUESTS_DIR.mkdir(parents=True, exist_ok=True)

_locks: dict[str, threading.Lock] = {}


def _lock(quest_id: str) -> threading.Lock:
    if quest_id not in _locks:
        _locks[quest_id] = threading.Lock()
    return _locks[quest_id]


# ── Quest 数据结构 ──

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(quest_id: str) -> Path:
    return QUESTS_DIR / f"{quest_id}.json"


def _default_quest(name: str) -> dict:
    return {
        "id": name.replace(" ", "_").lower(),
        "name": name,
        "status": STATUS_PENDING,
        "created_at": _now(),
        "updated_at": _now(),
        "steps": [],
        "dependencies": [],
        "result": None,
        "error": None,
        "tags": [],
    }


# ── Quest 核心操作 ──

def quest_create(name: str, steps: list[dict] | None = None, depends_on: list[str] | None = None, tags: list[str] | None = None) -> dict:
    """Create a new quest with optional steps, dependencies and tags.
    
    Each step: {"name": str, "action": str, "timeout": int(optional)}
    """
    quest = _default_quest(name)
    if steps:
        quest["steps"] = steps
    if depends_on:
        quest["dependencies"] = depends_on
    if tags:
        quest["tags"] = tags
    quest["status"] = STATUS_PENDING
    quest["created_at"] = _now()
    quest["updated_at"] = _now()
    
    # Check if dependencies are met
    if depends_on:
        for dep_id in depends_on:
            dep = quest_load(dep_id)
            if dep and dep.get("status") != STATUS_DONE:
                quest["status"] = STATUS_BLOCKED
                break

    with _lock(quest["id"]):
        _path(quest["id"]).write_text(json.dumps(quest, indent=2, ensure_ascii=False), encoding="utf-8")
    return quest


def quest_load(quest_id: str) -> dict | None:
    """Load a quest by ID."""
    p = _path(quest_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def quest_list(status: str | None = None, tag: str | None = None) -> list[dict]:
    """List all quests, optionally filtered by status or tag."""
    result = []
    for p in sorted(QUESTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        quest = json.loads(p.read_text(encoding="utf-8"))
        if status and quest.get("status") != status:
            continue
        if tag and tag not in quest.get("tags", []):
            continue
        result.append(quest)
    return result


def quest_start(quest_id: str) -> dict:
    """Start a quest (transition pending→running)."""
    quest = quest_load(quest_id)
    if not quest:
        return {"error": f"Quest {quest_id} not found"}
    if quest["status"] != STATUS_PENDING:
        return {"error": f"Quest {quest_id} is {quest['status']}, not pending"}
    
    quest["status"] = STATUS_RUNNING
    quest["updated_at"] = _now()
    quest["started_at"] = _now()
    
    # Auto-start first step
    if quest["steps"]:
        quest["steps"][0]["status"] = STATUS_RUNNING
        quest["steps"][0]["started_at"] = _now()
    
    with _lock(quest_id):
        _path(quest_id).write_text(json.dumps(quest, indent=2, ensure_ascii=False), encoding="utf-8")
    return quest


def quest_complete(quest_id: str, result: str | None = None) -> dict:
    """Complete a quest (transition running→done)."""
    quest = quest_load(quest_id)
    if not quest:
        return {"error": f"Quest {quest_id} not found"}
    if quest["status"] != STATUS_RUNNING:
        return {"error": f"Quest {quest_id} is {quest['status']}, not running"}
    
    quest["status"] = STATUS_DONE
    quest["updated_at"] = _now()
    quest["completed_at"] = _now()
    if result:
        quest["result"] = result

    # Mark all steps done
    for step in quest.get("steps", []):
        if step.get("status") in (STATUS_PENDING, STATUS_RUNNING):
            step["status"] = STATUS_DONE
            step["completed_at"] = _now()

    with _lock(quest_id):
        _path(quest_id).write_text(json.dumps(quest, indent=2, ensure_ascii=False), encoding="utf-8")

    # Auto-trigger dependent quests
    _trigger_dependents(quest_id)
    return quest


def quest_fail(quest_id: str, error: str) -> dict:
    """Mark a quest as failed."""
    quest = quest_load(quest_id)
    if not quest:
        return {"error": f"Quest {quest_id} not found"}
    quest["status"] = STATUS_FAILED
    quest["updated_at"] = _now()
    quest["error"] = error
    with _lock(quest_id):
        _path(quest_id).write_text(json.dumps(quest, indent=2, ensure_ascii=False), encoding="utf-8")
    return quest


def quest_step_complete(quest_id: str, step_name: str, result: str | None = None) -> dict:
    """Mark a step as complete and auto-start next step."""
    quest = quest_load(quest_id)
    if not quest:
        return {"error": f"Quest {quest_id} not found"}
    
    steps = quest.get("steps", [])
    for i, step in enumerate(steps):
        if step.get("name") == step_name:
            step["status"] = STATUS_DONE
            step["completed_at"] = _now()
            if result:
                step["result"] = result
            # Auto-start next step
            if i + 1 < len(steps):
                steps[i + 1]["status"] = STATUS_RUNNING
                steps[i + 1]["started_at"] = _now()
            break
    
    # If all steps done, auto-complete quest
    if all(s.get("status") == STATUS_DONE for s in steps):
        quest["status"] = STATUS_DONE
        quest["completed_at"] = _now()
    
    quest["updated_at"] = _now()
    with _lock(quest_id):
        _path(quest_id).write_text(json.dumps(quest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    if quest["status"] == STATUS_DONE:
        _trigger_dependents(quest_id)
    return quest


def quest_delete(quest_id: str) -> dict:
    """Delete a quest."""
    p = _path(quest_id)
    if p.exists():
        p.unlink()
        return {"status": "deleted", "id": quest_id}
    return {"error": f"Quest {quest_id} not found"}


def _trigger_dependents(completed_id: str):
    """Find and auto-start quests that depend on this one."""
    for quest in quest_list(status=STATUS_BLOCKED):
        deps = quest.get("dependencies", [])
        if completed_id in deps:
            all_deps_done = all(
                (quest_load(d) or {}).get("status") == STATUS_DONE
                for d in deps
            )
            if all_deps_done:
                quest["status"] = STATUS_PENDING
                quest["updated_at"] = _now()
                with _lock(quest["id"]):
                    _path(quest["id"]).write_text(
                        json.dumps(quest, indent=2, ensure_ascii=False), encoding="utf-8"
                    )


# ── Tool Definitions ──

QUEST_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "quest_create",
        "description": "Create a quest (long-running task). Steps auto-execute in order. Dependencies auto-trigger.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Quest name"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "action": {"type": "string", "description": "Description of what this step does"}
                        }
                    },
                    "description": "Optional ordered steps"
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Quest IDs this quest depends on"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for filtering"
                }
            },
            "required": ["name"]
        }
            }
        },
    {
        "type": "function",
        "function": {
            "name": "quest_start",
        "description": "Start a pending quest.",
        "parameters": {
            "type": "object",
            "properties": {
                "quest_id": {"type": "string", "description": "Quest ID"}
            },
            "required": ["quest_id"]
        }
            }
        },
    {
        "type": "function",
        "function": {
            "name": "quest_complete",
        "description": "Mark quest done, auto-trigger dependents.",
        "parameters": {
            "type": "object",
            "properties": {
                "quest_id": {"type": "string"},
                "result": {"type": "string", "description": "Optional result summary"}
            },
            "required": ["quest_id"]
        }
            }
        },
    {
        "type": "function",
        "function": {
            "name": "quest_list",
        "description": "List quests, filterable by status/tag.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "running", "done", "failed", "blocked"]},
                "tag": {"type": "string"}
            }
        }
            }
        },
    {
        "type": "function",
        "function": {
            "name": "quest_step_complete",
        "description": "Mark a step done, auto-advance to next step.",
        "parameters": {
            "type": "object",
            "properties": {
                "quest_id": {"type": "string"},
                "step_name": {"type": "string"},
                "result": {"type": "string"}
            },
            "required": ["quest_id", "step_name"]
        }
            }
        },
]

QUEST_EXECUTOR_MAP = {
    "quest_create": lambda **kw: json.dumps(quest_create(**kw), ensure_ascii=False),
    "quest_start": lambda **kw: json.dumps(quest_start(**kw), ensure_ascii=False),
    "quest_complete": lambda **kw: json.dumps(quest_complete(**kw), ensure_ascii=False),
    "quest_list": lambda **kw: json.dumps(quest_list(**kw.get("status"), **kw.get("tag")), ensure_ascii=False),
    "quest_step_complete": lambda **kw: json.dumps(quest_step_complete(**kw), ensure_ascii=False),
}
