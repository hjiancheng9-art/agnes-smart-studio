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

from ._mcp_utils import run_subprocess
import sys
import os
import asyncio
import json
import subprocess
from typing import Optional

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

    async def qoder_exec(self, prompt: str, work_dir: str = ".", model: str = "", timeout: int = 180) -> dict:
        args = ["-c", prompt]
        if work_dir != ".":
            args.extend(["--work-dir", work_dir])
        if model:
            args.extend(["--model", model])
        return self._run_qoder(args, timeout, work_dir)

    async def qoder_review(self, target: str, focus: str = "all", work_dir: str = ".", timeout: int = 180) -> dict:
        prompt = f"Review this code: {target}"
        if focus != "all":
            prompt += f". Focus on {focus}."
        return self._run_qoder(["-c", prompt], timeout, work_dir)

    async def qoder_status(self) -> dict:
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

    async def qoder_plan(self, prompt: str, work_dir: str = ".", timeout: int = 180) -> dict:
        args = ["-c", f"Create a plan for: {prompt}"]
        if work_dir != ".":
            args.extend(["--work-dir", work_dir])
        return self._run_qoder(args, timeout, work_dir)

    async def qoder_search(self, query: str, work_dir: str = ".", timeout: int = 60) -> dict:
        return self._run_qoder(["-c", f"Search codebase for: {query}"], timeout, work_dir)


async def handle_request(request: dict) -> dict:
    method = request.get("method")
    params = request.get("params", {})
    id_ = request.get("id")

    bridge = QoderMCPBridge()

    try:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "qoder-bridge", "version": "1.0.0"},
                    "capabilities": {"tools": {}}
                }
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {"tools": bridge.tools}
            }

        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})

            dispatch = {
                "qoder_exec": lambda: bridge.qoder_exec(
                    arguments.get("prompt", ""),
                    arguments.get("work_dir", "."),
                    arguments.get("model", ""),
                    arguments.get("timeout", 180)
                ),
                "qoder_review": lambda: bridge.qoder_review(
                    arguments.get("target", ""),
                    arguments.get("focus", "all"),
                    arguments.get("work_dir", "."),
                    arguments.get("timeout", 180)
                ),
                "qoder_status": lambda: bridge.qoder_status(),
                "qoder_plan": lambda: bridge.qoder_plan(
                    arguments.get("prompt", ""),
                    arguments.get("work_dir", "."),
                    arguments.get("timeout", 180)
                ),
                "qoder_search": lambda: bridge.qoder_search(
                    arguments.get("query", ""),
                    arguments.get("work_dir", "."),
                    arguments.get("timeout", 60)
                ),
            }

            if name in dispatch:
                result = await dispatch[name]()
                return {"jsonrpc": "2.0", "id": id_, "result": result}
            else:
                return {
                    "jsonrpc": "2.0", "id": id_,
                    "error": {"code": -32601, "message": f"Tool not found: {name}"}
                }

        else:
            return {
                "jsonrpc": "2.0", "id": id_,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

    except Exception as e:
        return {
            "jsonrpc": "2.0", "id": id_,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }


async def main():
    """Run MCP server over stdio."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = await handle_request(request)
            output = json.dumps(response)
            if not output.endswith('\n'):
                output += '\n'
            sys.stdout.write(output)
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    asyncio.run(main())
