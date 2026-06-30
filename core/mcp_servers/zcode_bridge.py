"""ZCode Bridge MCP Server — CRUX <-> ZCode CLI bridge.

Wraps ZCode CLI (node zcode.cjs) as an MCP stdio server. Provides:
- zcode_exec    — Delegate task execution to ZCode
- zcode_review  — Code review via ZCode
- zcode_status  — Check ZCode CLI status
- zcode_plan    — Generate execution plan via ZCode (--mode plan)

Usage:
    From CRUX:
    mcp_call_tool("zcode-bridge", "zcode_exec", {"prompt": "..."})
"""

import json, os, shutil, subprocess, sys, time
from pathlib import Path

# ── Path fix: run as script → relative imports fail ──
_SCRIPT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))
from core.mcp_servers._mcp_utils import run_subprocess

# ── Constants ──────────────────────────────────────────────────

# ZCode 是 Electron 打包的 Node.js 应用，入口是 glm/zcode.cjs
_ZCODE_DIR = r"C:\Program Files\ZCode\resources\glm"
_ZCODE_CJS = os.path.join(_ZCODE_DIR, "zcode.cjs")
# Use patched version that bypasses model config requirement
_ZCODE_PATCHED = os.path.expanduser(r"~\.zcode\cli\zcode.cjs")
_NODE_BIN = shutil.which("node") or "node"

JSONRPC_VERSION = "2.0"

ERR_PARSE = -32700
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

# ── Tool Definitions ───────────────────────────────────────────

TOOL_DEFS = [
    {
        "name": "zcode_exec",
        "description": (
            "Execute a task using ZCode CLI (GLM provider). "
            "Suitable for code generation, explanation, debugging, "
            "refactoring, and general coding tasks. "
            "ZCode uses the GLM model family."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task description for ZCode"},
                "work_dir": {"type": "string", "description": "Working directory"},
                "mode": {
                    "type": "string",
                    "enum": ["build", "edit", "plan", "yolo"],
                    "description": "Permission mode (default: yolo)"
                },
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "zcode_review",
        "description": "Code review via ZCode CLI (GLM provider).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "File/directory to review"},
                "work_dir": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "zcode_status",
        "description": "Check ZCode CLI status: installed, version, binary location.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "zcode_plan",
        "description": (
            "Generate an execution plan via ZCode CLI (GLM provider) in plan mode. "
            "Use this for architecture design, implementation planning, "
            "and multi-step task decomposition."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Planning task description"},
                "work_dir": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 300)"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "zcode_login",
        "description": (
            "Set up ZCode CLI authentication. Opens OAuth flow (or prints URL with --no-browser). "
            "Required before zcode_exec/zcode_review/zcode_plan can work. "
            "Also supports direct API key input for BigModel provider."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "description": "Direct BigModel API key (skips OAuth). Get from https://open.bigmodel.cn/"
                },
                "no_browser": {
                    "type": "boolean",
                    "description": "Print OAuth URL instead of opening browser (default: true for headless)"
                },
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 120)"},
            },
            "required": [],
        },
    },
]


# ── JSON-RPC Helpers ───────────────────────────────────────────

def _response(id_val, result=None, error=None):
    resp = {"jsonrpc": JSONRPC_VERSION, "id": id_val}
    if error:
        resp["error"] = error
    else:
        resp["result"] = result
    return resp


def _error(id_val, code, message):
    return _response(id_val, error={"code": code, "message": message})


# ── ZCode Runner ───────────────────────────────────────────────

def _find_zcode():
    """Find ZCode CLI entry point. Prefer patched version."""
    if os.path.isfile(_ZCODE_PATCHED):
        return _NODE_BIN, _ZCODE_PATCHED
    if os.path.isfile(_ZCODE_CJS):
        return _NODE_BIN, _ZCODE_CJS
    return None, None


