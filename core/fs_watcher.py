"""File system watcher — monitor directory changes via polling.

Tools:
    fs_watch_start  Start watching a directory
    fs_watch_stop   Stop a watch
    fs_watch_list   List active watches and recent events

Singleton pattern — one background thread handles all watches.
"""

from __future__ import annotations

import atexit
import collections
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class WatchConfig:
    watch_id: str
    path: str
    patterns: str
    recursive: bool
    created_at: float = field(default_factory=time.time)


class FsWatcher:
    """Background file system watcher using polling.

    Singleton — use get_fs_watcher() to access.
    """

    _instance: FsWatcher | None = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._watches: dict[str, WatchConfig] = {}
        self._events: dict[str, collections.deque] = {}
        self._file_state: dict[str, dict[str, tuple[float, int]]] = {}  # watch_id -> {path: (mtime, size)}
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── public API ──────────────────────────────────────────────

    def start(self) -> None:
        """Start the background watcher thread (idempotent)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="crux-fs-watcher")
        self._thread.start()

    def stop(self) -> None:
        """Stop the watcher thread and clean up."""
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        with self._lock:
            self._watches.clear()
            self._events.clear()
            self._file_state.clear()

    def add_watch(self, path: str, patterns: str = "*", recursive: bool = True) -> str:
        """Add a directory watch. Returns watch_id."""
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            raise ValueError(f"Not a directory: {path}")

        watch_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._watches[watch_id] = WatchConfig(
                watch_id=watch_id,
                path=path,
                patterns=patterns,
                recursive=recursive,
            )
            self._events[watch_id] = collections.deque(maxlen=500)
            # Initialize file state snapshot
            self._file_state[watch_id] = {}
            self._snapshot_dir(watch_id, path, patterns, recursive)

        self.start()
        return watch_id

    def remove_watch(self, watch_id: str) -> bool:
        """Remove a watch by ID. Returns True if found."""
        with self._lock:
            if watch_id in self._watches:
                del self._watches[watch_id]
                self._events.pop(watch_id, None)
                self._file_state.pop(watch_id, None)
                return True
        return False

    def get_events(self, watch_id: str = "") -> list[dict]:
        """Get recent events. If watch_id is empty, return summary for all watches."""
        with self._lock:
            if watch_id:
                events = self._events.get(watch_id)
                return list(events) if events else []
            # Summary: all watches
            result = []
            for wid, cfg in self._watches.items():
                evts = list(self._events.get(wid, collections.deque()))
                result.append(
                    {
                        "watch_id": wid,
                        "path": cfg.path,
                        "patterns": cfg.patterns,
                        "recursive": cfg.recursive,
                        "event_count": len(evts),
                        "recent_events": evts[-20:],
                    }
                )
            return result

    # ── internal ────────────────────────────────────────────────

    def _snapshot_dir(self, watch_id: str, root: str, patterns: str, recursive: bool) -> None:
        """Take initial snapshot of file states."""
        file_state = self._file_state.setdefault(watch_id, {})
        try:
            for entry in os.scandir(root):
                if entry.is_file():
                    if _match_pattern(entry.name, patterns):
                        stat = entry.stat()
                        file_state[entry.path] = (stat.st_mtime, stat.st_size)
                elif entry.is_dir() and recursive:
                    self._snapshot_dir(watch_id, entry.path, patterns, recursive)
        except PermissionError:
            pass

    def _poll_directory(self, watch_id: str, root: str, patterns: str, recursive: bool) -> list[dict]:
        """Poll one directory and return detected events."""
        events: list[dict] = []
        file_state = self._file_state.setdefault(watch_id, {})
        current_paths: set[str] = set()

        try:
            for entry in os.scandir(root):
                if entry.is_file():
                    if not _match_pattern(entry.name, patterns):
                        continue
                    stat = entry.stat()
                    current_paths.add(entry.path)
                    prev = file_state.get(entry.path)
                    if prev is None:
                        events.append({"type": "created", "path": entry.path, "timestamp": time.time()})
                        file_state[entry.path] = (stat.st_mtime, stat.st_size)
                    elif prev[0] != stat.st_mtime or prev[1] != stat.st_size:
                        events.append({"type": "modified", "path": entry.path, "timestamp": time.time()})
                        file_state[entry.path] = (stat.st_mtime, stat.st_size)
                elif entry.is_dir() and recursive:
                    sub_events = self._poll_directory(watch_id, entry.path, patterns, recursive)
                    events.extend(sub_events)
        except PermissionError:
            pass

        # Detect deletions
        for path in list(file_state.keys()):
            if path.startswith(root) and path not in current_paths:
                events.append({"type": "deleted", "path": path, "timestamp": time.time()})
                del file_state[path]

        return events

    def _poll_loop(self) -> None:
        """Main polling loop running in background daemon thread."""
        while self._running and not self._stop_event.is_set():
            with self._lock:
                watch_ids = list(self._watches.keys())

            for wid in watch_ids:
                with self._lock:
                    cfg = self._watches.get(wid)
                if cfg is None:
                    continue
                try:
                    evts = self._poll_directory(wid, cfg.path, cfg.patterns, cfg.recursive)
                    if evts:
                        with self._lock:
                            queue = self._events.get(wid)
                            if queue is not None:
                                queue.extend(evts)
                except Exception:
                    pass  # Don't crash the poll loop on transient errors

            self._stop_event.wait(0.5)


def _match_pattern(name: str, patterns: str) -> bool:
    """Simple glob match for file patterns (supports * and *.* style)."""
    import fnmatch

    for pat in patterns.split(";"):
        pat = pat.strip()
        if pat and fnmatch.fnmatch(name, pat):
            return True
    return patterns == "*"


# ── singleton ──────────────────────────────────────────────────────


def get_fs_watcher() -> FsWatcher:
    """Get or create the singleton FsWatcher."""
    if FsWatcher._instance is None:
        FsWatcher._instance = FsWatcher()
        atexit.register(FsWatcher._instance.stop)
    return FsWatcher._instance


def reset_fs_watcher() -> None:
    """Reset singleton for test isolation."""
    if FsWatcher._instance:
        FsWatcher._instance.stop()
        FsWatcher._instance = None


# ── tool functions ──────────────────────────────────────────────────


def fs_watch_start(path: str, patterns: str = "*", recursive: bool = True) -> str:
    """Start watching a directory for file changes.

    Args:
        path: Directory path to watch
        patterns: Glob patterns separated by semicolon, e.g. "*.py;*.js"
        recursive: Watch subdirectories (default: true)

    Returns:
        JSON with watch_id
    """
    if not path:
        return "[错误] path 参数不能为空"
    if not os.path.isdir(path):
        return f"[错误] 目录不存在: {path}"

    try:
        watcher = get_fs_watcher()
        watch_id = watcher.add_watch(path, patterns, recursive)
        return json.dumps(
            {
                "status": "ok",
                "watch_id": watch_id,
                "path": path,
                "patterns": patterns,
                "recursive": recursive,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return f"[错误] 启动文件监控失败: {e}"


def fs_watch_stop(watch_id: str) -> str:
    """Stop a file watch by ID.

    Args:
        watch_id: Watch ID returned by fs_watch_start

    Returns:
        JSON with status
    """
    if not watch_id:
        return "[错误] watch_id 参数不能为空"

    try:
        watcher = get_fs_watcher()
        removed = watcher.remove_watch(watch_id)
        if removed:
            return json.dumps({"status": "ok", "watch_id": watch_id}, ensure_ascii=False)
        return f"[错误] 未找到 watch_id: {watch_id}"
    except Exception as e:
        return f"[错误] 停止文件监控失败: {e}"


def fs_watch_list(watch_id: str = "") -> str:
    """List active watches and recent events.

    Args:
        watch_id: Specific watch ID (empty = list all)

    Returns:
        JSON with watch status and recent events
    """
    try:
        watcher = get_fs_watcher()
        result = watcher.get_events(watch_id)
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return f"[错误] 获取文件监控状态失败: {e}"
