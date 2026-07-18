"""Aider AI → MCP Bridge

Wraps Aider CLI (aider) as an MCP stdio server.
Maps MCP tools/call → Aider CLI via `aider --message "..." --yes` subprocess → returns results.

Uses line-based JSON-RPC 2.0 over stdio.
Aider natively supports DeepSeek models via LiteLLM.
API key from DEEPSEEK_API_KEY or OPENAI_API_KEY env var.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── ANSI cleanup ───────────────────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_OSC_RE = re.compile(r"\x1b\][0-9;]*[^\x1b]*\x1b\\")
_CTRL_RE = re.compile(r"[\x00-\x08\x0e-\x1f]")


def _clean_ansi(text: str) -> str:
    text = _ANSI_RE.sub("", text)
    text = _OSC_RE.sub("", text)
    return _CTRL_RE.sub("", text)


# ── Aider binary resolution ─────────────────────────────────────────

_AIDER_BINARY: str | None = None
_AIDER_VERSION: str = "unknown"


def _resolve_aider() -> str | None:
    global _AIDER_BINARY
    if _AIDER_BINARY is not None:
        return _AIDER_BINARY if _AIDER_BINARY else None
    candidates = [
        shutil.which("aider"),
        shutil.which("aider.exe"),
        str(Path(sys.executable).parent / "Scripts" / "aider.exe"),
        str(Path.home() / ".local" / "bin" / "aider"),
        str(Path.home() / ".local" / "bin" / "aider.exe"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            _AIDER_BINARY = os.path.realpath(p)
            return _AIDER_BINARY
    _AIDER_BINARY = shutil.which("aider") or ""
    return _AIDER_BINARY if _AIDER_BINARY else None


def _get_version() -> str:
    global _AIDER_VERSION
    if _AIDER_VERSION != "unknown":
        return _AIDER_VERSION
    binary = _resolve_aider()
    if not binary:
        return "unknown"
    try:
        r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
        _AIDER_VERSION = (r.stdout or r.stderr or "").strip()
    except Exception:
        _AIDER_VERSION = "unknown"
    return _AIDER_VERSION


# ── Aider execution via subprocess ───────────────────────────────────

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _run_aider(
    prompt: str,
    timeout: int = 600,
    model: str | None = None,
    target_file: str | None = None,
) -> dict:
    """Run Aider CLI with a prompt via subprocess (batch mode).

    Uses `aider --message "..." --yes --no-suggest-shell-commands` for
    non-interactive, approval-free execution.
    --yes skips all confirmation prompts.
    --no-suggest-shell-commands prevents aider from suggesting shell commands
    which would hang waiting for user input in a non-TTY context.
    """
    binary = _resolve_aider()
    if not binary:
        return {"success": False, "error": "Aider CLI not found"}

    cmd = [
        binary,
        "--message",
        prompt,
        "--yes",
        "--no-suggest-shell-commands",
    ]
    if model:
        cmd.extend(["--model", model])
    if target_file:
        cmd.append(target_file)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            cwd=PROJECT_ROOT,
        )
        output = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0 and not output.strip():
            return {
                "success": False,
                "error": f"Aider CLI failed (exit={proc.returncode}): {stderr[:500]}",
            }

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
        return {"success": False, "error": f"Aider timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_result(output: str, prompt: str) -> dict:
    """Extract meaningful summary and code from Aider CLI output.

    Aider emits ANSI-styled output. After ANSI cleanup, the first
    substantive line is used as summary, and the first fenced code block
    is extracted as the code segment.
    """
    summary = ""
    code = ""
    lines = [line.strip() for line in output.split("\n")]
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
        "name": "aider_status",
        "description": "Check Aider CLI availability, version, and binary path.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "aider_exec",
        "description": "Execute a coding task using Aider AI coding assistant. Uses aider --message for non-interactive batch mode with git-tracked edits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task description for Aider"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 600)"},
                "model": {
                    "type": "string",
                    "description": "Model to use, e.g. deepseek/deepseek-chat. Uses env DEEPSEEK_API_KEY.",
                },
                "target_file": {"type": "string", "description": "Optional target file path to edit."},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "aider_review",
        "description": "Review code using Aider AI coding assistant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "File path, directory, or code to review"},
                "focus": {
                    "type": "string",
                    "enum": ["all", "bugs", "security", "style", "performance"],
                    "description": "Review focus (default: all)",
                },
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 600)"},
                "model": {"type": "string", "description": "Model to use."},
            },
            "required": ["target"],
        },
    },
]


def _handle_tool_call(name: str, args: dict) -> dict:
    try:
        if name == "aider_status":
            binary = _resolve_aider()
            version = _get_version()
            try:
                if binary:
                    r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
                    live = r.returncode == 0
                else:
                    live = False
            except Exception:
                live = False
            info = {
                "available": live,
                "binary": binary,
                "version": version,
                "exists_on_disk": os.path.isfile(binary)
                if binary and os.path.isabs(binary)
                else bool(binary and shutil.which(binary)),
            }
            return {"content": [{"type": "text", "text": json.dumps(info, indent=2, ensure_ascii=False)}]}

        if name == "aider_exec":
            prompt = args.get("prompt", "")
            timeout = args.get("timeout", 600)
            model = args.get("model")
            target_file = args.get("target_file")
            result = _run_aider(prompt, timeout, model=model, target_file=target_file)
            if result.get("success"):
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": result["output"],
                        }
                    ]
                }
            return {
                "content": [{"type": "text", "text": f"Error: {result.get('error', 'unknown')}"}],
                "isError": True,
            }

        if name == "aider_review":
            target = args.get("target", "")
            focus = args.get("focus", "all")
            timeout = args.get("timeout", 600)
            model = args.get("model")

            review_prompt = f"Please review the following code for {focus} issues. Provide specific, actionable feedback:\n\n{target}"
            result = _run_aider(
                review_prompt, timeout, model=model, target_file=target if target and focus != "all" else None
            )
            if result.get("success"):
                return {"content": [{"type": "text", "text": result["output"]}]}
            return {
                "content": [{"type": "text", "text": f"Review error: {result.get('error', 'unknown')}"}],
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
    binary = _resolve_aider()
    version = _get_version()
    print(f"[aider_bridge] binary={binary}", file=sys.stderr, flush=True)
    print(f"[aider_bridge] version={version}", file=sys.stderr, flush=True)

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
                        "serverInfo": {"name": "aider-bridge", "version": "0.1.0"},
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

    print("[aider_bridge] shutting down", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
