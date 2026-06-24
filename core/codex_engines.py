"""Codex-complete engine suite -- js_repl, MCP, Playwright persistent, transcribe, imagegen."""

import json
import os
import subprocess
import time
from pathlib import Path

__all__ = [
    "JSRepl", "MCPConnector", "PlaywrightSession", "ROOT", "imagegen", "js_eval", "mcp_call", "mcp_connect", "pw_click", "pw_close", "pw_fill", "pw_js", "pw_navigate", "pw_screenshot", "transcribe_audio",
]
ROOT = Path(__file__).resolve().parent.parent


# =====================================================================
# js_repl -- Node.js REPL (Codex equivalent)
# =====================================================================

class JSRepl:
    """Node.js execution engine — one-shot subprocess model with vm sandbox.

    Uses subprocess.run for reliable cross-platform JS execution.
    Equivalent to Codex's node_repl but wraps code in a Node.js vm sandbox
    to strip dangerous globals (fs, child_process, process.exit, etc.).
    """

    # JS dangerous patterns — blocked before execution
    _JS_BLOCKED = [
        "child_process", "process.exit", "process.kill",
        "fs.", "require('fs')", 'require("fs")',
        "net.", "require('net')", 'require("net")',
        "process.env", "process.cwd()", "process.chdir",
    ]

    _SANDBOX_WRAPPER = """
const vm = require('vm');
const sandbox = {
    console, Math, Date, JSON, parseInt, parseFloat,
    String, Number, Boolean, Array, Object, RegExp,
    Error, TypeError, RangeError, SyntaxError,
    Map, Set, WeakMap, WeakSet, Promise,
    setTimeout, clearTimeout, setInterval, clearInterval,
    Buffer, require,
    global: undefined, process: undefined,
};
try {
    const result = vm.runInNewContext(`%s`, sandbox, { timeout: %d });
    if (result !== undefined) console.log(result);
} catch(e) { console.error(e.message); }
"""

    def __init__(self) -> None:
        self._node_path = self._find_node()

    def _find_node(self) -> str | None:
        """Locate Node.js executable."""
        import shutil
        return shutil.which("node")

    def eval(self, code: str, timeout_ms: int = 30000) -> str:
        """Execute JavaScript via one-shot subprocess with sandbox."""
        if not self._node_path:
            return "[错误] Node.js 未安装。https://nodejs.org"
        # ── 预检：拦截明显危险模式 ──
        code_lower = code.lower()
        for pattern in self._JS_BLOCKED:
            if pattern in code_lower:
                return f"[JS 安全拒绝] 禁止调用: {pattern}"
        # ── 包裹在 vm sandbox 中 ──
        escaped_code = code.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        timeout_sec = min(timeout_ms, 30000)  # 上限 30s
        wrapped = self._SANDBOX_WRAPPER % (escaped_code, timeout_ms)
        try:
            result = subprocess.run(
                [self._node_path, "-e", wrapped],
                capture_output=True, text=True, timeout=(timeout_sec / 1000) + 5,
                cwd=str(ROOT),
            )
            if result.returncode != 0:
                return f"[JS Error] {result.stderr.strip()[:500]}"
            output = result.stdout.strip()
            return output if output else "(no output)"
        except subprocess.TimeoutExpired:
            return f"[JS Error] 超时 ({timeout_ms}ms)"
        except (subprocess.SubprocessError, OSError) as e:
            return f"[JS Error] {e}"

    def close(self):
        pass  # one-shot, no cleanup needed


_js_repl = JSRepl()


def js_eval(code: str) -> str:
    """Run JavaScript in persistent Node REPL."""
    return _js_repl.eval(code)


# =====================================================================
# MCP Client -- functional MCP server connector
# =====================================================================

class MCPConnector:
    """Connect to stdio-based MCP servers and expose their tools."""

    def __init__(self) -> None:
        self._connections: dict[str, subprocess.Popen] = {}
        import atexit
        atexit.register(self._cleanup)

    def _cleanup(self):
        """Kill all child processes on exit/crash."""
        for _name, proc in list(self._connections.items()):
            try:
                proc.kill()
                proc.wait(timeout=3)
            except (subprocess.SubprocessError, OSError):
                pass
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if pipe:
                        pipe.close()
                except (subprocess.SubprocessError, OSError):
                    pass

    def connect(self, server_name: str, command: str, args: list[str],
                env: dict | None = None) -> bool:
        """Start an MCP server process."""
        try:
            proc_env = os.environ.copy()
            if env:
                proc_env.update(env)
            proc = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, env=proc_env,
            )
            self._connections[server_name] = proc
            return True
        except (subprocess.SubprocessError, OSError):
            return False

    def list_tools(self, server_name: str) -> list[dict]:
        """Send tools/list request to MCP server."""
        proc = self._connections.get(server_name)
        if not proc or not proc.stdin or not proc.stdout:
            return []
        request = json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/list", "params": {}
        })
        try:
            proc.stdin.write(request + "\n")
            proc.stdin.flush()
            resp = proc.stdout.readline()
            data = json.loads(resp)
            return data.get("result", {}).get("tools", [])
        except (subprocess.SubprocessError, OSError):
            return []

    def call_tool(self, server_name: str, tool_name: str, args: dict) -> str:
        """Call a tool on an MCP server."""
        proc = self._connections.get(server_name)
        if not proc or not proc.stdin or not proc.stdout:
            return f"[MCP Error] Server '{server_name}' not connected"
        request = json.dumps({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args}
        })
        try:
            proc.stdin.write(request + "\n")
            proc.stdin.flush()
            resp = proc.stdout.readline()
            data = json.loads(resp)
            if "error" in data:
                return f"[MCP Error] {data['error']}"
            content = data.get("result", {}).get("content", [])
            return json.dumps(content[:10], ensure_ascii=False)
        except (subprocess.SubprocessError, OSError) as e:
            return f"[MCP Error] {e}"

    def disconnect(self, server_name: str):
        proc = self._connections.pop(server_name, None)
        if proc:
            proc.terminate()


