"""CodeBuddy CLI → MCP Bridge

Wraps Tencent CodeBuddy CLI (@tencent-ai/codebuddy-code) as an MCP stdio server.
Maps MCP tools/call → CodeBuddy CLI via `codebuddy -p` subprocess → returns results.

CodeBuddy CLI: `codebuddy` (npm global @tencent-ai/codebuddy-code v2.117.0)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from core.error_sink import catch


# ── ANSI cleanup ──

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ── Binary resolution ──

_CODEBUDDY_BINARY: str | None = None
_CODEBUDDY_VERSION: str = "unknown"


def _find_codebuddy() -> str | None:
    candidates = [
        os.path.expanduser(r"~\AppData\Roaming\npm\codebuddy.cmd"),
        os.path.expanduser(r"~\AppData\Roaming\npm\codebuddy"),
        shutil.which("codebuddy"),
        shutil.which("cbc"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _resolve_codebuddy() -> str | None:
    global _CODEBUDDY_BINARY
    if _CODEBUDDY_BINARY is None:
        _CODEBUDDY_BINARY = _find_codebuddy()
    return _CODEBUDDY_BINARY


def _get_version() -> str:
    global _CODEBUDDY_VERSION
    if _CODEBUDDY_VERSION == "unknown":
        binary = _resolve_codebuddy()
        if binary:
            try:
                r = subprocess.run(
                    f'"{binary}" --version',
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    encoding="utf-8",
                    errors="replace",
                )
                _CODEBUDDY_VERSION = (r.stdout or r.stderr or "").strip()
            except Exception as _es:
                catch(_es, "core/mcp_servers/codebuddy_bridge", "swallowed")
    return _CODEBUDDY_VERSION


# ── Execution ──


def _extract_result(output: str, prompt: str) -> dict:
    summary = ""
    code = ""
    lines = output.split("\n")
    in_code = False
    code_lines = []
    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                in_code = False
                code = "\n".join(code_lines)
            else:
                in_code = True
                code_lines = []
        elif in_code:
            code_lines.append(line)
        elif line.strip() and not summary:
            summary = line.strip()[:200]
    if not summary and code:
        summary = f"Generated {len(code.split(chr(10)))} lines of code"
    return {"summary": summary, "code": code}


def _run_codebuddy(prompt: str, timeout: int = 300) -> dict:
    binary = _resolve_codebuddy()
    if not binary:
        return {"success": False, "error": "CodeBuddy CLI not found"}
    try:
        safe_prompt = prompt.replace('"', "'")
        proc = subprocess.run(
            f'"{binary}" -p "{safe_prompt}"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode != 0 and not output.strip():
            return {"success": False, "error": f"CodeBuddy failed (exit={proc.returncode}): {stderr[:500]}"}
        output = _clean_ansi(output)
        result = _extract_result(output, prompt)
        return {"success": True, "output": output, "summary": result["summary"], "code": result["code"]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"CodeBuddy timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── MCP protocol ──


def _read_request() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    return json.loads(line) if line else None


def _send_response(response: dict) -> None:
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


TOOLS = [
    {
        "name": "codebuddy_status",
        "description": "Check CodeBuddy CLI availability and version.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "codebuddy_exec",
        "description": "Execute a coding task using Tencent CodeBuddy CLI.",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}, "timeout": {"type": "integer"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "codebuddy_review",
        "description": "Review code using Tencent CodeBuddy CLI.",
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "string"}, "timeout": {"type": "integer"}},
            "required": ["target"],
        },
    },
    {
        "name": "codebuddy_think",
        "description": "Deep analysis using Tencent CodeBuddy CLI.",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}, "timeout": {"type": "integer"}},
            "required": ["prompt"],
        },
    },
]


def _handle_tool_call(name: str, args: dict) -> dict:
    try:
        if name == "codebuddy_status":
            binary = _resolve_codebuddy()
            version = _get_version()
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "available": True,
                                "binary": binary,
                                "version": version,
                                "exists_on_disk": binary and os.path.isfile(binary),
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                    }
                ]
            }

        if name == "codebuddy_exec":
            prompt = args.get("prompt", "")
            timeout = args.get("timeout", 300)
            result = _run_codebuddy(prompt, timeout)
            if result.get("success"):
                return {"content": [{"type": "text", "text": result["output"]}]}
            return {"content": [{"type": "text", "text": f"Error: {result.get('error', 'unknown')}"}], "isError": True}

        if name == "codebuddy_review":
            target = args.get("target", "")
            timeout = args.get("timeout", 300)
            result = _run_codebuddy(f"Review the following code:\n\n{target}", timeout)
            if result.get("success"):
                return {"content": [{"type": "text", "text": result["output"]}]}
            return {"content": [{"type": "text", "text": f"Error: {result.get('error', 'unknown')}"}], "isError": True}

        if name == "codebuddy_think":
            prompt = args.get("prompt", "")
            timeout = args.get("timeout", 300)
            result = _run_codebuddy(f"Think deeply and analyze: {prompt}", timeout)
            if result.get("success"):
                return {"content": [{"type": "text", "text": result["output"]}]}
            return {"content": [{"type": "text", "text": f"Error: {result.get('error', 'unknown')}"}], "isError": True}

        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Internal error: {e}"}], "isError": True}


def main():
    binary = _resolve_codebuddy()
    version = _get_version()
    print(f"[codebuddy_bridge] binary={binary} version={version}", file=sys.stderr, flush=True)
    while True:
        try:
            request = _read_request()
            if request is None:
                break
            req_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params", {})
            if method == "initialize":
                _send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "serverInfo": {"name": "codebuddy-bridge", "version": "1.0.0"},
                            "capabilities": {"tools": {}},
                        },
                    }
                )
            elif method == "tools/list":
                _send_response({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
            elif method == "tools/call":
                _send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": _handle_tool_call(params.get("name", ""), params.get("arguments", {})),
                    }
                )
            elif method == "notifications/initialized":
                pass
            else:
                _send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                    }
                )
        except json.JSONDecodeError:
            pass
        except EOFError:
            break
        except Exception as e:
            print(f"[codebuddy_bridge] Error: {e}", file=sys.stderr, flush=True)
    print(f"[codebuddy_bridge] shutting down", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
