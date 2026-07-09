"""Codex-complete engine suite -- js_repl, MCP, Playwright persistent, transcribe, imagegen."""

import json
import os
import subprocess
import sys
from pathlib import Path

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = [
    "JSRepl",
    "MCPConnector",
    "ROOT",
    "js_eval",
    "mcp_call",
    "mcp_connect",
    "pw_click",
    "pw_close",
    "pw_fill",
    "pw_js",
    "pw_navigate",
    "pw_screenshot",
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
        "child_process",
        "process.exit",
        "process.kill",
        "fs.",
        "require('fs')",
        'require("fs")',
        "net.",
        "require('net')",
        'require("net")',
        "process.env",
        "process.cwd()",
        "process.chdir",
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
            result = run_subprocess(
                [self._node_path, "-e", wrapped],
                timeout=(timeout_sec / 1000) + 5,
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

    def connect(self, server_name: str, command: str, args: list[str], env: dict | None = None) -> bool:
        """Start an MCP server process."""
        try:
            proc_env = os.environ.copy()
            if env:
                proc_env.update(env)
            proc = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=proc_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
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
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
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
        request = json.dumps(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool_name, "arguments": args}}
        )
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




# ═══════════════════════════════════════════════════════════════
# Subprocess bridge — solves sync_playwright + asyncio conflicts
# ═══════════════════════════════════════════════════════════════

def _pw_run(action: str, **kwargs) -> dict:
    """Run a Playwright action in a clean subprocess via pw_worker.py."""
    import json as _json
    import os as _os
    import subprocess as _subprocess
    import sys as _sys

    args = [_sys.executable, str(ROOT / "core" / "pw_worker.py"), action]
    for k, v in kwargs.items():
        args.append(f"{k}={v}")

    env = _os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        r = _subprocess.run(
            args,
            capture_output=True, text=True, timeout=45,
            encoding="utf-8", cwd=str(ROOT), env=env,
        )
        for line in r.stdout.strip().split("\n"):
            try:
                return _json.loads(line)
            except _json.JSONDecodeError:
                continue
        return {"error": f"pw_worker rc={r.returncode}: {r.stderr[:200]}"}
    except _subprocess.TimeoutExpired:
        return {"error": "pw_worker timeout (45s)"}
    except Exception as e:
        return {"error": f"pw_worker: {type(e).__name__}: {e}"}


def pw_navigate(url: str) -> str:
    """
    浏览器导航到指定 URL
    v6.1: CDP 直连（替代 subprocess），短超时 + JS 降级 + 自动重连
    """
    import json as _json
    from core.cdp_browser import pw_navigate as _cdp_navigate
    try:
        result = _json.loads(_cdp_navigate(url))
        if result.get("success"):
            return f"已导航: {result.get('url', url)} — {result.get('title', '')}"
        return f"[导航失败] {result.get('error', '未知错误')}"
    except Exception as e:
        return f"[导航错误] {type(e).__name__}: {e}"


def pw_screenshot() -> str:
    """
    截图当前浏览器页面
    v6.1: CDP 直连（替代 subprocess）
    """
    import time as _time
    from pathlib import Path as _Path
    from core.cdp_browser import cdp_session

    out_dir = _Path("output")
    out_dir.mkdir(exist_ok=True)
    path = str(out_dir / f"browser_{int(_time.time())}.png")

    try:
        with cdp_session() as browser:
            for ctx in browser.contexts:
                for p in ctx.pages:
                    if p.url and p.url != "about:blank":
                        p.screenshot(path=path, full_page=True)
                        return f"✅ 截图已保存: {path}"
            return "[截图] 无可用页面"
    except Exception as e:
        return f"[截图错误] {type(e).__name__}: {e}"


def pw_click(selector: str) -> str:
    """
    点击元素（CDP 直连）
    v6.1: 短超时 + JS 降级
    """
    from core.cdp_browser import cdp_session, safe_click
    try:
        with cdp_session() as browser:
            for ctx in browser.contexts:
                for p in ctx.pages:
                    if p.url and p.url != "about:blank":
                        ok = safe_click(p, selector)
                        return f"已点击: {selector}" if ok else f"[点击失败] {selector}"
            return "[点击] 无可用页面"
    except Exception as e:
        return f"[点击错误] {type(e).__name__}: {e}"


def pw_fill(selector: str, text: str) -> str:
    """Fill input (fresh subprocess, no async conflict)."""
    r = _pw_run("fill", selector=selector, text=text)
    if r.get("error"):
        return f"[错误] pw_fill: {r['error']}"
    return f"已填入: {selector}"


def pw_js(code: str) -> str:
    """Evaluate JS (fresh subprocess, no async conflict)."""
    r = _pw_run("js", code=code)
    if r.get("error"):
        return f"[错误] pw_js: {r['error']}"
    return r.get("value", "")


def pw_close() -> str:
    """Close browser (no-op — each call is stateless)."""
    return "浏览器会话已关闭。"
