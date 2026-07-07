"""Codex CLI → MCP Bridge

Wraps OpenAI Codex CLI (codex-cli) as an MCP stdio server.
Maps MCP tools/call → Codex CLI via `codex exec` subprocess → returns results.

Uses line-based JSON-RPC 2.0 over stdio.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ── ANSI cleanup ───────────────────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_OSC_RE = re.compile(r"\x1b\][0-9;]*[^\x1b]*\x1b\\")
_CTRL_RE = re.compile(r"[\x00-\x08\x0e-\x1f]")


def _clean_ansi(text: str) -> str:
    text = _ANSI_RE.sub("", text)
    text = _OSC_RE.sub("", text)
    text = _CTRL_RE.sub("", text)
    return text


# ── Codex binary resolution ─────────────────────────────────────────

_CODEX_BINARY: str | None = None
_CODEX_VERSION: str = "unknown"


def _resolve_codex() -> str:
    global _CODEX_BINARY
    if _CODEX_BINARY:
        return _CODEX_BINARY
    candidates = [
        shutil.which("codex"),
        shutil.which("codex.exe"),
        str(Path.home() / ".codex" / "packages" / "standalone" / "releases"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            _CODEX_BINARY = os.path.realpath(p)
            return _CODEX_BINARY
    codex_dir = Path.home() / ".codex" / "packages" / "standalone" / "releases"
    if codex_dir.is_dir():
        for release_dir in sorted(codex_dir.iterdir(), reverse=True):
            candidate = release_dir / "bin" / "codex.exe"
            if candidate.is_file():
                _CODEX_BINARY = str(candidate.resolve())
                return _CODEX_BINARY
    _CODEX_BINARY = shutil.which("codex") or "codex"
    return _CODEX_BINARY


def _get_version() -> str:
    global _CODEX_VERSION
    if _CODEX_VERSION != "unknown":
        return _CODEX_VERSION
    binary = _resolve_codex()
    try:
        r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
        _CODEX_VERSION = (r.stdout or r.stderr or "").strip()
    except Exception:
        _CODEX_VERSION = "unknown"
    return _CODEX_VERSION


# ── Codex execution via PTY ─────────────────────────────────────────

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _run_codex(prompt: str, timeout: int = 600) -> dict:
    """Run Codex CLI with a prompt via subprocess (codex exec).

    Uses `codex exec <prompt>` for non-interactive, approval-free execution.
    --dangerously-bypass-approvals-and-sandbox prevents the MCP server from
    hanging on interactive approval prompts (no TTY in stdio context).
    --ephemeral prevents session file accumulation on disk.
    -C ensures codex runs in the project root.
    """
    binary = _resolve_codex()
    if not binary:
        return {"success": False, "error": "Codex CLI not found"}

    try:
        proc = subprocess.run(
            [binary, "exec", prompt, "--dangerously-bypass-approvals-and-sandbox", "--ephemeral", "-C", PROJECT_ROOT],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0 and not output.strip():
            return {"success": False, "error": f"Codex CLI failed (exit={proc.returncode}): {stderr[:500]}"}

        output = _clean_ansi(output)
        result = _extract_result(output, prompt)

        return {
            "success": True,
            "output": output[:8000],
            "summary": result["summary"][:500] if result.get("summary") else "",
            "code": result.get("code", ""),
            "stderr": stderr[:500] if stderr else "",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Codex timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_result(output: str, prompt: str) -> dict:
    """Extract meaningful summary and code from Codex CLI output.

    Codex CLI emits ANSI-styled output. After ANSI cleanup, we extract
    the first substantive line as summary, and the first fenced code block
    as the code segment. Falls back gracefully on empty output.
    """
    summary = ""
    code = ""
    lines = [l.strip() for l in output.split("\n")]
    in_code = False
    code_lines = []

    for line in lines:
        if line.startswith("```"):
            if in_code and code_lines:
                code = "\n".join(code_lines).strip()
                in_code = False
            else:
                in_code = True
                code_lines = []
            continue

        if in_code:
            code_lines.append(line)
            continue

        # Skip noise lines before first substantive content
        if not summary and line and not line.startswith("[") and len(line) > 8:
            summary = line[:200]

    if not summary:
        if code:
            lines_count = len(code.split("\n"))
            summary = f"Generated {lines_count} lines of code"
        elif output.strip():
            summary = output.strip()[:200]
        else:
            summary = "(empty response)"

    return {"summary": summary, "code": code}


# ── MCP protocol (line-based JSON-RPC 2.0) ─────────────────────────


def _read_request() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line)


def _send_response(response: dict) -> None:
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ── Tool definitions ───────────────────────────────────────────────

TOOLS = [
    {
        "name": "codex_status",
        "description": "Check Codex CLI availability, version, and binary path.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "codex_exec",
        "description": "Execute a coding task using OpenAI Codex CLI. Write code, debug, refactor, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task description for Codex CLI"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "codex_review",
        "description": "Review code using OpenAI Codex CLI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "File path, directory, or code to review"},
                "focus": {
                    "type": "string",
                    "enum": ["all", "bugs", "security", "style", "performance"],
                    "description": "Review focus (default: all)",
                },
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "codex_think",
        "description": "Deep analysis using OpenAI Codex CLI. Architecture review, design proposals, complex reasoning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Analysis task description"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
            },
            "required": ["prompt"],
        },
    },
]


def _handle_tool_call(name: str, args: dict) -> dict:
    try:
        if name == "codex_status":
            binary = _resolve_codex()
            version = _get_version()
            # Verify the binary works by checking help output
            try:
                r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
                live = r.returncode == 0
            except Exception:
                live = False
            info = {
                "available": live,
                "binary": binary,
                "version": version,
                "exists_on_disk": os.path.isfile(binary) if os.path.isabs(binary) else bool(shutil.which(binary)),
            }
            return {"content": [{"type": "text", "text": json.dumps(info, indent=2, ensure_ascii=False)}]}

        if name == "codex_exec":
            prompt = args.get("prompt", "")
            timeout = args.get("timeout", 300)
            result = _run_codex(prompt, timeout)
            if result.get("success"):
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": result["output"],
                        }
                    ]
                }
            else:
                return {
                    "content": [{"type": "text", "text": f"Error: {result.get('error', 'unknown')}"}],
                    "isError": True,
                }

        if name == "codex_review":
            target = args.get("target", "")
            timeout = args.get("timeout", 600)
            binary = _resolve_codex()
            review_args = ["--dangerously-bypass-approvals-and-sandbox", "--ephemeral", "-C", PROJECT_ROOT]
            try:
                proc = subprocess.run(
                    [binary, "exec", "review", target] + review_args,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
                output = _clean_ansi(proc.stdout or "")
                if proc.returncode != 0 and not output.strip():
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Review failed (exit={proc.returncode}): {_clean_ansi(proc.stderr or '')[:500]}",
                            }
                        ],
                        "isError": True,
                    }
                return {"content": [{"type": "text", "text": output[:8000]}]}
            except subprocess.TimeoutExpired:
                return {
                    "content": [{"type": "text", "text": f"Codex review timed out after {timeout}s"}],
                    "isError": True,
                }
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Codex review error: {e}"}], "isError": True}

        if name == "codex_think":
            prompt = args.get("prompt", "")
            timeout = args.get("timeout", 300)
            result = _run_codex(f"Think deeply and analyze: {prompt}", timeout)
            if result.get("success"):
                return {"content": [{"type": "text", "text": result["output"]}]}
            else:
                return {
                    "content": [{"type": "text", "text": f"Error: {result.get('error', 'unknown')}"}],
                    "isError": True,
                }

        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }

    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error: {e}"}],
            "isError": True,
        }


# ── Main loop ──────────────────────────────────────────────────────


def main():
    binary = _resolve_codex()
    version = _get_version()
    print(f"[codex_bridge] Codex binary: {binary}", file=sys.stderr, flush=True)
    print(f"[codex_bridge] Codex version: {version}", file=sys.stderr, flush=True)

    while True:
        try:
            req = _read_request()
        except json.JSONDecodeError:
            continue
        if req is None:
            break

        msg_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "initialize":
            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "codex-bridge", "version": "0.1.0"},
                    },
                }
            )

        elif method == "notifications/initialized":
            pass

        elif method == "tools/list":
            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"tools": TOOLS},
                }
            )

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = _handle_tool_call(tool_name, arguments)
            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": result,
                }
            )

        elif method == "ping":
            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {},
                }
            )

        else:
            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )

    print(f"[codex_bridge] shutting down", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
