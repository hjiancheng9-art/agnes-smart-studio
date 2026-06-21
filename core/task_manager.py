"""Persistent task management system for agnes-smart-studio agent.

Provides TaskStatus enum, Task dataclass, TaskManager class, and
ToolRegistry-compatible definitions (TASK_MANAGER_TOOL_DEFS +
TASK_MANAGER_EXECUTOR_MAP) so tasks can be created/updated/listed
by the AI agent via function calls.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

from core.config import OUTPUT_DIR

__all__ = [
    'TASK_MANAGER_EXECUTOR_MAP', 'TASK_MANAGER_TOOL_DEFS', 'Task', 'TaskManager', 'TaskStatus',
]


# ── Task status enum ────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELETED = "deleted"


# ── Task dataclass ──────────────────────────────────────────

@dataclass
class Task:
    id: str
    subject: str
    description: str = ""
    activeForm: str = ""
    status: TaskStatus = TaskStatus.PENDING
    owner: str = ""
    blockedBy: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        data = dict(data)
        data["status"] = TaskStatus(data["status"])
        return cls(**data)


# ── Task manager ────────────────────────────────────────────

_TASKS_FILE = OUTPUT_DIR / "tasks.json"


class TaskManager:
    """Persistent task manager backed by a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _TASKS_FILE
        self._tasks: dict[str, Task] = {}
        self._next_id_counter: int = 1
        self._load()

    # ── CRUD ────────────────────────────────────────────────

    def create(self, subject: str, description: str = "",
               activeForm: str = "") -> Task:
        """Create a new task with an auto-incremented ID."""
        tid = self._next_id()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        task = Task(
            id=tid,
            subject=subject,
            description=description,
            activeForm=activeForm or subject,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._tasks[tid] = task
        self._save()
        return task

    def get(self, task_id: str) -> Task | None:
        """Return a task by ID, or None if not found."""
        return self._tasks.get(task_id)

    def update(self, task_id: str, *, status: str | None = None,
               subject: str | None = None, description: str | None = None,
               owner: str | None = None, activeForm: str | None = None,
               metadata: dict | None = None) -> Task | None:
        """Update fields on a task and persist. Returns the updated task."""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if status is not None:
            task.status = TaskStatus(status)
        if subject is not None:
            task.subject = subject
        if description is not None:
            task.description = description
        if owner is not None:
            task.owner = owner
        if activeForm is not None:
            task.activeForm = activeForm
        if metadata is not None:
            task.metadata.update(metadata)
        task.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save()
        return task

    def list(self, status: str | None = None) -> list[Task]:
        """List tasks, optionally filtered by status.
        DELETED tasks are excluded by default."""
        status_enum = TaskStatus(status) if status else None
        result = []
        for t in self._tasks.values():
            if t.status == TaskStatus.DELETED and status_enum is None:
                continue
            if status_enum is not None and t.status != status_enum:
                continue
            result.append(t)
        return result

    def delete(self, task_id: str) -> bool:
        """Soft-delete a task (sets status to DELETED)."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.DELETED
        task.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save()
        return True

    # ── Dependency management ───────────────────────────────

    def add_blocked_by(self, task_id: str, blocking_task_id: str) -> bool:
        """Mark *task_id* as blocked by *blocking_task_id*."""
        task = self._tasks.get(task_id)
        blocker = self._tasks.get(blocking_task_id)
        if task is None or blocker is None:
            return False
        if blocking_task_id not in task.blockedBy:
            task.blockedBy.append(blocking_task_id)
        if task_id not in blocker.blocks:
            blocker.blocks.append(task_id)
        task.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save()
        return True

    def add_blocks(self, task_id: str, blocked_task_id: str) -> bool:
        """Mark *task_id* as blocking *blocked_task_id* (reverse dependency)."""
        return self.add_blocked_by(blocked_task_id, task_id)

    def get_blocked_tasks(self) -> list[Task]:
        """Return tasks that have at least one uncompleted blocker."""
        completed_ids = {
            t.id for t in self._tasks.values()
            if t.status == TaskStatus.COMPLETED
        }
        return [
            t for t in self._tasks.values()
            if t.blockedBy and any(b not in completed_ids for b in t.blockedBy)
            and t.status not in (TaskStatus.COMPLETED, TaskStatus.DELETED)
        ]

    def get_available_tasks(self) -> list[Task]:
        """Return PENDING tasks with no uncompleted blockers."""
        completed_ids = {
            t.id for t in self._tasks.values()
            if t.status == TaskStatus.COMPLETED
        }
        return [
            t for t in self._tasks.values()
            if t.status == TaskStatus.PENDING
            and all(b in completed_ids for b in t.blockedBy)
        ]

    # ── Persistence ─────────────────────────────────────────

    def _save(self) -> None:
        data = {
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "next_id": self._next_id_counter,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return
        self._next_id_counter = data.get("next_id", 1)
        for td in data.get("tasks", []):
            try:
                task = Task.from_dict(td)
                self._tasks[task.id] = task
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

    def _next_id(self) -> str:
        tid = f"task-{self._next_id_counter:03d}"
        self._next_id_counter += 1
        return tid


# ── Module-level singleton ──────────────────────────────────

_manager: TaskManager | None = None


def _get_manager() -> TaskManager:
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager


# ── Tool definitions (OpenAI function format) ──────────────

TASK_MANAGER_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "task_create",
            "description": "Create a new task. Returns the created task with its auto-generated ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Brief title for the task",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the task",
                    },
                    "activeForm": {
                        "type": "string",
                        "description": "Present-continuous form shown during execution, e.g. 'Running tests'",
                    },
                },
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_update",
            "description": "Update a task's status, subject, description, or metadata. Only provided fields are changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID, e.g. task-001",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed"],
                        "description": "New status for the task",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Updated task title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Updated task description",
                    },
                    "activeForm": {
                        "type": "string",
                        "description": "Updated present-continuous form",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Metadata keys to merge into the task (existing keys are updated, not replaced)",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "List tasks, optionally filtered by status. DELETED tasks are excluded by default.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed"],
                        "description": "Filter by status. Omit to list all non-deleted tasks.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_get",
            "description": "Get full details of a single task by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID, e.g. task-001",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
]


# ── Executor map ────────────────────────────────────────────

def _exec_task_create(**kwargs) -> str:
    m = _get_manager()
    task = m.create(
        subject=kwargs["subject"],
        description=kwargs.get("description", ""),
        activeForm=kwargs.get("activeForm", ""),
    )
    return json.dumps(task.to_dict(), ensure_ascii=False)


def _exec_task_update(**kwargs) -> str:
    m = _get_manager()
    task = m.update(
        kwargs["task_id"],
        status=kwargs.get("status"),
        subject=kwargs.get("subject"),
        description=kwargs.get("description"),
        activeForm=kwargs.get("activeForm"),
        metadata=kwargs.get("metadata"),
    )
    if task is None:
        return json.dumps({"error": "Task not found"}, ensure_ascii=False)
    return json.dumps(task.to_dict(), ensure_ascii=False)


def _exec_task_list(**kwargs) -> str:
    m = _get_manager()
    tasks = m.list(status=kwargs.get("status"))
    return json.dumps(
        [t.to_dict() for t in tasks], ensure_ascii=False
    )


def _exec_task_get(**kwargs) -> str:
    m = _get_manager()
    task = m.get(kwargs["task_id"])
    if task is None:
        return json.dumps({"error": "Task not found"}, ensure_ascii=False)
    return json.dumps(task.to_dict(), ensure_ascii=False)


TASK_MANAGER_EXECUTOR_MAP = {
    "task_create": _exec_task_create,
    "task_update": _exec_task_update,
    "task_list": _exec_task_list,
    "task_get": _exec_task_get,
}
