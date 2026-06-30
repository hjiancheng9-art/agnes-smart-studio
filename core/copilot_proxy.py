"""Copilot Proxy — OpenAI-compatible HTTP server wrapping Copilot CLI.

Turns GitHub Copilot CLI into an OpenAI-compatible API that CRUX can use
as a regular provider in models.json.

Usage:
    python core/copilot_proxy.py --port 11436

Then add to models.json:
    "copilot": {
        "name": "Copilot GPT-5-mini",
        "base_url": "http://127.0.0.1:11436/v1",
        "api_key": "no-key-needed",
        "models": { "pro": "gpt-5-mini", "light": "gpt-5-mini" }
    }

Architecture:
    CRUX → CruxClient → HTTP POST /v1/chat/completions
        → copilot_proxy.py (Flask/aiohttp)
            → subprocess: copilot -p "<prompt>" -m gpt-5-mini
                → GitHub Copilot API (authenticated via gh)
            ← parsed text → OpenAI-format JSON response

Why proxy instead of direct API:
    - Copilot uses OAuth token exchange (not simple API key)
    - Copilot CLI handles auth, session management, rate limiting
    - Proxy is a thin translation layer (~200 lines)
"""

from core.mcp_servers._mcp_utils import run_subprocess
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

__all__ = ["CopilotProxyServer", "run_proxy", "COPILOT_BINARY"]

COPILOT_BINARY = (
    os.environ.get("COPILOT_BIN")
    or os.path.expanduser("~/AppData/Roaming/npm/copilot.CMD")
)
# Fallback to which
import shutil
if not os.path.isfile(COPILOT_BINARY):
    found = shutil.which("copilot")
    if found:
        COPILOT_BINARY = found

DEFAULT_PORT = 11436
DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_TIMEOUT = 120

# Track active sessions for continuity
_sessions: dict[str, list[dict]] = {}  # session_id → [messages]
_lock = threading.Lock()


def _find_copilot() -> str:
    if os.path.isfile(COPILOT_BINARY):
        return COPILOT_BINARY
    raise FileNotFoundError(
        "Copilot CLI not found. Install: npm i -g @githubnext/github-copilot-cli\n"
        "Or set COPILOT_BIN env var to the copilot executable path."
    )