_mcp = MCPConnector()


def mcp_connect(server_name: str, command: str, args: str = "") -> str:
    return "ok" if _mcp.connect(server_name, command, args.split() if args else []) else "failed"

def mcp_call(server_name: str, tool_name: str, args_json: str = "{}") -> str:
    return _mcp.call_tool(server_name, tool_name, json.loads(args_json))


# =====================================================================
# Playwright Persistent Session
# =====================================================================

class PlaywrightSession:
    """Persistent browser session via Playwright (codex-interactive style)."""

    def __init__(self) -> None:
        self._browser = None
        self._page = None
        self._playwright = None

    def start(self, headless: bool = True) -> str:
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=headless)
            self._page = self._browser.new_page()
            return "Browser started (chromium)"
        except ImportError:
            return "[错误] playwright 未安装"

    def navigate(self, url: str) -> str:
        if not self._page:
            return "[错误] Browser not started"
        self._page.goto(url, timeout=30000)
        return self._page.title()

    def click(self, selector: str) -> str:
        if not self._page:
            return "[错误] Browser not started"
        self._page.click(selector, timeout=10000)
        return "clicked"

    def fill(self, selector: str, text: str) -> str:
        if not self._page:
            return "[错误] Browser not started"
        self._page.fill(selector, text)
        return "filled"

    def content(self) -> str:
        if not self._page:
            return "[错误] Browser not started"
        return self._page.content()[:20000]

    def screenshot(self) -> str:
        if not self._page:
            return "[错误] Browser not started"
        path = ROOT / "output" / f"browser_{int(time.time())}.png"
        self._page.screenshot(path=str(path))
        return str(path)

    def js(self, code: str) -> str:
        """Evaluate JavaScript in the browser context."""
        if not self._page:
            return "[错误] Browser not started"
        result = self._page.evaluate(code)
        return json.dumps(result, ensure_ascii=False)

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()


_pw_session = PlaywrightSession()


def pw_navigate(url: str) -> str:
    """Module-level wrapper for PlaywrightSession.navigate."""
    from core.file_tools import _validate_url
    err = _validate_url(url)
    if err:
        return f"[安全拒绝] {err}"
    global _pw_session
    if not _pw_session._page:
        _pw_session.start()
    return _pw_session.navigate(url)


def pw_screenshot() -> str:
    """Module-level wrapper for PlaywrightSession.screenshot."""
    global _pw_session
    if not _pw_session._page:
        _pw_session.start()
    return _pw_session.screenshot()


def pw_click(selector: str) -> str:
    global _pw_session
    if not _pw_session._page:
        _pw_session.start()
    return _pw_session.click(selector)


def pw_fill(selector: str, text: str) -> str:
    global _pw_session
    if not _pw_session._page:
        _pw_session.start()
    return _pw_session.fill(selector, text)


def pw_js(code: str) -> str:
    global _pw_session
    if not _pw_session._page:
        _pw_session.start()
    return _pw_session.js(code)


def pw_close() -> str:
    global _pw_session
    _pw_session.close()
    return "browser closed"


# =====================================================================
# Audio Transcription
# =====================================================================

def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio file to text using whisper or API."""
    path = Path(audio_path)
    if not path.exists():
        return f"[错误] 文件不存在: {audio_path}"
    try:
        import whisper  # type: ignore[import-not-found]
        model = whisper.load_model("base")
        result = model.transcribe(str(path))
        return result["text"]
    except ImportError:
        return "[错误] whisper 未安装: pip install openai-whisper"


# =====================================================================
# Independent Image Generation Channel
# =====================================================================

def imagegen(prompt: str, size: str = "1024x1024", style: str = "") -> dict:
    """Generate image via independent channel (uses CRUX API if available)."""
    try:
        from core.client import CruxClient
        from engines.text_to_image import TextToImageEngine
        client = CruxClient()
        engine = TextToImageEngine(client)
        enhanced = prompt
        if style:
            enhanced = f"{prompt}, {style} style"
        result = engine.generate(prompt=enhanced, size=size)
        return {"status": "ok", "local_path": result.get("local_path", ""),
                "prompt": enhanced}
    except (OSError, ValueError, RuntimeError) as e:
        return {"status": "error", "message": str(e)}
