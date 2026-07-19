"""CodeBuddy Marketplace Bridge — MCP stdio server.

CRUX's marketplace.py already handles CodeBuddy skill search/install.
This bridge provides only a health-check endpoint for TRM discovery.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _find_codebuddy() -> str | None:
    candidates = [
        os.path.expandvars(r"%APPDATA%\\npm\\codebuddy.cmd"),
        shutil.which("codebuddy"),
        shutil.which("cbc"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


TOOLS = [
    {
        "name": "codebuddy_status",
        "description": "Check CodeBuddy marketplace availability.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _handle_tool_call(name: str, args: dict) -> dict:
    if name == "codebuddy_status":
        binary = _find_codebuddy()
        available = False
        version = "unknown"
        if binary:
            try:
                r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
                available = r.returncode == 0
                version = (r.stdout or r.stderr or "").strip()
            except Exception:
                import logging

                logging.getLogger("crux").debug("silent except", exc_info=True)
        info = {"available": available, "binary": binary, "version": version}
        return {"content": [{"type": "text", "text": json.dumps(info, indent=2, ensure_ascii=False)}]}
    return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})
        if method == "initialize":
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "codebuddy-bridge", "version": "0.2.0"},
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}, ensure_ascii=False) + "\n"
            )
        elif method == "tools/call":
            result = _handle_tool_call(params.get("name", ""), params.get("arguments", {}))
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}, ensure_ascii=False) + "\n")
        elif method == "ping":
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {}}, ensure_ascii=False) + "\n")
        else:
            sys.stdout.write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}},
                    ensure_ascii=False,
                )
                + "\n"
            )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
