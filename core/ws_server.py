"""WebSocket server — push real-time messages to connected clients.

Tools:
    ws_server_start      Start WebSocket server
    ws_server_stop       Stop the server
    ws_server_broadcast  Send message to all clients
    ws_server_status     Get server status

Singleton pattern — one WebSocket server per process.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import threading
import time


class WsServer:
    """Background WebSocket server for real-time messaging.

    Singleton — use get_ws_server() to access.
    """

    _instance: WsServer | None = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._port: int = 0
        self._host: str = "127.0.0.1"
        self._clients: set = set()
        self._started_at: float = 0

    # ── public API ──────────────────────────────────────────────

    def start(self, port: int = 0, host: str = "127.0.0.1") -> tuple[int, str]:
        """Start WebSocket server. Returns (port, url)."""
        if self._running:
            self.stop()

        self._port = port
        self._host = host
        self._running = True
        self._started_at = time.time()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(host, port),
            daemon=True,
            name="crux-ws-server",
        )
        self._thread.start()
        time.sleep(0.1)  # Let the server start

        return self._port, f"ws://{self._host}:{self._port}"

    def stop(self) -> None:
        """Stop the WebSocket server."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._started_at = 0

    def broadcast(self, message: str) -> int:
        """Send message to all connected clients. Returns count sent."""
        # We queue the broadcast for the event loop
        with self._lock:
            count = len(self._clients)
            # Store as a pending broadcast — the event loop thread picks it up
            self._pending_broadcast = message
        return count

    def status(self) -> dict:
        """Return server status."""
        with self._lock:
            uptime = time.time() - self._started_at if self._started_at > 0 else 0
            return {
                "running": self._running,
                "host": self._host,
                "port": self._port,
                "client_count": len(self._clients),
                "uptime_seconds": round(uptime, 1),
                "url": f"ws://{self._host}:{self._port}" if self._port else "",
            }

    # ── internal ────────────────────────────────────────────────

    def _run_loop(self, host: str, port: int) -> None:
        """Run the asyncio event loop with WebSocket server in daemon thread."""
        try:
            import websockets
        except ImportError:
            self._running = False
            return

        async def _handler(ws):
            """Handle a single WebSocket connection."""
            with self._lock:
                self._clients.add(ws)
            try:
                async for _msg in ws:
                    pass  # We don't process incoming messages (one-way server push)
            finally:
                with self._lock:
                    self._clients.discard(ws)

        async def _serve():
            try:
                async with websockets.serve(
                    _handler,
                    host,
                    port,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                ) as server:
                    # Capture actual port
                    sockets = server.sockets
                    if sockets:
                        self._port = sockets[0].getsockname()[1]

                    # Broadcast loop
                    while self._running:
                        msg = getattr(self, "_pending_broadcast", None)
                        if msg:
                            with self._lock:
                                self._pending_broadcast = None
                                dead = set()
                                for ws in list(self._clients):
                                    try:
                                        await ws.send(
                                            json.dumps(
                                                {
                                                    "type": "broadcast",
                                                    "message": msg,
                                                    "timestamp": time.time(),
                                                },
                                                ensure_ascii=False,
                                            )
                                        )
                                    except Exception:
                                        dead.add(ws)
                                self._clients -= dead
                        await asyncio.sleep(0.1)

            except OSError:
                self._running = False

        try:
            asyncio.run(_serve())
        except Exception:
            self._running = False


# ── singleton ──────────────────────────────────────────────────────


def get_ws_server() -> WsServer:
    """Get or create the singleton WsServer."""
    if WsServer._instance is None:
        WsServer._instance = WsServer()
        atexit.register(WsServer._instance.stop)
    return WsServer._instance


def reset_ws_server() -> None:
    """Reset singleton for test isolation."""
    if WsServer._instance:
        WsServer._instance.stop()
        WsServer._instance = None


# ── tool functions ──────────────────────────────────────────────────


def ws_server_start(port: int = 0, host: str = "127.0.0.1") -> str:
    """Start a WebSocket server for real-time push.

    Args:
        port: Port (default: 0 = auto-assign)
        host: Bind address (default: 127.0.0.1)

    Returns:
        JSON with server URL
    """
    try:
        import websockets  # noqa: F401  # pyright: ignore[reportUnusedImport]
    except ImportError:
        return "[错误] websockets 库未安装。运行: pip install websockets"

    try:
        server = get_ws_server()
        actual_port, url = server.start(port, host)
        return json.dumps(
            {
                "status": "ok",
                "url": url,
                "port": actual_port,
                "host": host,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return f"[错误] 启动 WebSocket 服务器失败: {e}"


def ws_server_stop() -> str:
    """Stop the WebSocket server.

    Returns:
        JSON with status
    """
    try:
        server = get_ws_server()
        server.stop()
        return json.dumps({"status": "ok"}, ensure_ascii=False)
    except Exception as e:
        return f"[错误] 停止 WebSocket 服务器失败: {e}"


def ws_server_broadcast(message: str) -> str:
    """Send a message to all connected WebSocket clients.

    Args:
        message: Text message to broadcast

    Returns:
        JSON with client count
    """
    if not message:
        return "[错误] message 参数不能为空"

    try:
        server = get_ws_server()
        count = server.broadcast(message)
        return json.dumps(
            {
                "status": "ok",
                "sent_to": count,
                "message_length": len(message),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return f"[错误] WebSocket 广播失败: {e}"


def ws_server_status() -> str:
    """Get WebSocket server status and connected client count.

    Returns:
        JSON with server status
    """
    try:
        server = get_ws_server()
        return json.dumps(server.status(), ensure_ascii=False, indent=2)
    except Exception as e:
        return f"[错误] 获取 WebSocket 状态失败: {e}"
