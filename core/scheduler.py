"""Built-in task scheduler for crux-smart-studio agent.

Provides ScheduledTask dataclass, Scheduler class with a daemon background
thread, parse_cron helper, and ToolRegistry-compatible definitions
(SCHEDULER_TOOL_DEFS + SCHEDULER_EXECUTOR_MAP) so the AI agent can
create, list, enable, disable, and remove scheduled tasks via function calls.

Schedule types:
  - "interval": schedule_value is seconds as string (e.g. "300" = 5 min)
  - "cron": schedule_value is a 5-field cron expression (e.g. "0 9 * * 1-5")
"""

import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

from core.config import OUTPUT_DIR
import contextlib

__all__ = [
    'SCHEDULER_EXECUTOR_MAP', 'SCHEDULER_TOOL_DEFS', 'ScheduledTask', 'Scheduler', 'get_scheduler', 'parse_cron',
]


# ── ScheduledTask dataclass ────────────────────────────────

@dataclass
class ScheduledTask:
    """Represents a single scheduled task."""

    id: str
    name: str
    prompt: str
    schedule_type: str          # "interval" or "cron"
    schedule_value: str         # seconds as str (interval) or cron expr (cron)
    enabled: bool = True
    last_run: str = ""
    next_run: str = ""
    created_at: str = ""
    run_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        known = cls.__dataclass_fields__
        return cls(**{k: data[k] for k in known if k in data})


# ── Cron expression parser ─────────────────────────────────

_CRON_FIELDS = ("minute", "hour", "day", "month", "weekday")
_CRON_RANGES = {
    "minute": range(0, 60),
    "hour": range(0, 24),
    "day": range(1, 32),
    "month": range(1, 13),
    "weekday": range(0, 7),     # 0 = Sunday
}


def parse_cron(expr: str) -> dict:
    """Parse a 5-field cron expression into a dict of allowed value sets.

    Supported syntax per field:
      *     - any value (wildcard)
      N     - specific number
      */N   - every N units (step)
      a-b   - inclusive range
      a,b,c - comma-separated list of any of the above

    Returns:
        dict with keys "minute", "hour", "day", "month", "weekday",
        each mapped to a set of ints.
    """
    fields = expr.strip().split()
    if len(fields) != 5:
        raise ValueError(
            f"Cron expression must have 5 fields, got {len(fields)}: {expr!r}"
        )
    result: dict[str, set[int]] = {}
    for name, raw in zip(_CRON_FIELDS, fields, strict=True):
        result[name] = _parse_cron_field(raw, _CRON_RANGES[name])
    # Normalize weekday: 7 is sometimes used for Sunday (same as 0)
    if 7 in result["weekday"]:
        result["weekday"].discard(7)
        result["weekday"].add(0)
    return result


def _parse_cron_field(raw: str, allowed: range) -> set[int]:
    """Parse a single cron field into a set of allowed integer values."""
    values: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part == "*":
            values.update(allowed)
        elif part.startswith("*/"):
            step = int(part[2:])
            if step <= 0:
                raise ValueError(f"Step must be positive: {part!r}")
            values.update(
                v for v in allowed if (v - allowed.start) % step == 0
            )
        elif "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
            values.update(range(lo, hi + 1))
        else:
            values.add(int(part))
    return values


# ── Scheduler ──────────────────────────────────────────────

_SCHEDULE_FILE = OUTPUT_DIR / "scheduled_tasks.json"
_TRIGGER_FILE = OUTPUT_DIR / "scheduler_triggers.jsonl"


