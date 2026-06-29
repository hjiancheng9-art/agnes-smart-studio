"""Codex Bridge MCP Server — CRUX <-> OpenAI Codex CLI bridge.

Wraps the OpenAI Codex CLI as an MCP stdio server, enabling CRUX to:
- codex_exec    — Delegate non-interactive task execution
- codex_review  — Run comprehensive code review
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────

CODEX_BINARY = (
    shutil.which("codex")
    or os.path.expanduser(
        "~/AppData/Local/Programs/OpenAI/Codex/bin/codex.EXE"
    )
    or os.path.expanduser("~/.local/bin/codex")
)

CODEX_NOT_FOUND_MSG = (
    "Codex CLI not found. Install with: "
    "https://github.com/openai/codex"
)

JSONRPC_VERSION = "2.0"

# JSON-RPC error codes
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_EXEC_FAILED = -32001
ERR_TIMEOUT = -32002

# ── Tool Definitions ───────────────────────────────────────────

TOOL_DEFS = [
    {
        "name": "codex_exec",
        "description": (
            "Execute a prompt with OpenAI Codex CLI non-interactively. "
            "Suitable for code generation, explanation, debugging, "
            "refactoring, and general coding tasks. "
            "Returns the Codex output with file diffs if any."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt / task for Codex to execute",
                },
                "work_dir": {
                    "type": "string",
                    "description": "Working directory for the execution (default: current dir)",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Model override, e.g. 'gpt-5-codex' or 'o4-mini'. "
                        "Leave empty for Codex default."
                    ),
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of tool names Codex is allowed to use. "
                        "Example: ['Read', 'Write', 'Bash', 'Grep', 'Glob']. "
                        "Omit to use Codex defaults."
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 180, max: 600)",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "codex_review",
        "description": (
            "Run a non-interactive code review using Codex CLI. "
            "Best for reviewing staged changes or specific files "
            "with Codex's deep code understanding capabilities."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "File path, directory, or 'staged' to review "
                        "git staged changes. Use '.' for entire working tree."
                    ),
                },
                "focus": {
                    "type": "string",
                    "enum": ["bugs", "security", "performance", "style", "all"],
                    "description": "Review focus area (default: all)",
                },
                "work_dir": {
                    "type": "string",
                    "description": "Working directory (default: current dir)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 180, max: 600)",
                },
            },
            "required": ["target"],
        },
    },
]


# ── JSON-RPC Helpers ───────────────────────────────────────────

def _make_jsonrpc_response(id_val, result=None, error=None):
    resp = {"jsonrpc": JSONRPC_VERSION, "id": id_val}
    if error is not None:
        resp["error"] = error
    else:
        resp["result"] = result
    return resp


def _make_jsonrpc_error(id_val, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return _make_jsonrpc_response(id_val, error=error)


# ── Codex Helpers ──────────────────────────────────────────────

def _find_codex() -> str or None:
    """Locate the Codex CLI binary."""
    if os.path.isfile(CODEX_BINARY):
        return CODEX_BINARY
    found = shutil.which("codex")
    return found


def _check_codex_status() -> dict:
    """Check Codex CLI availability and auth status."""
    codex_path = _find_codex()
    if not codex_path:
        return {
            "available": False,
            "binary": None,
            "auth": "unknown",
            "message": CODEX_NOT_FOUND_MSG,
        }

    # Check if authenticated
    auth_ok = False
    try:
        r = subprocess.run(
            [codex_path, "login", "--status"],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "NO_COLOR": "1"},
        )
        auth_ok = r.returncode == 0 and "logged in" in (r.stdout + r.stderr).lower()
    except Exception:
        pass

    # If login --status fails, check if auth file exists
    if not auth_ok:
        auth_file = os.path.expanduser("~/.codex/.cockpit_codex_auth.json")
        auth_ok = os.path.isfile(auth_file)

    return {
        "available": True,
        "binary": codex_path,
        "auth": "ok" if auth_ok else "unauthenticated",
        "message": "Ready" if auth_ok else "Run `codex login` to authenticate",
    }


def _run_codex_exec(
    prompt: str,
    *,
    work_dir: str or None = None,
    model: str or None = None,
    allowed_tools: list[str] or None = None,
    timeout: int = 180,
) -> dict:
    """Execute a prompt via Codex CLI."""

    codex_path = _find_codex()
    if not codex_path:
        return {
            "success": False,
            "error": CODEX_NOT_FOUND_MSG,
            "output": "",
            "stderr": "",
        }

    # Use "exec review" subcommand instead of plain "exec" because
    # Codex CLI's sandbox requires a real TTY for plain "exec",
    # but "exec review" works with captured stdout.
    cmd = [codex_path, "exec", "review"]

    if model:
        cmd.extend(["--model", model])

    if work_dir:
        cmd.extend(["-C", work_dir])

    cmd.append(prompt)

    timeout = min(timeout, 600)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir or os.getcwd(),
            env={**os.environ, "NO_COLOR": "1"},
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout[:50000],
            "stderr": result.stderr[:10000] if result.stderr else "",
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Timed out after {timeout}s",
            "output": "",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": "",
            "stderr": "",
        }


def _run_codex_review(
    target: str,
    *,
    focus: str = "all",
    work_dir: str or None = None,
    timeout: int = 180,
) -> dict:
    """Run a code review via Codex CLI."""

    codex_path = _find_codex()
    if not codex_path:
        return {
            "success": False,
            "error": CODEX_NOT_FOUND_MSG,
            "output": "",
            "stderr": "",
        }

    cmd = [codex_path, "exec", "review"]

    review_prompt = f"Review: {target}"
    if focus and focus != "all":
        review_prompt += f" (focus on {focus})"

    if work_dir:
        cmd.extend(["-C", work_dir])

    cmd.append(review_prompt)

    timeout = min(timeout, 600)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir or os.getcwd(),
            env={**os.environ, "NO_COLOR": "1"},
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout[:50000],
            "stderr": result.stderr[:10000] if result.stderr else "",
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Timed out after {timeout}s",
            "output": "",
            "stderr": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": "",
            "stderr": "",
        }


# ── MCP Server ─────────────────────────────────────────────────

class CodexBridgeServer:
    """Codex Bridge MCP Server via stdio JSON-RPC 2.0."""

    def __init__(self):
        self._initialized = False
        try:
            self._status = _check_codex_status()
            self._initialized = True
        except Exception as e:
            self._status = {
                "available": False,
                "binary": None,
                "auth": "error",
                "message": str(e),
            }
            self._initialized = False

    # ── IO ──────────────────────────────────────────────────

    def _send(self, response: dict):
        """Send a JSON-RPC response to stdout."""
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    # ── Dispatch ────────────────────────────────────────────

    def _dispatch(self, method: str, req_id, params=None) -> dict:
        """Route JSON-RPC methods to handlers."""
        try:
            if method == "tools/list":
                return self._handle_tools_list(req_id, params)
            elif method == "tools/call":
                return self._handle_tools_call(req_id, params)
            elif method == "initialize":
                return self._handle_initialize(req_id, params)
            elif method == "ping":
                return _make_jsonrpc_response(req_id, result={"pong": True})
            else:
                return _make_jsonrpc_error(
                    req_id, ERR_METHOD_NOT_FOUND,
                    f"Unknown method: {method}"
                )
        except Exception as e:
            return _make_jsonrpc_error(req_id, ERR_INTERNAL, str(e))

    # ── Initialize ──────────────────────────────────────────

    def _handle_initialize(self, req_id, params=None) -> dict:
        return _make_jsonrpc_response(req_id, result={
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "codex-bridge",
                "version": "1.0.0",
            },
            "capabilities": {
                "tools": {},
            },
        })

    # ── Tools List ──────────────────────────────────────────

    def _handle_tools_list(self, req_id, params=None) -> dict:
        status = _check_codex_status()
        tools = []
        for t in TOOL_DEFS:
            tool_copy = dict(t)
            tools.append(tool_copy)

        # Add status info to first tool's description if codex is unavailable
        if not status["available"]:
            tools[0]["description"] += f" [WARNING: {status['message']}]"

        return _make_jsonrpc_response(req_id, result={"tools": tools})

    # ── Tools Call ──────────────────────────────────────────

    def _handle_tools_call(self, req_id, params=None) -> dict:
        if not params or "name" not in params:
            return _make_jsonrpc_error(
                req_id, ERR_INVALID_PARAMS,
                "Missing 'name' in params"
            )

        tool_name = params["name"]
        args = params.get("arguments", {})

        if tool_name == "codex_exec":
            return self._call_codex_exec(req_id, args)
        elif tool_name == "codex_review":
            return self._call_codex_review(req_id, args)
        else:
            return _make_jsonrpc_error(
                req_id, ERR_METHOD_NOT_FOUND,
                f"Unknown tool: {tool_name}"
            )

    # ── Tool Handlers ───────────────────────────────────────

    def _call_codex_exec(self, req_id, args: dict) -> dict:
        prompt = args.get("prompt", "")
        if not prompt:
            return _make_jsonrpc_error(
                req_id, ERR_INVALID_PARAMS,
                "Missing required parameter: 'prompt'"
            )

        start = time.time()
        result = _run_codex_exec(
            prompt,
            work_dir=args.get("work_dir"),
            model=args.get("model"),
            allowed_tools=args.get("allowed_tools"),
            timeout=args.get("timeout", 180),
        )
        elapsed = round(time.time() - start, 2)

        output_lines = []
        if result.get("error"):
            output_lines.append(f"[ERROR] {result['error']}")
        if result.get("output"):
            output_lines.append(result["output"])
        if result.get("stderr"):
            output_lines.append(f"[STDERR]\n{result['stderr']}")

        response_text = "\n".join(output_lines) or "(empty response)"

        return _make_jsonrpc_response(req_id, result={
            "content": [
                {
                    "type": "text",
                    "text": response_text,
                }
            ],
            "isError": not result["success"],
            "meta": {
                "success": result["success"],
                "exit_code": result.get("exit_code"),
                "elapsed_seconds": elapsed,
            },
        })

    def _call_codex_review(self, req_id, args: dict) -> dict:
        target = args.get("target", "")
        if not target:
            return _make_jsonrpc_error(
                req_id, ERR_INVALID_PARAMS,
                "Missing required parameter: 'target'"
            )

        start = time.time()
        result = _run_codex_review(
            target,
            focus=args.get("focus", "all"),
            work_dir=args.get("work_dir"),
            timeout=args.get("timeout", 180),
        )
        elapsed = round(time.time() - start, 2)

        output_lines = []
        if result.get("error"):
            output_lines.append(f"[ERROR] {result['error']}")
        if result.get("output"):
            output_lines.append(result["output"])
        if result.get("stderr"):
            output_lines.append(f"[STDERR]\n{result['stderr']}")

        response_text = "\n".join(output_lines) or "(empty review)"

        return _make_jsonrpc_response(req_id, result={
            "content": [
                {
                    "type": "text",
                    "text": response_text,
                }
            ],
            "isError": not result["success"],
            "meta": {
                "success": result["success"],
                "exit_code": result.get("exit_code"),
                "elapsed_seconds": elapsed,
            },
        })

    # ── Run ─────────────────────────────────────────────────

    def run(self):
        """Main loop: read JSON-RPC from stdin, dispatch, reply to stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self._send(_make_jsonrpc_error(
                    None, ERR_PARSE, "Invalid JSON"
                ))
                continue

            req_id = req.get("id")
            method = req.get("method", "")
            params = req.get("params")

            # Skip notifications
            if method == "notifications/initialized":
                continue

            resp = self._dispatch(method, req_id, params)
            self._send(resp)


def run_codex_bridge():
    """Entry point: launch Codex Bridge MCP Server."""
    server = CodexBridgeServer()
    server.run()


if __name__ == "__main__":
    run_codex_bridge()
