"""Qoder Bridge MCP Server — CRUX <-> Qoder CLI bridge.

Wraps Qoder CLI as an MCP stdio server, enabling CRUX to:
- qoder_exec    — Delegate task execution to Qoder
- qoder_review  — Delegate code review to Qoder
- qoder_status  — Check Qoder CLI status
- qoder_plan    — Generate execution plan via Qoder
- qoder_search  — Search codebase with Qoder

Usage:
    From CRUX:
    mcp_call_tool("qoder-bridge", "qoder_exec", {"prompt": "..."})
"""

import sys, os, json, subprocess
from typing import Optional
from pathlib import Path

# ── Path fix: run as script → relative imports fail ──
_SCRIPT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))
from core.mcp_servers._mcp_utils import run_subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QODER_PATH = os.path.expanduser(r"~\.qoder\bin\qodercli\qodercli.exe")


class QoderMCPBridge:
    """MCP server bridging Qoder CLI tools."""

    def __init__(self):
        self._tools_cache: Optional[list[dict]] = None

    @property
    def tools(self) -> list[dict]:
        if self._tools_cache is not None:
            return self._tools_cache

        tools = [
            {
                "name": "qoder_exec",
                "description": "Execute a task using Qoder CLI. Supports code generation, explanation, debugging, refactoring, and general coding tasks.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Task description for Qoder"},
                        "work_dir": {"type": "string", "description": "Working directory (default: current dir)"},
                        "model": {"type": "string", "description": "Model override"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 180)"}
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": "qoder_review",
                "description": "Code review via Qoder CLI.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "File/directory to review"},
                        "focus": {"type": "string", "enum": ["bugs", "security", "performance", "style", "all"], "description": "Review focus (default: all)"},
                        "work_dir": {"type": "string", "description": "Working directory"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 180)"}
                    },
                    "required": ["target"]
                }
            },
            {
                "name": "qoder_status",
                "description": "Check Qoder CLI status: installed, version, auth status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "qoder_plan",
                "description": "Generate an execution plan using Qoder CLI.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The goal/task to plan"},
                        "work_dir": {"type": "string", "description": "Working directory (default: current dir)"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 180)"}
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": "qoder_search",
                "description": "Search codebase using Qoder CLI.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "work_dir": {"type": "string", "description": "Working directory (default: current dir)"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)"}
                    },
                    "required": ["query"]
                }
            }
        ]

        self._tools_cache = tools
        return tools

    def _run_qoder(self, args: list, timeout: int = 180, work_dir: str = ".") -> dict:
        """Run qodercli with given args."""
        cmd = [QODER_PATH, "--print"] + args

        try:
            cwd = os.path.abspath(work_dir) if work_dir != "." else os.getcwd()
            result = run_subprocess(
                cmd,
                timeout=timeout,
                cwd=cwd
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timed out after {timeout}s"}
        except FileNotFoundError:
            return {"success": False, "error": f"Qoder CLI not found at {QODER_PATH}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def qoder_exec(self, prompt: str, work_dir: str = ".", model: str = "", timeout: int = 180) -> dict:
        args = ["-c", prompt]
        if work_dir != ".":
            args.extend(["--work-dir", work_dir])
        if model:
            args.extend(["--model", model])
        return self._run_qoder(args, timeout, work_dir)

    def qoder_review(self, target: str, focus: str = "all", work_dir: str = ".", timeout: int = 180) -> dict:
        prompt = f"Review this code: {target}"
        if focus != "all":
            prompt += f". Focus on {focus}."
        return self._run_qoder(["-c", prompt], timeout, work_dir)

    def qoder_status(self) -> dict:
        try:
            result = run_subprocess([QODER_PATH, "--version"], timeout=10)
            version = result.stdout.strip()
            return {
                "success": True,
                "installed": True,
                "version": version,
                "binary": QODER_PATH
            }
        except FileNotFoundError:
            return {"success": False, "installed": False, "error": "Qoder CLI not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def qoder_plan(self, prompt: str, work_dir: str = ".", timeout: int = 180) -> dict:
        args = ["-c", f"Create a plan for: {prompt}"]
        if work_dir != ".":
            args.extend(["--work-dir", work_dir])
        return self._run_qoder(args, timeout, work_dir)

    def qoder_search(self, query: str, work_dir: str = ".", timeout: int = 60) -> dict:
        return self._run_qoder(["-c", f"Search codebase for: {query}"], timeout, work_dir)

    def _make_jsonrpc_response(self, req_id: int | str | None, result: dict | None = None, error: dict | None = None) -> dict:
        resp = {"jsonrpc": "2.0"}
        if req_id is not None:
            resp["id"] = req_id
        if error:
            resp["error"] = error
        else:
            resp["result"] = result or {}
        return resp

    def _make_jsonrpc_error(self, req_id: int | str | None, code: int, message: str) -> dict:
        return self._make_jsonrpc_response(req_id, error={"code": code, "message": message})

    def _dispatch(self, req_id: int | str | None, method: str, params: dict) -> dict:
        if method == "initialize":
            return self._make_jsonrpc_response(req_id, {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "qoder-bridge", "version": "1.0.0"},
                "capabilities": {"tools": {}}
            })

        if method == "tools/list":
            return self._make_jsonrpc_response(req_id, {"tools": self.tools})

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})

            dispatch = {
                "qoder_exec": lambda: self.qoder_exec(
                    arguments.get("prompt", ""),
                    arguments.get("work_dir", "."),
                    arguments.get("model", ""),
                    arguments.get("timeout", 180)
                ),
                "qoder_review": lambda: self.qoder_review(
                    arguments.get("target", ""),
                    arguments.get("focus", "all"),
                    arguments.get("work_dir", "."),
                    arguments.get("timeout", 180)
                ),
                "qoder_search": lambda: self.qoder_search(
                    query=arguments.get("query", ""),
                    work_dir=arguments.get("work_dir", "."),
                    timeout=arguments.get("timeout", 60),
                ),
                "qoder_status": lambda: self.qoder_status(),
            }

            if name in dispatch:
                try:
                    result = dispatch[name]()
                    return self._make_jsonrpc_response(req_id, result)
                except Exception as e:
                    return self._make_jsonrpc_error(req_id, -32603, f"Tool error: {str(e)}")
            else:
                return self._make_jsonrpc_error(req_id, -32601, f"Tool not found: {name}")

        return self._make_jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    def run(self):
        """主循环：逐行读取 JSON-RPC 请求，路由并响应。"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self._send(self._make_jsonrpc_error(None, -32700, "Parse error"))
                continue

            req_id = req.get("id")
            method = req.get("method", "")
            params = req.get("params", {})

            if method == "notifications/initialized":
                continue

            resp = self._dispatch(req_id, method, params)
            self._send(resp)

    def _send(self, resp: dict):
        output = json.dumps(resp, ensure_ascii=False)
        if not output.endswith('\n'):
            output += '\n'
        sys.stdout.write(output)
        sys.stdout.flush()


def run_qoder_bridge():
    """入口：启动 Qoder Bridge MCP Server。"""
    server = QoderMCPBridge()
    server.run()


if __name__ == "__main__":
    run_qoder_bridge()
