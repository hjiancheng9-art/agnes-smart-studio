"""Kimi MCP Bridge — CRUX <-> Kimi CLI bridge.

Wraps Kimi CLI as an MCP stdio server, enabling CRUX to:
- kimi_exec    — Delegate task execution to Kimi
- kimi_review  — Delegate code review to Kimi
- kimi_status  — Check Kimi CLI status
- kimi_login   — Refresh Kimi authentication

Usage:
    # From CRUX:
    mcp_call_tool("kimi-bridge", "kimi_exec", {"prompt": "..."})

    # From Kimi (if Kimi supported MCP):
    # kimi mcp add crux -- python core/mcp_servers/kimi_mcp_bridge.py
"""

import sys, os, asyncio, json
from typing import Any, Optional
from pathlib import Path

# ── Path fix: run as script → relative imports fail ──
_SCRIPT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))
from core.mcp_servers._mcp_utils import run_subprocess

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



class KimiMCPBridge:
    """MCP server that bridges Kimi CLI tools."""

    def __init__(self):
        self._tools_cache: Optional[list[dict]] = None

    @property
    def tools(self) -> list[dict]:
        """Register Kimi tools with MCP server."""
        if self._tools_cache is not None:
            return self._tools_cache

        tools = [
            {
                "name": "kimi_exec",
                "description": "Execute a task using Kimi CLI. Suitable for code generation, explanation, debugging, refactoring, and general coding tasks.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Task description for Kimi"
                        },
                        "work_dir": {
                            "type": "string",
                            "description": "Working directory (default: current dir)"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 180)"
                        }
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": "kimi_review",
                "description": "Code review via Kimi CLI.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "File/directory to review"
                        },
                        "work_dir": {
                            "type": "string",
                            "description": "Working directory"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 180)"
                        }
                    },
                    "required": ["target"]
                }
            },
            {
                "name": "kimi_status",
                "description": "Check Kimi CLI status: installed, logged in, version.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "kimi_login",
                "description": "Refresh Kimi authentication. Call this when API returns 401/403 (token expired).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 120)"
                        }
                    },
                    "required": []
                }
            }
        ]

        self._tools_cache = tools
        return tools

    async def kimi_exec(self, prompt: str, work_dir: str = ".", timeout: int = 180) -> dict:
        """Execute a task using Kimi CLI."""
        import subprocess
        import shlex

        cmd = ["kimi", "-c", prompt]
        if work_dir != ".":
            cmd.extend(["-c", prompt, "--work-dir", work_dir])

        try:
            result = run_subprocess(
                cmd,
                timeout=timeout,
                shell=True,
            )

            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Timed out after {timeout} seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def kimi_review(self, target: str, work_dir: str = ".", timeout: int = 180) -> dict:
        """Code review via Kimi CLI."""
        import subprocess

        cmd = ["kimi", "-c", f"Review this: {target}", "--work-dir", work_dir]

        try:
            result = run_subprocess(
                cmd,
                timeout=timeout,
                shell=True,
            )

            return {
                "success": True,
                "output": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Timed out after {timeout} seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def kimi_status(self) -> dict:
        """Check Kimi CLI status."""
        import subprocess

        try:
            # Check if kimi is installed
            result = run_subprocess(
                ["kimi", "--version"],
                timeout=10,
                shell=True,
            )

            version = result.stdout.strip() or "unknown"

            # Check if logged in
            login_result = run_subprocess(
                ["kimi", "provider", "list"],
                timeout=10,
                shell=True,
            )

            logged_in = "provider" in login_result.stdout.lower()

            return {
                "success": True,
                "installed": True,
                "version": version,
                "logged_in": logged_in
            }
        except FileNotFoundError:
            return {
                "success": False,
                "installed": False,
                "error": "Kimi CLI not found"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def kimi_login(self, timeout: int = 120) -> dict:
        """Refresh Kimi authentication."""
        import subprocess

        try:
            result = run_subprocess(
                ["kimi", "acp", "--login"],
                timeout=timeout,
                shell=True,
            )

            return {
                "success": True,
                "message": "Login flow started. Please follow the device-code instructions.",
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Login timed out"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


async def handle_request(request: dict) -> dict:
    """Handle a single MCP request."""
    method = request.get("method")
    params = request.get("params", {})
    id_ = request.get("id")

    bridge = KimiMCPBridge()

    try:
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "tools": bridge.tools
                }
            }

        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})

            if name == "kimi_exec":
                result = await bridge.kimi_exec(
                    prompt=arguments.get("prompt", ""),
                    work_dir=arguments.get("work_dir", "."),
                    timeout=arguments.get("timeout", 180)
                )
                return {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "result": result
                }

            elif name == "kimi_review":
                result = await bridge.kimi_review(
                    target=arguments.get("target", ""),
                    work_dir=arguments.get("work_dir", "."),
                    timeout=arguments.get("timeout", 180)
                )
                return {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "result": result
                }

            elif name == "kimi_status":
                result = await bridge.kimi_status()
                return {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "result": result
                }

            elif name == "kimi_login":
                result = await bridge.kimi_login(
                    timeout=arguments.get("timeout", 120)
                )
                return {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "result": result
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "error": {
                        "code": -32601,
                        "message": f"Tool not found: {name}"
                    }
                }

        else:
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": id_,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }


async def main():
    """Run the MCP server."""
    import sys
    import os

    # Add project root to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Read from stdin, write to stdout
    import sys
    import json

    async for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = await handle_request(request)

            # Add newline if not already present
            output = json.dumps(response)
            if not output.endswith('\n'):
                output += '\n'

            sys.stdout.write(output)
            sys.stdout.flush()

        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    asyncio.run(main())
