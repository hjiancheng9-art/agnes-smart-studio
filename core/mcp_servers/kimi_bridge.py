"""Kimi Bridge MCP Server v2 — CRUX <-> Kimi CLI bridge.

Wraps Kimi CLI as an MCP stdio server. Provides:
- kimi_exec    — Delegate task execution to Kimi
- kimi_review  — Code review via Kimi  
- kimi_login   — Refresh Kimi authentication
"""

import json, os, shutil, subprocess, sys, time
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────

KIMI_BINARY = shutil.which("kimi") or os.path.expanduser(
    "~/.kimi-code/bin/kimi.EXE"
)

JSONRPC_VERSION = "2.0"

ERR_PARSE = -32700
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

# ── Tool Definitions ───────────────────────────────────────────

TOOL_DEFS = [
    {
        "name": "kimi_exec",
        "description": (
            "Execute a task using Kimi CLI. Suitable for code generation, "
            "explanation, debugging, refactoring, and general coding tasks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task description for Kimi"},
                "work_dir": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 180)"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "kimi_review",
        "description": "Code review via Kimi CLI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "File/directory to review"},
                "work_dir": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 180)"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "kimi_status",
        "description": "Check Kimi CLI status: installed, logged in, version.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kimi_login",
        "description": "Refresh Kimi authentication. Call this when API returns 401/403 (token expired). Runs kimi login to refresh OAuth token.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 120)"
                }
            },
            "required": []
        },
    },
]


# ── JSON-RPC Helpers ───────────────────────────────────────────

def _response(id_val, result=None, error=None):
    resp = {"jsonrpc": JSONRPC_VERSION, "id": id_val}
    if error: resp["error"] = error
    else: resp["result"] = result
    return resp

def _error(id_val, code, message):
    return _response(id_val, error={"code": code, "message": message})


# ── Kimi Runner ────────────────────────────────────────────────

def _find_kimi():
    if os.path.isfile(KIMI_BINARY):
        return KIMI_BINARY
    return shutil.which("kimi")


def _check_status():
    kimi = _find_kimi()
    if not kimi:
        return {"installed": False, "error": "Kimi CLI not found"}
    
    ver = "unknown"
    try:
        r = subprocess.run([kimi, "-V"], capture_output=True, text=True,
                           timeout=10, env={**os.environ, "NO_COLOR": "1"})
        ver = r.stdout.strip() or r.stderr.strip()
    except:
        pass
    
    return {"installed": True, "binary": kimi, "version": ver}


def _run_kimi(prompt, *, work_dir=None, timeout=180):
    kimi = _find_kimi()
    if not kimi:
        return {"success": False, "error": "Kimi CLI not found", "output": ""}
    
    cmd = [kimi, "-p", prompt]
    wd = work_dir or os.getcwd()
    timeout = min(timeout, 600)
    
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=wd,
            env={**os.environ, "NO_COLOR": "1"},
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout[:50000],
            "stderr": result.stderr[:10000],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout ({timeout}s)", "output": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "output": ""}


# ── MCP Server ─────────────────────────────────────────────────

class KimiBridgeServer:
    def __init__(self):
        self._status = _check_status()

    def _send(self, resp):
        line = json.dumps(resp, ensure_ascii=True) + "\n"
        sys.stdout.buffer.write(line.encode('utf-8'))
        sys.stdout.buffer.flush()

    def _dispatch(self, method, req_id, params):
        try:
            if method == "tools/list":
                return self._tools_list(req_id)
            elif method == "tools/call":
                return self._tools_call(req_id, params)
            elif method == "initialize":
                return _response(req_id, result={
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "kimi-bridge", "version": "2.0"},
                    "capabilities": {"tools": {}},
                })
            elif method == "ping":
                return _response(req_id, result={"pong": True})
            return _error(req_id, ERR_METHOD_NOT_FOUND, f"Unknown: {method}")
        except Exception as e:
            return _error(req_id, ERR_INTERNAL, str(e))

    def _tools_list(self, req_id):
        status = _check_status()
        tools = []
        for t in TOOL_DEFS:
            tc = dict(t)
            if not status["installed"]:
                tc["description"] = "[NOT_AVAILABLE] " + tc["description"]
            tools.append(tc)
        return _response(req_id, result={"tools": tools})

    def _tools_call(self, req_id, params):
        name = params.get("name", "")
        args = params.get("arguments", {})

        if name == "kimi_login":
            timeout = args.get("timeout", 120)
            if not _check_status():
                # Force re-login
                try:
                    cmd = _find_kimi()
                    if cmd:
                        result = subprocess.run(
                            [cmd, "login", "--status"],
                            capture_output=True, text=True, timeout=timeout,
                            encoding="utf-8", errors="replace",
                        )
                        ok = "Success" in result.stdout or "signed in" in (result.stdout + result.stderr).lower() or result.returncode == 0
                        return _response(req_id, result={
                            "ok": ok,
                            "stdout": result.stdout.strip()[:500],
                            "stderr": result.stderr.strip()[:500],
                        })
                    else:
                        return _response(req_id, result={
                            "ok": False,
                            "error": "Kimi CLI not found",
                        })
                except Exception as e:
                    return _error(req_id, ERR_INTERNAL, str(e))
            else:
                return _response(req_id, result={
                    "ok": True,
                    "message": "Already authenticated",
                })
        elif name == "kimi_status":
            return _response(req_id, result={
                "content": [{"type": "text", "text": json.dumps(_check_status(), indent=2, ensure_ascii=False)}],
            })
        elif name == "kimi_exec":
            prompt = args.get("prompt", "")
            if not prompt:
                return _error(req_id, ERR_INVALID_PARAMS, "Missing 'prompt'")
            start = time.time()
            r = _run_kimi(prompt, work_dir=args.get("work_dir"), timeout=args.get("timeout", 180))
            elapsed = round(time.time() - start, 2)
            text = r.get("output", "") or r.get("error", "") or "(empty)"
            return _response(req_id, result={
                "content": [{"type": "text", "text": text}],
                "isError": not r["success"],
                "meta": {"success": r["success"], "elapsed": elapsed},
            })
        elif name == "kimi_review":
            target = args.get("target", "")
            if not target:
                return _error(req_id, ERR_INVALID_PARAMS, "Missing 'target'")
            start = time.time()
            r = _run_kimi(f"Review: {target}", work_dir=args.get("work_dir"), timeout=args.get("timeout", 180))
            elapsed = round(time.time() - start, 2)
            text = r.get("output", "") or r.get("error", "") or "(empty)"
            return _response(req_id, result={
                "content": [{"type": "text", "text": text}],
                "isError": not r["success"],
                "meta": {"success": r["success"], "elapsed": elapsed},
            })
        return _error(req_id, ERR_METHOD_NOT_FOUND, f"Unknown tool: {name}")

    def run(self):
        for line in sys.stdin.buffer:
            line = line.decode('utf-8').strip()
            if not line: continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self._send(_error(None, ERR_PARSE, "Invalid JSON"))
                continue
            rid = req.get("id")
            method = req.get("method", "")
            params = req.get("params")
            if method == "notifications/initialized":
                continue
            self._send(self._dispatch(method, rid, params))


def main():
    KimiBridgeServer().run()

if __name__ == "__main__":
    main()
