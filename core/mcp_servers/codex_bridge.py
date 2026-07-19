"""Codex Bridge MCP Server — CRUX <-> Codex CLI bridge.

Wraps Codex CLI (codex.exe) as an MCP stdio server,
enabling kimi-code to discover and route tasks to Codex.

Usage (TRM auto-discovery):
    BRIDGES = {
        "codex": {
            "script": "core/mcp_servers/codex_bridge.py",
        },
    }
"""

import json
import os
import shutil
import subprocess
import sys

# ── Constants ───────────────────────────────────────────────────
CODEX_BIN = os.path.expanduser(r"~\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe")


def _find_codex() -> str | None:
    candidates = [
        CODEX_BIN,
        shutil.which("codex"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


class CodexMCPBridge:
    """MCP server bridging Codex CLI tools."""

    def __init__(self):
        self._tools_cache: list[dict] | None = None

    @property
    def tools(self) -> list[dict]:
        if self._tools_cache is not None:
            return self._tools_cache

        tools = [
            {
                "name": "codex_exec",
                "description": "Execute a coding task using Codex CLI. For file editing, TDD, git operations, and code generation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Task description for Codex"},
                        "work_dir": {"type": "string", "description": "Working directory (default: current dir)"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "codex_status",
                "description": "Check Codex CLI status: installed, version, binary path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "codex_handoff",
                "description": "Accept a handoff task from another agent. Follows the multi-agent handoff protocol.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Unique task identifier"},
                        "task": {"type": "string", "description": "Task description to hand off"},
                        "work_dir": {"type": "string", "description": "Working directory for the task"},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "Task priority (default: normal)",
                        },
                    },
                    "required": ["task_id", "task"],
                },
            },
        ]

        self._tools_cache = tools
        return tools

    # ── Tool methods ────────────────────────────────────────────

    def _run_codex(self, args: list, timeout: int = 300, work_dir: str = ".") -> dict:
        binary = _find_codex()
        if not binary:
            return {"success": False, "error": "Codex CLI not found"}

        cmd = [binary, *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=work_dir or os.getcwd(),
                encoding="utf-8",
                errors="replace",
            )
            return {
                "success": True,
                "output": result.stdout or "",
                "stderr": result.stderr or "",
                "return_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timeout after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def codex_exec(self, prompt: str, work_dir: str = ".", timeout: int = 300) -> dict:
        return self._run_codex(["exec", prompt], timeout, work_dir)

    def codex_status(self) -> dict:
        binary = _find_codex()
        if not binary:
            return {"success": False, "installed": False}

        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "success": True,
                "installed": True,
                "version": (result.stdout or result.stderr or "").strip(),
                "binary": binary,
            }
        except Exception as e:
            return {"success": False, "installed": True, "error": str(e), "binary": binary}

    def codex_handoff(self, task_id: str, task: str, work_dir: str = ".", priority: str = "normal") -> dict:
        handoff_dir = os.path.expanduser(r"~\.codex\handoff")
        os.makedirs(handoff_dir, exist_ok=True)
        handoff_file = os.path.join(handoff_dir, f"{task_id}.yaml")

        content = (
            f"---\n"
            f"from: kimi\n"
            f"to: codex\n"
            f"task_id: {task_id}\n"
            f"status: pending\n"
            f"priority: {priority}\n"
            f"---\n"
            f"### 任务\n"
            f"{task}\n"
            f"### 上下文\n"
            f"work_dir: {work_dir}\n"
            f"### 约束\n"
            f"- 最小变更原则\n"
            f"### 验证标准\n"
            f"- 由 Codex 自行验证\n"
        )

        try:
            with open(handoff_file, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "handoff_file": handoff_file,
                "task_id": task_id,
                "message": f"Handoff task {task_id} written. Codex will pick it up on next scan.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── JSON-RPC helpers ────────────────────────────────────────

    def _make_response(self, req_id: int | str | None, result: dict | None = None, error: dict | None = None) -> dict:
        resp = {"jsonrpc": "2.0"}
        if req_id is not None:
            resp["id"] = req_id
        if error:
            resp["error"] = error
        else:
            resp["result"] = result or {}
        return resp

    def _make_error(self, req_id: int | str | None, code: int, message: str) -> dict:
        return self._make_response(req_id, error={"code": code, "message": message})

    def _dispatch(self, req_id: int | str | None, method: str, params: dict) -> dict:
        if method == "initialize":
            return self._make_response(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "codex-bridge", "version": "1.0.0"},
                    "capabilities": {"tools": {}},
                },
            )

        if method == "tools/list":
            return self._make_response(req_id, {"tools": self.tools})

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})

            dispatch_map = {
                "codex_exec": lambda: self.codex_exec(
                    arguments.get("prompt", ""),
                    arguments.get("work_dir", "."),
                    arguments.get("timeout", 300),
                ),
                "codex_status": lambda: self.codex_status(),
                "codex_handoff": lambda: self.codex_handoff(
                    arguments.get("task_id", ""),
                    arguments.get("task", ""),
                    arguments.get("work_dir", "."),
                    arguments.get("priority", "normal"),
                ),
            }

            if name in dispatch_map:
                try:
                    result = dispatch_map[name]()
                    return self._make_response(req_id, result)
                except Exception as e:
                    return self._make_error(req_id, -32603, f"Tool error: {e!s}")
            return self._make_error(req_id, -32601, f"Tool not found: {name}")

        if method == "ping":
            return self._make_response(req_id, {})

        return self._make_error(req_id, -32601, f"Method not found: {method}")

    def run(self):
        """Main loop: read JSON-RPC requests line by line, route and respond."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self._send(self._make_error(None, -32700, "Parse error"))
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


def run_codex_bridge():
    """Entry point: start Codex Bridge MCP Server."""
    server = CodexMCPBridge()
    server.run()


if __name__ == "__main__":
    run_codex_bridge()
