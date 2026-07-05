"""Codex CLI → MCP Bridge

Wraps OpenAI Codex CLI (codex-cli) as an MCP stdio server.
Maps MCP tools/call → Codex CLI via pywinpty pseudo-terminal → returns results.

Uses line-based JSON-RPC 2.0 over stdio.

REQUIRES: pip install pywinpty (for pseudo-terminal on Windows)
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

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
_OSC_RE = re.compile(r'\x1b\][0-9;]*[^\x1b]*\x1b\\')
_CTRL_RE = re.compile(r'[\x00-\x08\x0e-\x1f]')


def _clean_ansi(text: str) -> str:
    text = _ANSI_RE.sub('', text)
    text = _OSC_RE.sub('', text)
    text = _CTRL_RE.sub('', text)
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

def _read_pty(proc) -> str:
    """Read all available data from PTY."""
    data = ""
    while True:
        try:
            chunk = proc.read()
            if not chunk:
                break
            data += chunk
        except EOFError:
            break
    return data


def _run_codex(prompt: str, timeout: int = 300) -> dict:
    """Run Codex CLI with a prompt via pywinpty pseudo-terminal.

    Codex requires a TTY. pywinpty creates one on Windows.
    """
    binary = _resolve_codex()

    try:
        from winpty import PtyProcess
    except ImportError:
        return {"exit_code": -10, "output": "pywinpty not installed. Run: pip install pywinpty"}

    proc = None
    try:
        proc = PtyProcess.spawn([binary], dimensions=(40, 200))
        start = time.time()

        # Phase 1: Wait for Codex to initialize (model loading)
        time.sleep(10)
        _read_pty(proc)  # drain init data

        # Phase 2: Send the prompt
        proc.write(prompt + '\n')

        # Phase 3: Read response with patience
        response = ""
        while time.time() - start < timeout:
            time.sleep(2)
            data = _read_pty(proc)
            if data:
                clean = _clean_ansi(data)
                response += clean

                # If prompt reappeared and we have enough output, stop
                if ('›' in data or '> ' in data) and len(response) > 100:
                    time.sleep(1)
                    try:
                        extra = _read_pty(proc)
                        if extra:
                            response += _clean_ansi(extra)
                    except Exception:
                        pass
                    break
            else:
                # No new data for 2 seconds - might be done
                if len(response) > 20:
                    # Wait one more cycle
                    continue
                break

        return {"exit_code": 0, "output": response.strip() or "(no output)"}

    except Exception as e:
        return {"exit_code": -3, "output": f"(error: {e})"}

    finally:
        if proc and proc.isalive():
            try:
                proc.terminate()
                time.sleep(0.3)
                proc.close()
            except Exception:
                pass


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
            pty_ok = False
            try:
                from winpty import PtyProcess
                pty_ok = True
            except ImportError:
                pass
            info = {
                "available": True,
                "binary": binary,
                "version": version,
                "pywinpty_installed": pty_ok,
                "exists_on_disk": os.path.isfile(binary) if os.path.isabs(binary) else bool(shutil.which(binary)),
            }
            return {"content": [{"type": "text", "text": json.dumps(info, indent=2, ensure_ascii=False)}]}

        if name == "codex_exec":
            prompt = args.get("prompt", "")
            timeout = args.get("timeout", 300)
            result = _run_codex(prompt, timeout)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"[exit: {result['exit_code']}]\n\n{result['output']}",
                    }
                ]
            }

        if name == "codex_review":
            target = args.get("target", "")
            focus = args.get("focus", "all")
            timeout = args.get("timeout", 300)
            focus_map = {
                "all": "Full code review",
                "bugs": "Find bugs in this code",
                "security": "Security audit of this code",
                "style": "Review code style",
                "performance": "Review code for performance issues",
            }
            prompt = f"{focus_map.get(focus, 'Review')}:\n\n{target}"
            result = _run_codex(prompt, timeout)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"[exit: {result['exit_code']}]\n\n{result['output']}",
                    }
                ]
            }

        if name == "codex_think":
            prompt = args.get("prompt", "")
            timeout = args.get("timeout", 300)
            result = _run_codex(f"Think deeply and analyze: {prompt}", timeout)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"[exit: {result['exit_code']}]\n\n{result['output']}",
                    }
                ]
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
            _send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "codex-bridge", "version": "0.1.0"},
                },
            })

        elif method == "notifications/initialized":
            pass

        elif method == "tools/list":
            _send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            })

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = _handle_tool_call(tool_name, arguments)
            _send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": result,
            })

        elif method == "ping":
            _send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {},
            })

        else:
            _send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })

    print(f"[codex_bridge] shutting down", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