def _call_copilot(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    stream: bool = False,
    session_id: str | None = None,
) -> dict:
    """Call Copilot CLI with chat messages, return parsed response.

    Converts OpenAI-format messages to a prompt string for copilot CLI.
    Uses system message as prefix, combines user/assistant messages.
    """
    copilot = _find_copilot()

    # Build prompt from messages
    system_parts = []
    conversation_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Multimodal: extract text only
            texts = [p.get("text", "") for p in content if p.get("type") == "text"]
            content = "\n".join(texts)
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            conversation_parts.append(f"User: {content}")
        elif role == "assistant":
            conversation_parts.append(f"Assistant: {content}")

    system_prefix = "\n".join(system_parts) if system_parts else ""
    conversation = "\n\n".join(conversation_parts) if conversation_parts else ""

    # For single-turn, just use the last user message directly
    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            c = msg.get("content", "")
            if isinstance(c, list):
                c = "\n".join(p.get("text", "") for p in c if p.get("type") == "text")
            last_user = c
            break

    if not last_user:
        return {"error": "No user message found", "content": ""}

    # Build prompt: system context + user query
    prompt = last_user
    if system_prefix:
        prompt = f"[System Instructions]\n{system_prefix}\n\n[Task]\n{prompt}"
    if conversation_parts and len(conversation_parts) > 2:
        # Multi-turn: include conversation context
        prompt = f"[Conversation]\n{conversation}\n\n[Latest]\n{prompt}"

    # Build command (model selection via Copilot's default, no -m flag needed)
    cmd = [
        copilot,
        "-p", prompt,
        "--allow-all-tools",
        "--allow-all-paths",
    ]

    try:
        r = run_subprocess(cmd, timeout=timeout)
        output = r.stdout.strip()
        stderr = r.stderr.strip()

        if r.returncode != 0 and not output:
            output = f"[Copilot Error] {stderr}" if stderr else "[Copilot returned empty]"

        # Clean up output: remove ANSI, thinking markers, etc.
        output = _clean_output(output)

        return {
            "content": output,
            "model": model,
            "usage": {"prompt_tokens": len(prompt) // 3, "completion_tokens": len(output) // 3},
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout after {timeout}s", "content": "[Timeout]"}
    except Exception as e:
        return {"error": str(e), "content": f"[Error: {e}]"}


def _clean_output(text: str) -> str:
    """Remove ANSI codes, thinking markers, and other noise from Copilot output."""
    # Strip ANSI escape codes
    ansi_escape = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    text = ansi_escape.sub("", text)

    # Remove thinking/reasoning blocks
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL)

    # Remove <｜end▁of▁thinking｜> markers
    text = re.sub(r"^.*?<｜end▁of▁thinking｜>", "", text, count=1, flags=re.MULTILINE)

    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ════════════════════════════════════════════════════════════════
# HTTP Server
# ════════════════════════════════════════════════════════════════


class CopilotProxyHandler(BaseHTTPRequestHandler):
    """OpenAI-compatible /v1/chat/completions handler."""

    # Class-level session store
    _sessions: dict[str, list[dict]] = {}
    _default_model: str = DEFAULT_MODEL
    _default_timeout: int = DEFAULT_TIMEOUT

    def log_message(self, format, *args):
        """Suppress default logging to stderr."""
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        if self.path == "/v1/models":
            self._send_json({
                "object": "list",
                "data": [
                    {"id": "gpt-5-mini", "object": "model", "owned_by": "github-copilot"},
                    {"id": "gpt-5", "object": "model", "owned_by": "github-copilot"},
                ],
            })
        elif self.path == "/health":
            self._send_json({"status": "ok", "model": self._default_model})
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self._send_json({"error": "Only /v1/chat/completions supported"}, 404)
            return

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        model = data.get("model", self._default_model)
        messages = data.get("messages", [])
        stream = data.get("stream", False)
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 4096)
        session_id = data.get("user") or self.headers.get("X-Session-Id", "default")

        if not messages:
            self._send_json({"error": "No messages"}, 400)
            return

        # Call Copilot
        result = _call_copilot(
            messages=messages,
            model="auto" if model == "gpt-5-mini" else model,
            stream=stream,
            session_id=session_id,
        )

        if "error" in result:
            self._send_json({
                "error": {"message": result["error"], "type": "copilot_error"},
            }, 500)
            return

        # Build OpenAI-format response
        resp_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        response = {
            "id": resp_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["content"],
                },
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": result.get("usage", {}).get("completion_tokens", 0),
                "total_tokens": (
                    result.get("usage", {}).get("prompt_tokens", 0)
                    + result.get("usage", {}).get("completion_tokens", 0)
                ),
            },
        }

        # Update session history
        with _lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            self._sessions[session_id].extend(messages)
            self._sessions[session_id].append({
                "role": "assistant", "content": result["content"],
            })
            # Keep last 50 messages max
            if len(self._sessions[session_id]) > 50:
                self._sessions[session_id] = self._sessions[session_id][-50:]

        self._send_json(response)


class CopilotProxyServer:
    """Copilot proxy server manager."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, blocking: bool = False):
        """Start the proxy server."""
        self._server = HTTPServer(("127.0.0.1", self.port), CopilotProxyHandler)
        if blocking:
            print(f"Copilot Proxy: {self.url}/v1/chat/completions (gpt-5-mini)")
            self._server.serve_forever()
        else:
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            # Wait for startup
            time.sleep(0.5)
            return self.url

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None

    def health(self) -> bool:
        """Check if proxy is responding."""
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{self.url}/health", timeout=3)
            return json.loads(resp.read()).get("status") == "ok"
        except Exception:
            return False


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════


def run_proxy():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Copilot OpenAI-compatible proxy")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
    parser.add_argument("--model", default=None, help=f"Default model (default: {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=int, default=None, help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})")
    args = parser.parse_args()

    # Set module-level defaults for handler
    CopilotProxyHandler._default_model = args.model or DEFAULT_MODEL
    CopilotProxyHandler._default_timeout = args.timeout or DEFAULT_TIMEOUT

    # Verify copilot works
    try:
        _find_copilot()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    server = CopilotProxyServer(port=args.port)
    print(f"Copilot Proxy ({args.model}) → {server.url}/v1/chat/completions")
    print(f"Add to models.json: 'base_url': '{server.url}/v1'")
    server.start(blocking=True)


if __name__ == "__main__":
    run_proxy()
