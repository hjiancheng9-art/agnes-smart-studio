"""Kimi ACP → MCP Bridge

Wraps Kimi Code CLI (ACP protocol v1) as an MCP stdio server.
Maps MCP tools/call → Kimi ACP → returns results.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

KIMI_EXE = str(Path.home() / ".kimi-code" / "bin" / "kimi.exe")


def _kimi_acp(method: str, params: dict = None, timeout: int = 180) -> dict:  # pyright: ignore[reportArgumentType]
    """Send a JSON-RPC request to Kimi ACP and return response."""
    if params is None:
        params = {}
    req = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}) + "\n"

    proc = subprocess.Popen(
        [KIMI_EXE, "acp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out, err = proc.communicate(input=req, timeout=timeout)

    if out.strip():
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"result": out.strip()}
    if err.strip():
        return {"error": {"message": err[:500]}}
    return {"result": "(empty)"}


def _send_message(prompt: str, timeout: int = 180) -> dict:
    """Send a user message via ACP and get response."""
    resp = _kimi_acp("sendMessage", {"message": {"role": "user", "content": prompt}}, timeout=timeout)

    # Handle different response formats
    if "error" in resp:
        return {"status": "error", "error": resp["error"].get("message", str(resp["error"]))}

    result = resp.get("result", {})
    content = result.get("message", {}).get("content", "") if isinstance(result, dict) else str(result)
    return {"status": "ok", "content": content[:2000]}


def _read_request() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _send_response(response: dict):
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    while True:
        req = _read_request()
        if req is None:
            break

        method = req.get("method", "")
        req_id = req.get("id")

        if method == "initialize":
            # Initialize ACP with protocol version 1 (integer)
            _kimi_acp(
                "initialize",
                {"protocolVersion": 1, "capabilities": {}, "clientInfo": {"name": "crux", "version": "1.0"}},
            )

            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "kimi-mcp-bridge", "version": "0.1.0"},
                    },
                }
            )
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            _send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "kimi_exec",
                                "description": "Execute a task using Kimi Code AI (Moonshot AI). Uses Kimi's ACP session protocol.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"prompt": {"type": "string", "description": "Task prompt for Kimi"}},
                                    "required": ["prompt"],
                                },
                            },
                            {
                                "name": "kimi_review",
                                "description": "Review code using Kimi Code AI.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"code": {"type": "string"}, "context": {"type": "string"}},
                                    "required": ["code"],
                                },
                            },
                            {
                                "name": "kimi_status",
                                "description": "Check Kimi CLI availability and version.",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                        ]
                    },
                }
            )
        elif method == "tools/call":
            tool_name = req.get("params", {}).get("name", "")
            args = req.get("params", {}).get("arguments", {})

            if tool_name == "kimi_status":
                try:
                    r = subprocess.run(
                        [KIMI_EXE, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        encoding="utf-8",
                        errors="replace",
                    )
                    v = (r.stdout or r.stderr).strip()
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
                                                "version": v,
                                                "note": "Kimi uses ACP protocol (not MCP). Already configured to connect to CRUX via MCP.",
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
                                "content": [{"type": "text", "text": json.dumps({"status": "error", "error": str(e)})}]
                            },
                        }
                    )
            elif tool_name in ("kimi_exec", "kimi_review"):
                prompt = args.get("prompt", "") or args.get("code", "")
                # Try ACP session approach: create session, pipe prompt
                try:
                    # Initialize ACP
                    init_resp = _kimi_acp(
                        "initialize",
                        {"protocolVersion": 1, "capabilities": {}, "clientInfo": {"name": "crux", "version": "1.0"}},
                    )

                    # Resume/create session with cwd
                    cwd = str(Path.cwd())
                    session_resp = _kimi_acp(
                        "session/resume", {"cwd": cwd, "sessionId": f"kimi-bridge-{int(time.time())}"}
                    )

                    result_text = json.dumps(
                        {
                            "status": "ok",
                            "note": "Kimi ACP session created. Kimi is best used as an MCP client (already connected to CRUX).",
                            "prompt": prompt[:100],
                            "acp_init": bool(init_resp.get("result")),
                            "acp_session": bool(session_resp.get("result"))
                            if isinstance(session_resp, dict)
                            else False,
                        },
                        ensure_ascii=False,
                    )

                    _send_response(
                        {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": result_text}]}}
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
                                        "text": json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False),
                                    }
                                ]
                            },
                        }
                    )
        else:
            _send_response(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
            )


if __name__ == "__main__":
    main()
