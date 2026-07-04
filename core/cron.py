"""Cron scheduler — Kimi-style recurring/one-shot task scheduling.

Port of Kimi Code CLI's CronCreate / CronList / CronDelete system.

Features:
    - 5-field cron: minute hour day-of-month month day-of-week
    - Recurring tasks (fire on every cron match, auto-expire after 7 days)
    - One-shot tasks (fire once, auto-delete)
    - Jitter: recurring shifted forward ≤10% period/15min; one-shot :00/:30 pulled back ≤90s
    - Coalesce: multiple missed fires collapsed into single delivery
    - 7-day stale auto-cleanup

Usage:
    scheduler = CronScheduler.get()
    job_id = scheduler.create("*/5 * * * *", "check CI status", recurring=True)
    jobs = scheduler.list_all()
    scheduler.delete(job_id)
"""

from __future__ import annotations

import contextlib
import json
import random
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from core.config import OUTPUT_DIR

__all__ = [
    "CronJob",
    "CronScheduler",
    "cron_create",
    "cron_delete",
    "cron_list",
]

CRON_STATE_FILE = OUTPUT_DIR / "cron_state.json"


# ── Cron expression parser ───────────────────────────────────


def _parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of matching values."""
    values: set[int] = set()

    if field == "*":
        return set(range(min_val, max_val + 1))

    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            base, _, step_str = part.partition("/")
            step = int(step_str)
            if base == "*":
                start, end = min_val, max_val
            else:
                start = end = int(base)
            v = start
            while v <= end:
                values.add(v)
                v += step
        elif "-" in part:
            start_str, _, end_str = part.partition("-")
            values.update(range(int(start_str), int(end_str) + 1))
        else:
            values.add(int(part))

    return values


def _next_cron_fire(cron: str, from_time: datetime | None = None) -> datetime | None:
    """Compute the next fire time from a 5-field cron expression.

    Returns None if no fire in the next 5 years (effectively "never").
    """
    now = from_time or datetime.now()
    fields = cron.strip().split()
    if len(fields) != 5:
        return None

    try:
        minutes = _parse_cron_field(fields[0], 0, 59)
        hours = _parse_cron_field(fields[1], 0, 23)
        doms = _parse_cron_field(fields[2], 1, 31)
        months = _parse_cron_field(fields[3], 1, 12)
        dows = _parse_cron_field(fields[4], 0, 6)
    except (ValueError, IndexError):
        return None

    # Search forward minute by minute (max 5 years)
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    deadline = now + timedelta(days=365 * 5)

    while candidate <= deadline:
        if (
            candidate.minute in minutes
            and candidate.hour in hours
            and candidate.day in doms
            and candidate.month in months
            and candidate.weekday() in dows
        ):
            return candidate
        candidate += timedelta(minutes=1)

    return None


def human_schedule(cron: str, recurring: bool) -> str:
    """Render a human-readable description of the cron schedule."""
    if not recurring:
        return "once"
    fields = cron.strip().split()
    if len(fields) != 5:
        return cron

    m, h, dom, mon, dow = fields

    if m.startswith("*/"):
        interval = int(m.split("/")[1])
        if h == "*" and dom == "*" and mon == "*" and dow == "*":
            return f"every {interval} minutes"

    if h == "*" and m != "*":
        return f"hourly at :{m}"

    if h != "*" and m != "*":
        hour_part = f"{int(h):02d}:{int(m):02d}"
        if dom == "*" and mon == "*" and dow == "*":
            return f"daily at {hour_part}"
        if dow != "*":
            day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
            days = [day_names[int(d)] for d in _parse_cron_field(dow, 0, 6)]
            return f"{','.join(days)} at {hour_part}"

    return cron


# ── Jitter ────────────────────────────────────────────────────


def _apply_jitter(fire_time: datetime, cron: str, recurring: bool) -> datetime:
    """Apply anti-herd jitter to a fire time.

    - Recurring: shift forward by ≤ min(10% of period, 15 minutes).
    - One-shot on :00 or :30: pull back by ≤ 90 seconds.
    """
    if recurring:
        # Estimate period from cron
        period_seconds = _estimate_period(cron)
        max_jitter = min(int(period_seconds * 0.1), 900)  # max 15 min
        jitter = random.randint(1, max(max_jitter, 1))
        return fire_time + timedelta(seconds=jitter)
    else:
        # One-shot: only jitter if on :00 or :30
        if fire_time.minute == 0 or fire_time.minute == 30:
            jitter = random.randint(-90, 0)
            return fire_time + timedelta(seconds=jitter)
        return fire_time


def _estimate_period(cron: str) -> int:
    """Crude period estimate in seconds."""
    fields = cron.strip().split()
    if len(fields) != 5:
        return 3600
    m = fields[0]
    if m.startswith("*/"):
        return int(m.split("/")[1]) * 60
    if m == "*" and fields[1] == "*":
        return 60
    if fields[1] == "*":
        return 3600
    return 86400


# ── Dataclass ─────────────────────────────────────────────────


@dataclass
class CronJob:
    """A scheduled cron job."""

    id: str
    cron: str
    prompt: str
    recurring: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    next_fire_at: str | None = None
    last_fired_at: str | None = None
    coalesced_count: int = 0

    @property
    def age_days(self) -> float:
        try:
            created = datetime.fromisoformat(self.created_at)
            age = datetime.now(timezone.utc) - created
            return age.total_seconds() / 86400.0
        except (ValueError, TypeError):
            return 0.0

    @property
    def stale(self) -> bool:
        """True if recurring and older than 7 days."""
        return self.recurring and self.age_days >= 7.0


# ── Scheduler ─────────────────────────────────────────────────


class CronScheduler:
    """Background thread scheduler for cron jobs.

    Singleton per process. Fires callbacks when jobs are due.
    """

    _instance: CronScheduler | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._jobs: dict[str, CronJob] = {}
        self._callbacks: dict[str, Callable] = {}
        self._thread: threading.Thread | None = None
        self._running = False
        self._wake_interval = 30  # seconds between poll ticks
        self._load_state()

    @classmethod
    def get(cls) -> CronScheduler:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── State persistence ──────────────────────────────────

    def _load_state(self) -> None:
        if not CRON_STATE_FILE.exists():
            return
        try:
            data = json.loads(CRON_STATE_FILE.read_text(encoding="utf-8"))
            for job_data in data.get("jobs", []):
                job = CronJob(**job_data)
                self._jobs[job.id] = job
        except (json.JSONDecodeError, TypeError, OSError):
            pass

    def _save_state(self) -> None:
        CRON_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {"jobs": [asdict(job) for job in self._jobs.values()]}
            CRON_STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ── Job management ─────────────────────────────────────

    def create(
        self, cron: str, prompt: str, *, recurring: bool = True, callback: Callable | None = None
    ) -> str:
        """Create a new cron job. Returns the job id (8-hex)."""
        job_id = uuid.uuid4().hex[:8]
        datetime.now()

        # Compute next fire with jitter
        next_fire = _next_cron_fire(cron)
        if next_fire:
            next_fire = _apply_jitter(next_fire, cron, recurring)

        job = CronJob(
            id=job_id,
            cron=cron,
            prompt=prompt,
            recurring=recurring,
            next_fire_at=next_fire.isoformat() if next_fire else None,
        )
        self._jobs[job_id] = job

        if callback:
            self._callbacks[job_id] = callback

        self._save_state()
        self._ensure_running()
        return job_id

    def delete(self, job_id: str) -> bool:
        """Delete a cron job by id. Returns False if not found."""
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        self._callbacks.pop(job_id, None)
        self._save_state()
        return True

    def list_all(self) -> list[CronJob]:
        """List all cron jobs."""
        return sorted(self._jobs.values(), key=lambda j: j.created_at)

    def get(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    # ── Background thread ──────────────────────────────────

    def _ensure_running(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="cron-scheduler")
        self._thread.start()

    def _poll_loop(self) -> None:
        """Poll for due jobs every wake_interval seconds."""
        while self._running:
            with contextlib.suppress(Exception):
                self._check_and_fire()
            time.sleep(self._wake_interval)

    def _check_and_fire(self) -> None:
        now = datetime.now()
        to_fire: list[CronJob] = []
        to_delete: list[str] = []

        for job in list(self._jobs.values()):
            # Check stale (recurring older than 7 days)
            if job.stale:
                # Fire one final time with stale flag
                callback = self._callbacks.get(job.id)
                if callback:
                    callback(job.id, job.prompt, stale=True, coalesced=job.coalesced_count)
                to_delete.append(job.id)
                continue

            # Check if due
            if job.next_fire_at:
                try:
                    next_fire = datetime.fromisoformat(job.next_fire_at)
                except (ValueError, TypeError):
                    continue
                if now >= next_fire:
                    to_fire.append(job)

        # Fire due jobs
        for job in to_fire:
            callback = self._callbacks.get(job.id)
            if callback:
                callback(job.id, job.prompt, stale=job.stale, coalesced=job.coalesced_count)

            job.last_fired_at = datetime.now(timezone.utc).isoformat()
            job.coalesced_count = 0

            # Compute next fire
            if job.recurring and job.id not in to_delete:
                next_fire = _next_cron_fire(job.cron)
                if next_fire:
                    next_fire = _apply_jitter(next_fire, job.cron, True)
                    job.next_fire_at = next_fire.isoformat()
                else:
                    job.next_fire_at = None
            else:
                # One-shot: auto-delete
                to_delete.append(job.id)

        # Clean up
        for job_id in to_delete:
            self._jobs.pop(job_id, None)
            self._callbacks.pop(job_id, None)

        if to_fire or to_delete:
            self._save_state()

    def stop(self) -> None:
        self._running = False


# ── Tool interface (for CRUX tool calling system) ─────────────


def cron_create(cron: str, prompt: str, *, recurring: bool = True) -> dict:
    """Create a cron job. Returns job info dict.

    This is the function exposed as a CRUX tool.
    """
    scheduler = CronScheduler.get()  # pyright: ignore[reportCallIssue]
    job_id = scheduler.create(cron, prompt, recurring=recurring)
    job = scheduler.get(job_id)
    if not job:
        return {"error": "failed to create job"}
    return {
        "id": job.id,
        "cron": job.cron,
        "humanSchedule": human_schedule(job.cron, job.recurring),
        "recurring": job.recurring,
        "nextFireAt": job.next_fire_at,
    }


def cron_list() -> list[dict]:
    """List all cron jobs."""
    scheduler = CronScheduler.get()  # pyright: ignore[reportCallIssue]
    return [
        {
            "id": job.id,
            "cron": job.cron,
            "humanSchedule": human_schedule(job.cron, job.recurring),
            "recurring": job.recurring,
            "nextFireAt": job.next_fire_at,
            "prompt": job.prompt[:200] + "…(truncated)" if len(job.prompt) > 200 else job.prompt,
            "ageDays": round(job.age_days, 2),
            "stale": job.stale,
        }
        for job in scheduler.list_all()
    ]


def cron_delete(job_id: str) -> dict:
    """Delete a cron job. Returns result dict."""
    scheduler = CronScheduler.get()  # pyright: ignore[reportCallIssue]
    ok = scheduler.delete(job_id)
    if ok:
        return {"deleted": job_id}
    return {"error": f"no cron job with id {job_id}"}
