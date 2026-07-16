"""Qoder CLI → MCP Bridge

Wraps Qoder CLI (qodercli npm package) as an MCP stdio server.
Maps MCP tools/call → Qoder CLI → returns results.

Tools:
    - qoder_exec    Execute a coding task using Qoder
    - qoder_review  Review code using Qoder
    - qoder_plan    Generate an execution plan using Qoder
    - qoder_search  Search code / docs using Qoder
    - qoder_status  Check Qoder CLI availability and version
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Qoder CLI binary (global npm install)
# 默认使用 DeepSeek V4 Pro
DEFAULT_MODEL = os.environ.get("QODER_MODEL", "lite")
QODER_EXE = "qodercli"  # rely on PATH


def _find_qoder() -> str | None:
    """Find qodercli binary; return path or None."""
    import shutil

    binary = shutil.which(QODER_EXE)
    if binary:
        return binary
    # Try common npm global locations on Windows
    for candidate in [
        Path.home() / "AppData" / "Roaming" / "npm" / "qodercli.cmd",
        Path.home() / "AppData" / "Roaming" / "npm" / "qodercli",
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def _run_qoder(args: list[str], timeout: int = 300, work_dir: str | None = None) -> dict:  # pyright: ignore[reportArgumentType]
    """Run qodercli with given args and return structured result."""
    binary = _find_qoder()
    if not binary:
        return {"success": False, "error": "Qoder CLI (qodercli) not found. Install via: npm install -g qodercli"}
    cmd = [binary, "--model", DEFAULT_MODEL, *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=work_dir or os.getcwd(),
        )
        return {
            "success": proc.returncode == 0,
            "output": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "return_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Qoder command timed out after {timeout}s"}
    except FileNotFoundError:
        return {"success": False, "error": "Qoder CLI binary not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _read_request() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _send_response(response: dict):
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    # Windows stdout encoding safety
    try:
        sys.stdout.reconfigure(newline="\n", encoding="utf-8", write_through=True)  # type: ignore[attr-defined]
        sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    while True:
        req = _read_request()
        if req is None:
            break

        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params", {})

        # ── initialize ────────────────────────────────────────
        if method == "initialize":
            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "qoder-mcp-bridge", "version": "0.1.0"},
                    },
                }
            )

        # ── notifications/initialized ──────────────────────────
        elif method == "notifications/initialized":
            pass  # no response for notifications

        # ── tools/list ─────────────────────────────────────────
        elif method == "tools/list":
            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "qoder_exec",
                                "description": "Execute a coding task using Qoder CLI. Delegates to qodercli for code generation, debugging, and file manipulation.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "prompt": {"type": "string", "description": "Task description for Qoder"},
                                        "work_dir": {
                                            "type": "string",
                                            "description": "Working directory (default: current dir)",
                                        },
                                        "timeout": {
                                            "type": "integer",
                                            "description": "Timeout in seconds (default: 300)",
                                        },
                                    },
                                    "required": ["prompt"],
                                },
                            },
                            {
                                "name": "qoder_review",
                                "description": "Review code using Qoder CLI.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "target": {"type": "string", "description": "File path or directory to review"},
                                        "focus": {
                                            "type": "string",
                                            "enum": ["all", "bugs", "security", "style", "performance"],
                                            "description": "Review focus (default: all)",
                                        },
                                        "work_dir": {"type": "string", "description": "Working directory"},
                                        "timeout": {
                                            "type": "integer",
                                            "description": "Timeout in seconds (default: 300)",
                                        },
                                    },
                                    "required": ["target"],
                                },
                            },
                            {
                                "name": "qoder_plan",
                                "description": "Generate an execution plan using Qoder CLI. Breaks down complex tasks into actionable steps.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "prompt": {"type": "string", "description": "Task/goal to plan for"},
                                        "work_dir": {"type": "string", "description": "Working directory"},
                                        "timeout": {
                                            "type": "integer",
                                            "description": "Timeout in seconds (default: 300)",
                                        },
                                    },
                                    "required": ["prompt"],
                                },
                            },
                            {
                                "name": "qoder_search",
                                "description": "Search code or documentation using Qoder CLI semantic search.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string", "description": "Search query"},
                                        "work_dir": {"type": "string", "description": "Working directory"},
                                        "timeout": {
                                            "type": "integer",
                                            "description": "Timeout in seconds (default: 60)",
                                        },
                                    },
                                    "required": ["query"],
                                },
                            },
                            {
                                "name": "qoder_status",
                                "description": "Check Qoder CLI availability, version, and health.",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                        ]
                    },
                }
            )

        # ── tools/call ─────────────────────────────────────────
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})

            if tool_name == "qoder_status":
                binary = _find_qoder()
                if not binary:
                    _send_response(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps(
                                            {
                                                "status": "not_found",
                                                "installed": False,
                                                "error": "qodercli not in PATH. Install: npm install -g qodercli",
                                            }
                                        ),
                                    }
                                ]
                            },
                        }
                    )
                else:
                    try:
                        r = subprocess.run(
                            [binary, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            encoding="utf-8",
                            errors="replace",
                        )
                        version = (r.stdout or r.stderr).strip()
                        _send_response(
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": json.dumps(
                                                {
                                                    "status": "ok",
                                                    "installed": True,
                                                    "binary": binary,
                                                    "version": version,
                                                }
                                            ),
                                        }
                                    ]
                                },
                            }
                        )
                    except Exception as e:
                        _send_response(
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": json.dumps(
                                                {
                                                    "status": "error",
                                                    "installed": True,
                                                    "binary": binary,
                                                    "error": str(e),
                                                }
                                            ),
                                        }
                                    ]
                                },
                            }
                        )

            elif tool_name == "qoder_exec":
                prompt = args.get("prompt", "")
                work_dir = args.get("work_dir")
                timeout = args.get("timeout", 300)
                result = _run_qoder(["-p", prompt], timeout=timeout, work_dir=work_dir)
                text = json.dumps(result, ensure_ascii=False)
                _send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}], "isError": not result.get("success")},
                    }
                )

            elif tool_name == "qoder_review":
                target = args.get("target", "")
                focus = args.get("focus", "all")
                work_dir = args.get("work_dir")
                timeout = args.get("timeout", 300)
                cmd_args = ["review"]
                if focus != "all":
                    cmd_args.extend(["--focus", focus])
                cmd_args.append(target)
                result = _run_qoder(cmd_args, timeout=timeout, work_dir=work_dir)
                text = json.dumps(result, ensure_ascii=False)
                _send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}], "isError": not result.get("success")},
                    }
                )

            elif tool_name == "qoder_plan":
                prompt = args.get("prompt", "")
                work_dir = args.get("work_dir")
                timeout = args.get("timeout", 300)
                result = _run_qoder(["plan", prompt], timeout=timeout, work_dir=work_dir)
                text = json.dumps(result, ensure_ascii=False)
                _send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}], "isError": not result.get("success")},
                    }
                )

            elif tool_name == "qoder_search":
                query = args.get("query", "")
                work_dir = args.get("work_dir")
                timeout = args.get("timeout", 60)
                result = _run_qoder(["search", query], timeout=timeout, work_dir=work_dir)
                text = json.dumps(result, ensure_ascii=False)
                _send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}], "isError": not result.get("success")},
                    }
                )

            else:
                _send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"})}],
                            "isError": True,
                        },
                    }
                )

        # ── unknown method ─────────────────────────────────────
        else:
            _send_response(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
            )


if __name__ == "__main__":
    main()
