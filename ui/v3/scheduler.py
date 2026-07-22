"""CRUX TUI v3 — single refresh scheduler with watchdog.

Replaces the three independent threads in tui_v2:
  - animation thread (10fps beast icon rotation)
  - heartbeat timer (2s Watchdog.beat)
  - spinner thread (80ms activity log repaint)

Design:
  - One Timer thread that fires TickEvent at variable rate.
  - Rate depends on UI state: 10fps when animating, 1fps idle, 0fps when hidden.
  - Watchdog: if the timer thread dies, a backup restarts it.
  - All time-based rendering uses time.monotonic() — no frame counting needed.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("crux.v3.scheduler")


class Scheduler:
    """Single refresh timer with adaptive rate and watchdog.

    Fires on_tick callbacks on every timer tick.  Callbacks are called
    from the timer thread; they should be non-blocking (post to queue,
    invalidate, etc.).

    Watchdog: a separate thread monitors the timer thread's heartbeat.
    If no heartbeat for WATCHDOG_TIMEOUT seconds, the timer is restarted.
    """

    WATCHDOG_TIMEOUT = 5.0  # seconds without heartbeat → restart
    WATCHDOG_CHECK_INTERVAL = 1.0  # how often the watcher checks

    def __init__(
        self,
        *,
        active_interval: float = 0.1,
        idle_interval: float = 1.0,
        off_interval: float = 5.0,
        on_crash: Callable[[str], None] | None = None,
    ) -> None:
        self._active_interval = active_interval
        self._idle_interval = idle_interval
        self._off_interval = off_interval

        self._running = False
        self._thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None
        self._interval = idle_interval
        self._lock = threading.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._last_heartbeat = 0.0
        self._heartbeat_lock = threading.Lock()
        self._crash_count = 0
        self._on_crash = on_crash

    # ── Public API ────────────────────────────────────────────

    def on_tick(self, fn: Callable[[], None]) -> None:
        """Register a callback to fire on each tick (from timer thread)."""
        self._listeners.append(fn)

    def start(self) -> None:
        """Start the timer thread + watchdog (daemon, so they won't block exit)."""
        if self._running:
            return
        self._running = True
        self._start_timer_thread()
        self._start_watchdog()

    def stop(self) -> None:
        """Stop the timer and watchdog threads."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=1.0)
            self._watchdog_thread = None

    def set_streaming(self, active: bool) -> None:
        """Called when streaming starts/stops. Speeds up refresh during streaming."""
        with self._lock:
            self._interval = self._active_interval if active else self._idle_interval

    def set_hidden(self, hidden: bool) -> None:
        """Called when the app is minimized/backgrounded."""
        with self._lock:
            self._interval = self._off_interval if hidden else self._idle_interval

    def heartbeat(self) -> None:
        """Called by the timer thread each loop iteration. Updates watchdog timestamp."""
        with self._heartbeat_lock:
            self._last_heartbeat = time.monotonic()

    @property
    def crash_count(self) -> int:
        return self._crash_count

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Internal: timer thread ────────────────────────────────

    def _start_timer_thread(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="v3-scheduler")
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            with self._lock:
                interval = self._interval
            time.sleep(interval)
            if not self._running:
                break
            self.heartbeat()
            for fn in self._listeners:
                try:
                    fn()
                except Exception:
                    logger.exception("Scheduler tick callback failed")
                    # Let the watchdog know we're still alive even on error
                    self.heartbeat()

    # ── Internal: watchdog ────────────────────────────────────

    def _start_watchdog(self) -> None:
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True, name="v3-scheduler-watchdog")
        self._watchdog_thread.start()

    def _watchdog_loop(self) -> None:
        while self._running:
            time.sleep(self.WATCHDOG_CHECK_INTERVAL)
            if not self._running:
                break

            with self._heartbeat_lock:
                last = self._last_heartbeat
            elapsed = time.monotonic() - last

            # Check if timer thread is alive (first heartbeat may take a cycle)
            if self._last_heartbeat == 0.0 and self._thread is not None and self._thread.is_alive():
                continue

            if elapsed > self.WATCHDOG_TIMEOUT or (self._thread is not None and not self._thread.is_alive()):
                self._crash_count += 1
                msg = (
                    f"Scheduler timer thread died or stalled "
                    f"(last heartbeat {elapsed:.1f}s ago, crash #{self._crash_count}). Restarting."
                )
                logger.warning(msg)
                if self._on_crash:
                    try:
                        self._on_crash(msg)
                    except Exception:
                        logger.exception("on_crash callback failed")

                # Restart timer thread
                old = self._thread
                self._start_timer_thread()
                if old is not None:
                    try:
                        old.join(timeout=0.5)
                    except Exception:
                        import logging

                        logging.getLogger(__name__).debug("silent except", exc_info=True)
