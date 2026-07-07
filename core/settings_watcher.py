"""Settings hot-reload — watch models.json and tools.json for changes.

When config files change on disk, auto-reload without restart.
Uses polling (no filesystem watcher dependency on Windows).
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("crux.settings_watcher")

_WATCHED: dict[str, float] = {}  # path → last mtime
_watcher_thread: threading.Thread | None = None
_running = False


def _get_mtimes() -> dict[str, float]:
    """Get current mtimes for all watched files."""
    result = {}
    for path in _WATCHED:
        with contextlib.suppress(OSError):
            result[path] = os.path.getmtime(path)
    return result


def _on_change(path: str):
    """Called when a watched file changes."""
    if "models.json" in path:
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            mgr.load()
            logger.info("models.json reloaded (hot-reload)")
        except Exception as e:
            logger.debug("models.json reload failed: %s", e)
    elif "tools.json" in path:
        try:
            from core.tools import get_registry

            reg = get_registry()
            reg.load(mcp=True)
            logger.info("tools.json reloaded (hot-reload)")
        except Exception as e:
            logger.debug("tools.json reload failed: %s", e)


def _watch_loop(interval: float = 2.0):
    """Background polling loop."""
    global _running
    while _running:
        try:
            current = _get_mtimes()
            for path, old_mtime in _WATCHED.items():
                new_mtime = current.get(path, 0)
                if new_mtime > old_mtime:
                    _WATCHED[path] = new_mtime
                    _on_change(path)
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)
        time.sleep(interval)


def start_watcher(paths: list[str] | None = None, interval: float = 2.0):
    """Start background config file watcher.

    Args:
        paths: List of absolute paths to watch.
               Default: models.json + tools.json in project root.
        interval: Polling interval in seconds.
    """
    global _WATCHED, _watcher_thread, _running

    if paths is None:
        paths = [
            str(ROOT / "models.json"),
            str(ROOT / "tools.json"),
        ]

    for p in paths:
        try:
            _WATCHED[p] = os.path.getmtime(p)
        except OSError:
            _WATCHED[p] = 0

    if _watcher_thread is not None and _watcher_thread.is_alive():
        return  # Already running

    _running = True
    _watcher_thread = threading.Thread(target=_watch_loop, args=(interval,), daemon=True)
    _watcher_thread.start()
    logger.debug("settings watcher started (%d files, %ss interval)", len(_WATCHED), interval)


def stop_watcher():
    """Stop the background watcher thread."""
    global _running
    _running = False
