"""Claude Code Bridge MCP Server — CRUX <-> Claude Code CLI bridge.

Wraps Claude Code CLI (claude.exe mcp serve) as an MCP stdio server,
enabling CRUX to discover and route to Claude Code's tools.

Usage (TRM auto-discovery):
    BRIDGES = {
        "claude-code": {
            "script": "core/mcp_servers/claude_code_bridge.py",
        },
    }
"""

import sys, os, json, subprocess
from pathlib import Path
from typing import Optional

# ── Constants ───────────────────────────────────────────────────
CLAUDE_CODE_PATH = os.path.expanduser(r"~\.local\bin\claude.exe")
PYTHON = sys.executable


class ClaudeCodeMCPBridge:
    """MCP server bridging Claude Code CLI tools."""

    def __init__(self):
        self._tools_cache: Optional[list[dict]] = None

    @property
    def tools(self) -> list[dict]:
        if self._tools_cache is not None:
            return self._tools_cache

        tools = [
            {
                "name": "claude_code_exec",
                "description": "Execute a coding task using Claude Code CLI. Delegates to claude.exe for code generation, debugging, refactoring, and file manipulation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Task description for Claude Code"},
                        "work_dir": {"type": "string", "description": "Working directory (default: current dir)"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "claude_code_review",
                "description": "Review code using Claude Code CLI. Delegates to claude.exe /review agent.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "File path, directory, or 'git diff'"},
                        "focus": {"type": "string", "enum": ["all", "bugs", "security", "style", "performance"], "description": "Review focus (default: all)"},
                        "work_dir": {"type": "string", "description": "Working directory"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
                    },
                    "required": ["target"],
                },
            },
            {
                "name": "claude_code_think",
                "description": "Deep analysis using Claude Code CLI. For architecture review, design proposals, and complex reasoning.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Analysis task description"},
                        "work_dir": {"type": "string", "description": "Working directory"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "claude_code_status",
                "description": "Check Claude Code CLI status: installed, version, binary path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

        self._tools_cache = tools
        return tools

    # ── Tool methods ────────────────────────────────────────────

    def _run_claude(self, args: list, timeout: int = 300, work_dir: str = ".") -> dict:
        """Run claude.exe with given args."""
        cmd = [CLAUDE_CODE_PATH] + args

        # Check binary exists
        if not os.path.isfile(CLAUDE_CODE_PATH):
            return {"success": False, "error": f"Claude Code CLI not found at {CLAUDE_CODE_PATH}"}

        try:
            from core.mcp_servers._mcp_utils import run_subprocess

            result = run_subprocess(cmd, timeout=timeout, cwd=work_dir or os.getcwd())
            return {
                "success": True,
                "output": result.get("output", ""),
                "stderr": result.get("stderr", ""),
                "return_code": result.get("return_code"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def claude_code_exec(self, prompt: str, work_dir: str = ".", timeout: int = 300) -> dict:
        return self._run_claude(["-p", prompt], timeout, work_dir)

    def claude_code_review(self, target: str, focus: str = "all", work_dir: str = ".", timeout: int = 300) -> dict:
        args = ["review"] if focus == "all" else ["review", "--focus", focus]
        if target:
            args.append(target)
        return self._run_claude(args, timeout, work_dir)

    def claude_code_think(self, prompt: str, work_dir: str = ".", timeout: int = 300) -> dict:
        return self._run_claude(["-p", f"Think deeply: {prompt}"], timeout, work_dir)

    def claude_code_status(self) -> dict:
        """Check Claude Code CLI status."""
        if not os.path.isfile(CLAUDE_CODE_PATH):
            return {"success": False, "installed": False, "binary": CLAUDE_CODE_PATH}

        try:
            result = subprocess.run([CLAUDE_CODE_PATH, "--version"], capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
            return {
                "success": True,
                "installed": True,
                "version": result.stdout.strip(),
                "binary": CLAUDE_CODE_PATH,
            }
        except Exception as e:
            return {"success": False, "installed": True, "error": str(e), "binary": CLAUDE_CODE_PATH}

    # ── JSON-RPC helpers ────────────────────────────────────────

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
                "serverInfo": {"name": "claude-code-bridge", "version": "1.0.0"},
                "capabilities": {"tools": {}}
            })

        if method == "tools/list":
            return self._make_jsonrpc_response(req_id, {"tools": self.tools})

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})

            dispatch = {
                "claude_code_exec": lambda: self.claude_code_exec(
                    arguments.get("prompt", ""),
                    arguments.get("work_dir", "."),
                    arguments.get("timeout", 300),
                ),
                "claude_code_review": lambda: self.claude_code_review(
                    arguments.get("target", ""),
                    arguments.get("focus", "all"),
                    arguments.get("work_dir", "."),
                    arguments.get("timeout", 300),
                ),
                "claude_code_think": lambda: self.claude_code_think(
                    arguments.get("prompt", ""),
                    arguments.get("work_dir", "."),
                    arguments.get("timeout", 300),
                ),
                "claude_code_status": lambda: self.claude_code_status(),
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
        if not output.endswith("\n"):
            output += "\n"
        sys.stdout.write(output)
        sys.stdout.flush()


def run_claude_code_bridge():
    """入口：启动 Claude Code Bridge MCP Server。"""
    server = ClaudeCodeMCPBridge()
    server.run()


if __name__ == "__main__":
    run_claude_code_bridge()
