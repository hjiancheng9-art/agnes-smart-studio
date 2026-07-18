"""Webhook receiver — local HTTP server for inbound webhooks.

Tools:
    webhook_start   Start HTTP webhook server
    webhook_stop    Stop the server
    webhook_list    List received webhook payloads

Singleton pattern — one HTTP server per process.
"""

from __future__ import annotations

import atexit
import collections
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

_MAX_BODY = 4096  # Truncate stored body at 4KB


class _WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler that stores webhook payloads.

    Note: this class is configured by the WebhookServer singleton
    at handler creation time (via the server instance). The server
    object carries a reference to the WebhookServer's store.
    """

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(min(content_length, _MAX_BODY * 2))
        body = body_bytes.decode("utf-8", errors="replace")[:_MAX_BODY]

        store: collections.deque = getattr(self.server, "_webhook_store", collections.deque())
        store.append(
            {
                "timestamp": time.time(),
                "method": "POST",
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
                "source_ip": self.client_address[0],
            }
        )

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"webhook server running"}')

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # Suppress default logging to stderr


class WebhookServer:
    """Background HTTP server for receiving webhooks.

    Singleton — use get_webhook_server() to access.
    """

    _instance: WebhookServer | None = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0
        self._running = False
        self._store: collections.deque = collections.deque(maxlen=200)

    # ── public API ──────────────────────────────────────────────

    def start(self, port: int = 8765, path: str = "/webhook") -> tuple[int, str]:
        """Start the HTTP server. Returns (port, url)."""
        if self._running:
            self.stop()

        self._port = port
        self._running = True
        self._thread = threading.Thread(
            target=self._serve,
            args=(port, path),
            daemon=True,
            name="crux-webhook",
        )
        self._thread.start()
        time.sleep(0.1)  # Let the server socket bind

        actual_port = self._port
        return actual_port, f"http://127.0.0.1:{actual_port}{path}"

    def stop(self) -> None:
        """Stop the HTTP server."""
        self._running = False
        if self._httpd:
            try:
                self._httpd.shutdown()
            except Exception:
                import logging; logging.getLogger('crux').debug('silent except', exc_info=True)
            self._httpd = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None

    def list_payloads(self, limit: int = 20) -> list[dict]:
        """Return recent webhook payloads."""
        with self._lock:
            items = list(self._store)
            return items[-limit:]

    def store(self) -> collections.deque:
        """Return the shared store deque."""
        return self._store

    # ── internal ────────────────────────────────────────────────

    def _serve(self, port: int, path: str) -> None:
        """Run the HTTP server in the background thread."""
        try:
            self._httpd = HTTPServer(("127.0.0.1", port), _WebhookHandler)
            self._port = self._httpd.server_address[1]
            # Attach the store to the server so handlers can access it
            self._httpd._webhook_store = self._store  # type: ignore[attr-defined]
            self._httpd.timeout = 1.0
            while self._running:
                self._httpd.handle_request()
        except OSError:
            if self._running:
                self._port = 0
        finally:
            self._running = False


# ── singleton ──────────────────────────────────────────────────────


def get_webhook_server() -> WebhookServer:
    """Get or create the singleton WebhookServer."""
    if WebhookServer._instance is None:
        WebhookServer._instance = WebhookServer()
        atexit.register(WebhookServer._instance.stop)
    return WebhookServer._instance


def reset_webhook_server() -> None:
    """Reset singleton for test isolation."""
    if WebhookServer._instance:
        WebhookServer._instance.stop()
        WebhookServer._instance = None


# ── tool functions ──────────────────────────────────────────────────


def webhook_start(port: int = 8765, path: str = "/webhook") -> str:
    """Start a local HTTP server to receive webhooks.

    Args:
        port: Port to listen on (default: 8765)
        path: URL path to accept webhooks on (default: /webhook)

    Returns:
        JSON with server URL
    """
    if not 1024 <= port <= 65535:
        return f"[错误] 端口 {port} 不在有效范围 (1024-65535)"

    try:
        server = get_webhook_server()
        actual_port, url = server.start(port, path)
        return json.dumps(
            {
                "status": "ok",
                "url": url,
                "port": actual_port,
                "path": path,
                "note": "仅监听 127.0.0.1，仅接受 POST 请求",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return f"[错误] 启动 Webhook 服务器失败: {e}"


def webhook_stop() -> str:
    """Stop the webhook server.

    Returns:
        JSON with status
    """
    try:
        server = get_webhook_server()
        server.stop()
        return json.dumps({"status": "ok"}, ensure_ascii=False)
    except Exception as e:
        return f"[错误] 停止 Webhook 服务器失败: {e}"


def webhook_list(limit: int = 20) -> str:
    """List recently received webhook payloads.

    Args:
        limit: Max payloads to return (default: 20)

    Returns:
        JSON array of recent webhook payloads
    """
    try:
        server = get_webhook_server()
        payloads = server.list_payloads(limit)
        return json.dumps(
            {
                "total_stored": len(server._store),
                "returned": len(payloads),
                "payloads": payloads,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except Exception as e:
        return f"[错误] 获取 Webhook 列表失败: {e}"