class Scheduler:
    """Persistent task scheduler backed by a JSON file.

    Runs a daemon background thread that checks for due tasks every
    10 seconds and executes them via a registered callback or by
    writing triggers to a JSONL file for the chat system to pick up.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()
        self._callback = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._load()
        self._thread.start()

    # ── Public API ─────────────────────────────────────────

    def add_task(self, name: str, prompt: str,
                 schedule_type: str, schedule_value: str) -> ScheduledTask:
        """Create and add a new scheduled task.

        Args:
            name: Human-readable task name.
            prompt: The prompt to execute when the task is due.
            schedule_type: "interval" or "cron".
            schedule_value: Seconds as string (interval) or cron expr (cron).

        Returns:
            The created ScheduledTask.
        """
        if schedule_type not in ("interval", "cron"):
            raise ValueError(
                f"schedule_type must be 'interval' or 'cron', "
                f"got {schedule_type!r}"
            )
        # Validate schedule_value early
        if schedule_type == "interval":
            int(schedule_value)
        else:
            parse_cron(schedule_value)

        task = ScheduledTask(
            id=uuid.uuid4().hex[:12],
            name=name,
            prompt=prompt,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            enabled=True,
            created_at=datetime.now().isoformat()[:19],
        )
        task.next_run = self._calculate_next_run(task)
        with self._lock:
            self._tasks[task.id] = task
            self._save()
        return task

    def remove_task(self, task_id: str) -> bool:
        """Remove a task by ID. Returns True if found and removed."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self._save()
                return True
            return False

    def list_tasks(self) -> list[ScheduledTask]:
        """Return all scheduled tasks."""
        with self._lock:
            return list(self._tasks.values())

    def enable_task(self, task_id: str) -> bool:
        """Enable a task by ID. Returns True if found."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task.enabled = True
            task.next_run = self._calculate_next_run(task)
            self._save()
            return True

    def disable_task(self, task_id: str) -> bool:
        """Disable a task by ID. Returns True if found."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task.enabled = False
            self._save()
            return True

    def set_execution_callback(self, callback) -> None:
        """Register a callback invoked when a task is due.

        The callback receives a single argument: the prompt string.
        Set to None to clear the callback.
        """
        self._callback = callback

    def create_auto_improvement_task(self) -> ScheduledTask | None:
        """Analyze observability data and create an auto-improvement task.

        Reads recent traces to find tools with high error rates, then creates
        a scheduled task that prompts the agent to review and fix those tools.

        Returns the created task, or None if no problematic tools were found
        or if a similar task already exists.
        """
        try:
            from core.observability import get_recent_traces

            recent = get_recent_traces(limit=50)
            if not recent:
                return None

            # Find tools with high error rates
            tool_stats: dict[str, dict] = {}
            for trace in recent:
                name = trace.get("name", "")
                if not name.startswith("tool:"):
                    continue
                tool_name = name[5:]
                stat = tool_stats.setdefault(tool_name, {"calls": 0, "errors": 0})
                stat["calls"] += 1
                if trace.get("status") == "error":
                    stat["errors"] += 1

            problematic = []
            for tool_name, stat in tool_stats.items():
                error_rate = stat["errors"] / stat["calls"] if stat["calls"] else 0
                if error_rate > 0.3 and stat["calls"] >= 3:
                    problematic.append(f"{tool_name} ({stat['errors']}/{stat['calls']} errors)")

            if not problematic:
                return None

            # Check if a similar auto-improvement task already exists
            with self._lock:
                for task in self._tasks.values():
                    if task.name == "auto_improvement" and task.enabled:
                        return None  # Already exists

            prompt = (
                f"[Auto-Improvement] Recent tool performance analysis shows "
                f"these tools have high error rates: {', '.join(problematic[:3])}. "
                f"Please review the parameters and prerequisites for these tools, "
                f"check if there are common failure patterns, and suggest fixes."
            )

            return self.add_task(
                name="auto_improvement",
                prompt=prompt,
                schedule_type="interval",
                schedule_value="3600",  # Every hour
            )
        except (OSError, ValueError, RuntimeError):
            return None

    def shutdown(self) -> None:
        """Stop the background thread gracefully."""
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    # ── Scheduling logic ───────────────────────────────────

    def _calculate_next_run(self, task: ScheduledTask) -> str:
        """Calculate the next run time as an ISO-format string."""
        if task.schedule_type == "interval":
            seconds = int(task.schedule_value)
            return (
                datetime.now() + timedelta(seconds=seconds)
            ).isoformat()[:19]

        # cron: find the next matching minute
        parsed = parse_cron(task.schedule_value)
        now = datetime.now()
        # Start from the next whole minute
        candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # Search up to ~4 years to handle leap-year-only expressions
        max_iter = 4 * 366 * 24 * 60
        for _ in range(max_iter):
            cron_wd = (candidate.weekday() + 1) % 7  # Python 0=Mon -> cron 0=Sun
            if (candidate.minute in parsed["minute"]
                    and candidate.hour in parsed["hour"]
                    and candidate.day in parsed["day"]
                    and candidate.month in parsed["month"]
                    and cron_wd in parsed["weekday"]):
                return candidate.isoformat()[:19]
            candidate += timedelta(minutes=1)
        # Fallback: should not reach here for valid cron expressions
        return (now + timedelta(days=1)).isoformat()[:19]

    # ── Background thread ─────────────────────────────────

    def _run_loop(self) -> None:
        """Background loop: check for due tasks every 10 seconds."""
        while not self._stop_event.is_set():
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                self._check_and_run()
            self._stop_event.wait(timeout=10)

    def _check_and_run(self) -> None:
        """Check all enabled tasks and execute those that are due."""
        now_str = datetime.now().isoformat()[:19]
        due: list[ScheduledTask] = []
        with self._lock:
            for task in self._tasks.values():
                if task.enabled and task.next_run and task.next_run <= now_str:
                    due.append(task)
        for task in due:
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                self._execute_task(task)
            # Update task state after execution
            with self._lock:
                t = self._tasks.get(task.id)
                if t is not None:
                    t.last_run = now_str
                    t.run_count += 1
                    t.next_run = self._calculate_next_run(t)
                    self._save()

    # ── Task execution ─────────────────────────────────────

    def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a due task.

        Writes a trigger entry to the JSONL trigger file so the chat
        system can pick it up, then calls the registered callback (if any)
        with the task's prompt.
        """
        trigger = {
            "task_id": task.id,
            "name": task.name,
            "prompt": task.prompt,
            "timestamp": datetime.now().isoformat()[:19],
        }
        try:
            with open(_TRIGGER_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(trigger, ensure_ascii=False) + "\n")
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        if self._callback is not None:
            self._callback(task.prompt)

    # ── Persistence ────────────────────────────────────────

    def _save(self) -> None:
        """Persist all tasks to JSON. Caller must hold self._lock."""
        data = {"tasks": [t.to_dict() for t in self._tasks.values()]}
        _SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SCHEDULE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load(self) -> None:
        """Load tasks from JSON."""
        with self._lock:
            if not _SCHEDULE_FILE.exists():
                return
            try:
                raw = _SCHEDULE_FILE.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError, OSError):
                return
            for td in data.get("tasks", []):
                try:
                    task = ScheduledTask.from_dict(td)
                    self._tasks[task.id] = task
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue


# ── Module-level singleton ─────────────────────────────────

_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    """Return the singleton Scheduler instance, creating it if necessary."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


