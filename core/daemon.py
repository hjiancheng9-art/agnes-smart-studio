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
STARTUP_LOG_FILE = DAEMON_DIR / "startup_log.json"
PIPE_NAME = r"\\.\pipe\crux_daemon"
SCHEMA_VERSION = "crux.daemon.v1"


@dataclass
class StartupEvent:
    """Single timed event in the startup sequence."""
    name: str
    elapsed_ms: float


@dataclass
class StartupDiagnostics:
    """Records timing of daemon startup sequence — saved to JSON for post-mortem."""
    pid: int = 0
    started_at: float = 0.0
    events: list | None = None

    def mark(self, name: str) -> None:
        if self.events is None:
            self.events = []
        self.events.append(StartupEvent(name=name, elapsed_ms=(time.time() - self.started_at) * 1000))

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "started_at": self.started_at,
            "events": [{"name": e.name, "elapsed_ms": round(e.elapsed_ms, 1)} for e in (self.events or [])],
        }


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
        self._ws_thread: threading.Thread | None = None
        self._ws_port: int = 0
        self.startup = StartupDiagnostics(pid=os.getpid(), started_at=time.time())
        self.startup.mark("__init__")

    def start(self, background: bool = False) -> bool:
        with self._lock:
            if self._running:
                return False
            self.state.started_at = time.time()
            self.state.pid = os.getpid()
            self._running = True
            self.startup.started_at = time.time()
            self.startup.pid = os.getpid()
        self.startup.mark("lock_acquired")
        try:
            from core.watchdog import get_watchdog

            wd = get_watchdog()
            wd.start()
            self.state.watchdog_alive = wd.alive
            self.startup.mark("watchdog_ready")
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("Watchdog unavailable: %s", e)
            self.startup.mark("watchdog_skipped")
        try:
            from core.provider import get_provider_manager

            self.state.provider_active = get_provider_manager().active_provider
            self.startup.mark("provider_ready")
        except (ImportError, RuntimeError, OSError):
            logger.exception("[Daemon] provider init failed")
            self.startup.mark("provider_failed")
        self._save_startup_log()
        self._save_state()
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        self.startup.mark("daemon_ready")
        logger.info("[Daemon] PID %d active (startup %dms)",
                     self.state.pid, self.startup.events[-1].elapsed_ms if self.startup.events else 0)
        if background:
            self._thread = threading.Thread(target=self._serve, daemon=True, name="crux-daemon")
            self._thread.start()
            self._start_websocket()
            return True
        self._start_websocket()
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
        self._stop_websocket()
        self._save_startup_log()
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
            if isinstance(raw, bytes):
                try:
                    from core.encoding_fix import fix_garbled_bytes
                    data, _, _ = fix_garbled_bytes(raw)
                    data = data.strip()
                except ImportError:
                    data = raw.decode("utf-8", errors="replace").strip()
            else:
                data = raw.strip()
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
                    raw_data = conn.recv(4096)
                    try:
                        from core.encoding_fix import fix_garbled_bytes
                        data, _, _ = fix_garbled_bytes(raw_data)
                        data = data.strip()
                    except ImportError:
                        data = raw_data.decode("utf-8", errors="replace").strip()
                    resp = self._handle_command(data)
                    conn.send(resp.encode("utf-8"))
                    conn.close()
                except (RuntimeError, TimeoutError, OSError) as e:
                    logger.debug("Socket accept: %s", e)
                    continue
                except ValueError:
                    break
            s.close()
        except (RuntimeError, OSError, ValueError) as e:
            logger.debug("Socket serve: %s", e)

    # ── WebSocket channel (push-capable IPC) ──

    def _start_websocket(self) -> None:
        """Launch WebSocket server in a daemon thread if websockets is available."""
        try:
            import websockets  # noqa: F401
            self._ws_thread = threading.Thread(
                target=self._serve_websocket, daemon=True, name="crux-ws"
            )
            self._ws_thread.start()
        except ImportError:
            logger.debug("[Daemon] websockets not available — skipping WS channel")
        except Exception as e:
            logger.exception("[Daemon] WS start failed: %s", e)

    def _stop_websocket(self) -> None:
        """Signal the WS server to stop by setting _ws_port to 0."""
        self._ws_port = 0

    def _serve_websocket(self) -> None:
        """WebSocket server — alongside named pipe for push-capable IPC.
        
        Port is written to output/daemon/ws_port.txt for discovery.
        Protocol: JSON {cmd: str, ...} → same response as named pipe.
        """
        import asyncio

        import websockets

        WS_PORT_FILE = DAEMON_DIR / "ws_port.txt"

        async def handler(ws):
            async for message in ws:
                try:
                    data = json.loads(message)
                    cmd = data.get("cmd", "status")
                    resp = self._handle_command(cmd)
                    await ws.send(resp)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({"ok": False, "error": "invalid JSON"}))
                except Exception as e:
                    await ws.send(json.dumps({"ok": False, "error": str(e)}))

        async def serve():
            async with websockets.serve(handler, "127.0.0.1", 0) as server:
                sock = server.sockets[0]
                port = sock.getsockname()[1]
                self._ws_port = port
                try:
                    WS_PORT_FILE.write_text(str(port), encoding="utf-8")
                except OSError:
                    pass
                logger.info("[Daemon] WS channel on 127.0.0.1:%d", port)
                # Keep running until _ws_port is reset to 0
                while self._ws_port == port and self._running:
                    await asyncio.sleep(1)

        asyncio.run(serve())

    def _handle_command(self, cmd: str) -> str:
        parts = cmd.strip().split()
        op = parts[0].lower() if parts else "status"
        if op == "attach":
            self.state.sessions_active += 1
            self.state.total_sessions += 1
            return json.dumps({"ok": True, "session": self.state.sessions_active})
        if op == "detach":
            self.state.sessions_active = max(0, self.state.sessions_active - 1)
            return json.dumps({"ok": True, "session": self.state.sessions_active})
        if op == "stop":
            self.stop()
            return json.dumps({"ok": True, "stopped": True})
        if op == "status":
            return json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2)
        if op == "startup-log":
            return json.dumps(self.startup.to_dict(), ensure_ascii=False, indent=2)
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

    def _save_startup_log(self) -> None:
        with contextlib.suppress(OSError):
            STARTUP_LOG_FILE.write_text(json.dumps(self.startup.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

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
