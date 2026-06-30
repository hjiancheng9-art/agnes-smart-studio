"""Copilot Bridge MCP Server — CRUX ↔ Copilot CLI 桥接。

将 GitHub Copilot CLI 包装为 MCP stdio 服务器，让 CRUX 可以：
- copilot_explore  — 委托代码探索（只读）
- copilot_code     — 委托代码实现
- copilot_review   — 委托代码审查（/review agent）
- copilot_think    — 委托深度分析
- copilot_status   — 检查 Copilot 状态

架构：
    CRUX → MCP Client → copilot_bridge.py (stdio) → copilot CLI subprocess
                                                           ↓
                                                  --agent 控制权限

与 kimi_bridge.py 镜像设计，让 CRUX 可以同时委派 Kimi 和 Copilot，
实现三方协同（CRUX 规划 → Kimi/Copilot 并行执行）。

使用方法：
    python core/mcp_servers/copilot_bridge.py
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ._mcp_utils import find_binary, run_subprocess

__all__ = ["CopilotBridgeServer", "run_copilot_bridge"]

# ── 常量 ───────────────────────────────────────────────────────

COPILOT_BINARY = shutil.which("copilot") or os.path.expanduser(
    "~/AppData/Roaming/npm/copilot.CMD"
)

MCP_PROTOCOL_VERSION = "2024-11-05"
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

# 工具定义：镜像 kimi_bridge.py
TOOL_DEFS = [
    {
        "name": "copilot_explore",
        "description": "委托 Copilot 做只读代码探索：读文件、搜索、Glob。不涉及写操作，安全可并行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "探索任务描述"},
                "work_dir": {"type": "string", "description": "工作目录（默认当前项目根）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 120）", "default": 120},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "copilot_code",
        "description": "委托 Copilot 执行完整编码任务：读-改-写-验证。CRUX 规划，Copilot 实现。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {"type": "string", "description": "实现计划（CRUX 规划好传给 Copilot 执行）"},
                "work_dir": {"type": "string", "description": "工作目录"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 600）", "default": 600},
            },
            "required": ["plan"],
        },
    },
    {
        "name": "copilot_review",
        "description": "委托 Copilot 执行代码审查：使用其内置 /review 或 /security-review agent。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["code", "security"],
                    "description": "审查模式：code=质量审查, security=安全审查（默认 code）",
                },
                "work_dir": {"type": "string", "description": "工作目录"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 300）", "default": 300},
            },
        },
    },
    {
        "name": "copilot_think",
        "description": "委托 Copilot 做深度分析：架构审查、方案设计。使用其 /research 能力。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "分析任务描述"},
                "model": {"type": "string", "description": "模型别名（如 gpt-5-mini, auto，默认 auto）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 300）", "default": 300},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "copilot_status",
        "description": "检查 Copilot CLI 状态：是否安装、登录、版本号、可用模型。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

TOOL_MAP = {t["name"]: t for t in TOOL_DEFS}


def _find_copilot() -> str | None:
    """定位 copilot 可执行文件。"""
    p = find_binary("copilot")
    if p:
        return p
    npm_cmd = os.path.expanduser("~/AppData/Roaming/npm/copilot.CMD")
    if os.path.isfile(npm_cmd):
        return npm_cmd
    return None


def _check_copilot_status() -> dict:
    """检查 Copilot CLI 状态。"""
    copilot = _find_copilot()
    if not copilot:
        return {
            "installed": False,
            "error": "Copilot CLI 未找到。安装: npm i -g @githubnext/github-copilot-cli",
        }

    try:
        r = run_subprocess([copilot, "--version"], timeout=10)
        version = r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        version = "unknown"

    # 检查 gh 登录状态
    gh_logged_in = False
    try:
        r2 = run_subprocess(["gh", "auth", "status"], timeout=10)
        gh_logged_in = r2.returncode == 0
    except Exception:
        pass

    # 检查可用模型
    models = []
    try:
        r3 = run_subprocess([copilot, "/model"], timeout=15)
        if r3.returncode == 0:
            out = r3.stdout + r3.stderr
            # 简单提取模型名
            import re
            models = re.findall(r"(gpt[-\w]+|claude[-\w]+|gemini[-\w]+)", out, re.IGNORECASE)
    except Exception:
        pass

    return {
        "installed": True,
        "path": copilot,
        "version": version,
        "logged_in": gh_logged_in,
        "models": models or ["auto (unknown)"],
        "hint": None if gh_logged_in else "请运行 'gh auth login' 完成认证",
    }


def _run_copilot_prompt(
    prompt: str,
    *,
    work_dir: str | None = None,
    timeout: int = 120,
    model: str | None = None,
    agent: str | None = None,
    extra_flags: list[str] | None = None,
) -> dict:
    """执行 copilot -p 并返回结构化结果。"""
    copilot = _find_copilot()
    if not copilot:
        return {"success": False, "error": "Copilot CLI 未安装", "output": ""}

    work_dir = work_dir or os.getcwd()

    cmd = [
        copilot,
        "-p", prompt,
        "-w", work_dir,
        "--allow-all-tools",
        "--allow-all-paths",
    ]
    if model:
        cmd.extend(["-m", model])
    if agent:
        cmd.extend(["--agent", agent])
    if extra_flags:
        cmd.extend(extra_flags)

    try:
        r = run_subprocess(cmd, timeout=timeout, cwd=work_dir)
        output = (r.stdout or "") + (r.stderr or "")
        success = r.returncode == 0 and "error:" not in r.stderr.lower()
        return {
            "success": success,
            "output": output.strip()[:10000],
            "rc": r.returncode,
            "work_dir": work_dir,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Copilot 任务超时 ({timeout}s)", "output": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "output": ""}


def _make_jsonrpc_response(id_val, result=None, error=None):
    resp = {"jsonrpc": "2.0", "id": id_val}
    if error:
        resp["error"] = error
    else:
        resp["result"] = result
    return resp


def _make_jsonrpc_error(id_val, code, message):
    return _make_jsonrpc_response(id_val, error={"code": code, "message": message})


# ── MCP Server ──────────────────────────────────────────────────

class CopilotBridgeServer:
    """Copilot Bridge MCP Server — stdio JSON-RPC 2.0。"""

    def __init__(self):
        self._initialized = False
        try:
            sys.stdout.reconfigure(newline="\n", encoding="utf-8", write_through=True)
            sys.stdin.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    def _send(self, msg: dict):
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _handle_initialize(self, req_id, params):
        self._initialized = True
        return _make_jsonrpc_response(req_id, result={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "copilot-bridge", "version": "1.0.0"},
        })

    def _handle_tools_list(self, req_id, params=None):
        status = _check_copilot_status()
        tools = []
        for t in TOOL_DEFS:
            tool_copy = dict(t)
            if not status["installed"] or not status.get("logged_in"):
                tool_copy["description"] = "[⚠ 不可用] " + tool_copy["description"]
            tools.append(tool_copy)
        return _make_jsonrpc_response(req_id, result={"tools": tools})

    def _handle_tools_call(self, req_id, params):
        tool_name = (params or {}).get("name", "")
        arguments = (params or {}).get("arguments", {}) or {}

        if tool_name == "copilot_status":
            status = _check_copilot_status()
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": json.dumps(status, ensure_ascii=False, indent=2)}],
            })

        status = _check_copilot_status()
        if not status["installed"]:
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": "❌ Copilot CLI 未安装。安装: npm i -g @githubnext/github-copilot-cli"}],
                "isError": True,
            })
        if not status.get("logged_in"):
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": "❌ 未登录 GitHub。请运行: gh auth login"}],
                "isError": True,
            })

        if tool_name == "copilot_explore":
            prompt = arguments.get("prompt", "")
            work_dir = arguments.get("work_dir") or os.getcwd()
            timeout = int(arguments.get("timeout", 120))
            enhanced = f"[ROLE: READ-ONLY CODE EXPLORER]\n{prompt}\n\n⚠ You have NO write access. Read and report only."
            result = _run_copilot_prompt(enhanced, work_dir=work_dir, timeout=timeout)
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": result.get("output", "")}],
                "structuredContent": result,
            })

        elif tool_name == "copilot_code":
            plan = arguments.get("plan", "")
            work_dir = arguments.get("work_dir") or os.getcwd()
            timeout = int(arguments.get("timeout", 600))
            enhanced = f"[ROLE: CODE IMPLEMENTER]\nExecute the following plan:\n\n{plan}\n\nImplement, verify, report."
            result = _run_copilot_prompt(enhanced, work_dir=work_dir, timeout=timeout)
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": result.get("output", "")}],
                "structuredContent": result,
            })

        elif tool_name == "copilot_review":
            mode = arguments.get("mode", "code")
            work_dir = arguments.get("work_dir") or os.getcwd()
            timeout = int(arguments.get("timeout", 300))

            if mode == "security":
                prompt = "/security-review"
            else:
                prompt = "/review"

            result = _run_copilot_prompt(prompt, work_dir=work_dir, timeout=timeout)
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": result.get("output", "")}],
                "structuredContent": result,
            })

        elif tool_name == "copilot_think":
            prompt = arguments.get("prompt", "")
            model = arguments.get("model", "auto")
            timeout = int(arguments.get("timeout", 300))
            # 使用 /research 命令做深度分析
            enhanced = f"[ROLE: DEEP ANALYSIS]\n{prompt}\n\nUse /research for deep investigation. Analyze thoroughly."
            result = _run_copilot_prompt(
                enhanced, timeout=timeout,
                extra_flags=["-m", model],
            )
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": result.get("output", "")}],
                "structuredContent": result,
            })

        return _make_jsonrpc_error(req_id, ERR_METHOD_NOT_FOUND, f"Unknown tool: {tool_name}")

    def _dispatch(self, method: str, req_id, params):
        handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
        }
        handler = handlers.get(method)
        if handler is None:
            return _make_jsonrpc_error(req_id, ERR_METHOD_NOT_FOUND, f"Method not found: {method}")
        try:
            return handler(req_id, params)
        except Exception as e:
            return _make_jsonrpc_error(req_id, ERR_INTERNAL, str(e))

    def run(self):
        """主循环：逐行读取 JSON-RPC 请求，路由并响应。"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self._send(_make_jsonrpc_error(None, ERR_PARSE, "Invalid JSON"))
                continue

            req_id = req.get("id")
            method = req.get("method", "")
            params = req.get("params")

            if method == "notifications/initialized":
                continue

            resp = self._dispatch(method, req_id, params)
            self._send(resp)


def run_copilot_bridge():
    """入口：启动 Copilot Bridge MCP Server。"""
    server = CopilotBridgeServer()
    server.run()


if __name__ == "__main__":
    run_copilot_bridge()
