"""Daemon — CRUX 常驻态。真 IPC。
Windows: named pipe `\\\\.\\pipe\\crux_daemon`
监听 attach/detach/status/stop 命令。
内置信号处理，Watchdog 随 daemon 生命周期自动启停。
Usage: from core.daemon import get_daemon
get_daemon().start()
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("crux.daemon")
ROOT = Path(__file__).resolve().parent.parent
DAEMON_DIR = ROOT / "output" / "daemon"
DAEMON_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DAEMON_DIR / "daemon_state.json"
PIPE_NAME = r"\\.\pipe\crux_daemon"
SCHEMA_VERSION = "crux.daemon.v1"


@dataclass
class DaemonState:
    pid: int = 0
    started_at: float = 0.0
    sessions_active: int = 0
    total_sessions: int = 0
    uptime: float = 0.0
    watchdog_alive: bool = False
    plugins_loaded: int = 0
    provider_active: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "pid": self.pid,
            "started_at": self.started_at,
            "sessions_active": self.sessions_active,
            "total_sessions": self.total_sessions,
            "uptime": time.time() - self.started_at if self.started_at else 0,
            "watchdog_alive": self.watchdog_alive,
            "plugins_loaded": self.plugins_loaded,
            "provider_active": self.provider_active,
        }


class Daemon:
    def __init__(self) -> None:
        self.state = DaemonState(pid=os.getpid())
        self._running = False
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self, background: bool = False) -> bool:
        with self._lock:
            if self._running:
                return False
            self.state.started_at = time.time()
            self.state.pid = os.getpid()
            self._running = True
        try:
            from core.watchdog import get_watchdog

            wd = get_watchdog()
            wd.start()
            self.state.watchdog_alive = wd.alive
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("Watchdog unavailable: %s", e)
        try:
            from core.provider import get_provider_manager

            self.state.provider_active = get_provider_manager().active_provider
        except (ImportError, RuntimeError, OSError):
            logger.exception("[Daemon] provider init failed")
        self._save_state()
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        logger.info("[Daemon] PID %d active", self.state.pid)
        if background:
            self._thread = threading.Thread(target=self._serve, daemon=True, name="crux-daemon")
            self._thread.start()
            return True
        self._serve()
        return True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
        try:
            from core.watchdog import get_watchdog

            get_watchdog().stop()
        except (ImportError, RuntimeError, OSError) as e:
            logger.exception("[Daemon] watchdog stop failed: %s", e)
        self._save_state()
        logger.info("[Daemon] stopped")

    def _serve(self) -> None:
        while self._running:
            try:
                self._accept_one()
            except (RuntimeError, OSError, ValueError) as e:
                logger.debug("Pipe accept: %s", e)
            time.sleep(1)

    def _accept_one(self) -> None:
        try:
            import pywintypes  # noqa: F401
            import win32file
            import win32pipe

            pipe = win32pipe.CreateNamedPipe(
                PIPE_NAME,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                1,
                4096,
                4096,
                1000,
                None,  # type: ignore[arg-type]
            )
            win32pipe.ConnectNamedPipe(pipe, None)
            raw: bytes | str = win32file.ReadFile(pipe, 4096)[1]
            data = raw.decode("utf-8").strip() if isinstance(raw, bytes) else raw.strip()
            resp = self._handle_command(data)
            win32file.WriteFile(pipe, resp.encode("utf-8"))
            win32file.CloseHandle(pipe)
        except ImportError:
            # No pywin32 — use simple socket fallback
            self._serve_socket()

    def _serve_socket(self) -> None:
        try:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 4367))
            s.listen(1)
            s.settimeout(5)
            while self._running:
                try:
                    conn, _ = s.accept()
                    data = conn.recv(4096).decode("utf-8").strip()
                    resp = self._handle_command(data)
                    conn.send(resp.encode("utf-8"))
                    conn.close()
                except (RuntimeError, TimeoutError, OSError) as e:
                    logger.debug("Socket accept: %s", e)
                    continue
                except (RuntimeError, OSError, ValueError):
                    break
            s.close()
        except (RuntimeError, OSError, ValueError) as e:
            logger.debug("Socket serve: %s", e)

    def _handle_command(self, cmd: str) -> str:
        parts = cmd.strip().split()
        op = parts[0].lower() if parts else "status"
        if op == "attach":
            self.state.sessions_active += 1
            self.state.total_sessions += 1
            return json.dumps({"ok": True, "session": self.state.sessions_active})
        elif op == "detach":
            self.state.sessions_active = max(0, self.state.sessions_active - 1)
            return json.dumps({"ok": True, "session": self.state.sessions_active})
        elif op == "stop":
            self.stop()
            return json.dumps({"ok": True, "stopped": True})
        elif op == "status":
            return json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2)
        else:
            return json.dumps({"ok": False, "error": f"unknown command: {op}"})

    def attach(self) -> bool:
        self.state.sessions_active += 1
        self.state.total_sessions += 1
        return True

    def detach(self) -> None:
        self.state.sessions_active = max(0, self.state.sessions_active - 1)

    def _save_state(self) -> None:
        with contextlib.suppress(OSError):
            STATE_FILE.write_text(json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def is_running(self) -> bool:
        return self._running

    def summary(self) -> str:
        s = self.state
        return f"""\n## Daemon
  PID: {s.pid} | uptime: {int(time.time() - s.started_at) if s.started_at else 0}s
  sessions: {s.sessions_active} active / {s.total_sessions} total
  watchdog: {"alive" if s.watchdog_alive else "off"} | provider: {s.provider_active}"""


_daemon: Daemon | None = None


def get_daemon() -> Daemon:
    global _daemon
    if _daemon is None:
        _daemon = Daemon()
    return _daemon


def reset_daemon() -> None:
    """Stop the global daemon (if running) and drop the singleton.

    Used for test isolation. A subsequent get_daemon() returns a fresh Daemon.
    """
    global _daemon
    if _daemon is not None:
        with contextlib.suppress(Exception):
            _daemon.stop()
        _daemon = None