def _check_status():
    node, zcode = _find_zcode()
    if not zcode:
        return {"installed": False, "error": f"ZCode not found at {_ZCODE_CJS}"}

    if not shutil.which(node):
        return {"installed": False, "error": "Node.js not found"}

    ver = "unknown"
    try:
        r = run_subprocess(
            [node, zcode, "--version"],
            timeout=15,
            env_add={"NO_COLOR": "1"},
        )
        ver = r.stdout.strip() or r.stderr.strip()
    except Exception:
        pass

    return {
        "installed": True,
        "binary": zcode,
        "node": node,
        "version": ver,
    }


def _run_zcode(prompt, *, work_dir=None, mode="yolo", timeout=300, api_key=None):
    """Run ZCode with a prompt and return results."""
    node, zcode = _find_zcode()
    if not zcode:
        return {"success": False, "error": f"ZCode not found at {_ZCODE_CJS}", "output": ""}

    cmd = [node, zcode, "--prompt", prompt, "--mode", mode]
    wd = work_dir or os.getcwd()
    timeout = min(timeout, 600)

    # Pass API key via environment variable
    env = {**os.environ, "NO_COLOR": "1"}
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    try:
        result = run_subprocess(
            cmd,
            timeout=timeout, cwd=wd,
            env_add=env,
        )
        stderr = result.stderr[:10000]
        stdout = result.stdout[:50000]

        # Detect auth/config errors and give helpful hints
        if "Model config is missing" in stderr or "Model config is missing" in stdout:
            hint = (
                "ZCode needs authentication. Run zcode_login to set up:\n"
                "  - OAuth: zcode_login()  (opens browser)\n"
                "  - API Key: zcode_login(api_key='your-bigmodel-key')\n"
                "Get BigModel API keys at https://open.bigmodel.cn/"
            )
            return {
                "success": False,
                "error": "Authentication required",
                "output": hint,
                "stderr": stderr,
                "exit_code": result.returncode,
            }

        return {
            "success": result.returncode == 0,
            "output": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout ({timeout}s)", "output": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "output": ""}


# ── MCP Server ─────────────────────────────────────────────────

def _setup_api_key_config(api_key):
    """Write ZCode CLI config with a direct API key for BigModel provider."""
    config_path = os.path.expanduser(r"~\.zcode\cli\config.json")
    config_dir = os.path.dirname(config_path)

    config = {
        "main": {
            "provider": "bigmodel",
            "model": "GLM-5.2",
        },
        "provider": {
            "bigmodel": {
                "name": "Bigmodel - API Key",
                "kind": "anthropic",
                "options": {
                    "apiKey": api_key,
                    "baseURL": "https://open.bigmodel.cn/api/anthropic",
                },
                "models": {
                    "GLM-5.2": {
                        "limit": {"context": 1000000},
                        "modalities": {
                            "input": ["text"],
                            "output": ["text"],
                        },
                    },
                    "GLM-5-Turbo": {
                        "name": "glm-5-turbo",
                        "reasoning": {
                            "enabled": True,
                            "variants": ["enabled", "off"],
                            "defaultVariant": "enabled",
                        },
                        "limit": {"context": 200000, "output": 64000},
                        "modalities": {
                            "input": ["text"],
                            "output": ["text"],
                        },
                    },
                },
                "source": "custom",
                "enabled": True,
            }
        },
    }

    try:
        os.makedirs(config_dir, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True, f"Config written to {config_path}"
    except Exception as e:
        return False, str(e)


class ZCodeBridgeServer:
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
                    "serverInfo": {"name": "zcode-bridge", "version": "1.0"},
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

        if name == "zcode_status":
            return _response(req_id, result={
                "content": [{"type": "text", "text": json.dumps(
                    _check_status(), indent=2, ensure_ascii=False
                )}],
            })

        elif name == "zcode_exec":
            prompt = args.get("prompt", "")
            if not prompt:
                return _error(req_id, ERR_INVALID_PARAMS, "Missing 'prompt'")
            start = time.time()
            mode = args.get("mode", "yolo")
            r = _run_zcode(
                prompt,
                work_dir=args.get("work_dir"),
                mode=mode,
                timeout=args.get("timeout", 300),
                api_key=args.get("api_key"),
            )
            elapsed = round(time.time() - start, 2)
            text = r.get("output", "") or r.get("error", "") or "(empty)"
            return _response(req_id, result={
                "content": [{"type": "text", "text": text}],
                "isError": not r["success"],
                "meta": {"success": r["success"], "elapsed": elapsed},
            })

        elif name == "zcode_review":
            target = args.get("target", "")
            if not target:
                return _error(req_id, ERR_INVALID_PARAMS, "Missing 'target'")
            start = time.time()
            r = _run_zcode(
                f"Review this code for bugs, style, security, and performance issues: {target}",
                work_dir=args.get("work_dir"),
                mode="edit",
                timeout=args.get("timeout", 300),
                api_key=args.get("api_key"),
            )
            elapsed = round(time.time() - start, 2)
            text = r.get("output", "") or r.get("error", "") or "(empty)"
            return _response(req_id, result={
                "content": [{"type": "text", "text": text}],
                "isError": not r["success"],
                "meta": {"success": r["success"], "elapsed": elapsed},
            })

        elif name == "zcode_plan":
            prompt = args.get("prompt", "")
            if not prompt:
                return _error(req_id, ERR_INVALID_PARAMS, "Missing 'prompt'")
            start = time.time()
            r = _run_zcode(
                prompt,
                work_dir=args.get("work_dir"),
                mode="plan",
                timeout=args.get("timeout", 300),
                api_key=args.get("api_key"),
            )
            elapsed = round(time.time() - start, 2)
            text = r.get("output", "") or r.get("error", "") or "(empty)"
            return _response(req_id, result={
                "content": [{"type": "text", "text": text}],
                "isError": not r["success"],
                "meta": {"success": r["success"], "elapsed": elapsed},
            })

        elif name == "zcode_login":
            api_key = args.get("api_key", "")
            no_browser = args.get("no_browser", True)
            timeout = args.get("timeout", 120)

            if api_key:
                # Store API key and set up config
                ok, msg = _setup_api_key_config(api_key)
                # Also test connectivity
                test_r = _run_zcode(
                    "say ok", mode="yolo", timeout=30, api_key=api_key
                )
                if test_r["success"]:
                    msg += " | API key validated successfully!"
                else:
                    msg += f" | API test failed: {test_r.get('error', 'unknown')}"
                return _response(req_id, result={
                    "content": [{"type": "text", "text": json.dumps({
                        "ok": ok and test_r["success"],
                        "message": msg,
                        "hint": "Set ANTHROPIC_API_KEY env var for persistent use, or pass api_key in each call."
                    }, indent=2, ensure_ascii=False)}],
                })
            else:
                # Try OAuth login (opens browser or prints URL)
                node, zcode = _find_zcode()
                if not zcode:
                    return _error(req_id, ERR_INTERNAL, "ZCode not found")
                try:
                    cmd = [node, zcode, "login"]
                    if no_browser:
                        cmd.append("--no-browser")
                    result = run_subprocess(
                        cmd,
                        timeout=timeout,
                        env_add={"NO_COLOR": "1"},
                    )
                    output = (result.stdout + result.stderr).strip()
                    ok = result.returncode == 0
                    return _response(req_id, result={
                        "content": [{"type": "text", "text": json.dumps({
                            "ok": ok,
                            "output": output[:2000],
                            "hint": (
                                "OAuth login completed. If it failed, provide a BigModel API key: "
                                "zcode_login(api_key='your-key-here'). "
                                "Get keys at https://open.bigmodel.cn/"
                            ),
                        }, indent=2, ensure_ascii=False)}],
                    })
                except Exception as e:
                    return _error(req_id, ERR_INTERNAL, str(e))

        return _error(req_id, ERR_METHOD_NOT_FOUND, f"Unknown tool: {name}")

    def run(self):
        for line in sys.stdin.buffer:
            line = line.decode('utf-8').strip()
            if not line:
                continue
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
    ZCodeBridgeServer().run()


if __name__ == "__main__":
    main()