def _get_scheduler() -> Scheduler:
    """Internal accessor for executor functions."""
    return get_scheduler()


# ── Tool definitions (OpenAI function format) ──────────────

SCHEDULER_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "schedule_add",
            "description": (
                "Add a new scheduled task. The task will run automatically "
                "at the specified interval or cron schedule, executing the "
                "given prompt each time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human-readable name for the task",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to execute when the task is due",
                    },
                    "schedule_type": {
                        "type": "string",
                        "enum": ["interval", "cron"],
                        "description": (
                            '"interval" runs every N seconds; '
                            '"cron" uses a 5-field cron expression'
                        ),
                    },
                    "schedule_value": {
                        "type": "string",
                        "description": (
                            'For interval: seconds as string (e.g. "300" '
                            'for 5 minutes). For cron: 5-field expression '
                            '(e.g. "0 9 * * 1-5" for 9 AM weekdays)'
                        ),
                    },
                },
                "required": ["name", "prompt", "schedule_type", "schedule_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_remove",
            "description": "Remove a scheduled task by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to remove",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_list",
            "description": "List all scheduled tasks with their current status.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_enable",
            "description": "Enable a scheduled task so it will run again.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to enable",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_disable",
            "description": "Disable a scheduled task so it stops running until re-enabled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to disable",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_auto_improve",
            "description": (
                "Analyze recent tool performance data and automatically create "
                "an improvement task for tools with high error rates. "
                "This is the agent's self-improvement mechanism."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ── Executor functions ─────────────────────────────────────

def _exec_schedule_add(**kwargs) -> str:
    s = _get_scheduler()
    task = s.add_task(
        name=kwargs["name"],
        prompt=kwargs["prompt"],
        schedule_type=kwargs["schedule_type"],
        schedule_value=kwargs["schedule_value"],
    )
    return json.dumps(task.to_dict(), ensure_ascii=False)


def _exec_schedule_remove(**kwargs) -> str:
    s = _get_scheduler()
    removed = s.remove_task(kwargs["task_id"])
    return json.dumps(
        {"removed": removed, "task_id": kwargs["task_id"]},
        ensure_ascii=False,
    )


def _exec_schedule_list(**kwargs) -> str:
    s = _get_scheduler()
    tasks = s.list_tasks()
    return json.dumps(
        [t.to_dict() for t in tasks], ensure_ascii=False
    )


def _exec_schedule_enable(**kwargs) -> str:
    s = _get_scheduler()
    enabled = s.enable_task(kwargs["task_id"])
    return json.dumps(
        {"enabled": enabled, "task_id": kwargs["task_id"]},
        ensure_ascii=False,
    )


def _exec_schedule_disable(**kwargs) -> str:
    s = _get_scheduler()
    disabled = s.disable_task(kwargs["task_id"])
    return json.dumps(
        {"disabled": disabled, "task_id": kwargs["task_id"]},
        ensure_ascii=False,
    )


def _exec_schedule_auto_improve(**kwargs) -> str:
    s = _get_scheduler()
    task = s.create_auto_improvement_task()
    if task is None:
        return json.dumps(
            {"created": False, "reason": "No problematic tools found or task already exists"},
            ensure_ascii=False,
        )
    return json.dumps(
        {"created": True, "task": task.to_dict()},
        ensure_ascii=False,
    )


SCHEDULER_EXECUTOR_MAP = {
    "schedule_add": _exec_schedule_add,
    "schedule_remove": _exec_schedule_remove,
    "schedule_list": _exec_schedule_list,
    "schedule_enable": _exec_schedule_enable,
    "schedule_disable": _exec_schedule_disable,
    "schedule_auto_improve": _exec_schedule_auto_improve,
}
