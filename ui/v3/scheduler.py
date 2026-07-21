"""CRUX TUI v3 — single refresh scheduler.

Replaces the three independent threads in tui_v2:
  - animation thread (10fps beast icon rotation)
  - heartbeat timer (2s Watchdog.beat)
  - spinner thread (80ms activity log repaint)

Design:
  - One Timer thread that fires TickEvent at variable rate.
  - Rate depends on UI state: 10fps when animating, 1fps idle, 0fps when hidden.
  - All time-based rendering uses time.monotonic() — no frame counting needed.

Usage in app.py:
    scheduler = Scheduler(post_event)
    scheduler.start()
    # ... app runs ...
    scheduler.stop()
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class Scheduler:
    """Single refresh timer with adaptive rate.

    Fires on_tick callbacks on every timer tick.  Callbacks are called
    from the timer thread; they should be non-blocking (post to queue,
    invalidate, etc.).
    """

    def __init__(
        self,
        *,
        active_interval: float = 0.1,
        idle_interval: float = 1.0,
        off_interval: float = 5.0,
    ) -> None:
        self._active_interval = active_interval
        self._idle_interval = idle_interval
        self._off_interval = off_interval

        self._running = False
        self._thread: threading.Thread | None = None
        self._interval = idle_interval
        self._lock = threading.Lock()
        self._listeners: list[Callable[[], None]] = []

    # ── Public API ────────────────────────────────────────────────

    def on_tick(self, fn: Callable[[], None]) -> None:
        """Register a callback to fire on each tick (from timer thread)."""
        self._listeners.append(fn)

    # ── Public API ────────────────────────────────────────────────

    def start(self) -> None:
        """Start the timer thread (daemon, so it won't block exit)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="v3-scheduler")
        self._thread.start()

    def stop(self) -> None:
        """Stop the timer thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def set_streaming(self, active: bool) -> None:
        """Called when streaming starts/stops. Speeds up refresh during streaming."""
        with self._lock:
            self._interval = self._active_interval if active else self._idle_interval

    def set_hidden(self, hidden: bool) -> None:
        """Called when the app is minimized/backgrounded."""
        with self._lock:
            self._interval = self._off_interval if hidden else self._idle_interval

    # ── Internal ──────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            with self._lock:
                interval = self._interval
            time.sleep(interval)
            if self._running:
                for fn in self._listeners:
                    try:
                        fn()
                    except Exception:
                        pass  # never let a tick crash the scheduler
