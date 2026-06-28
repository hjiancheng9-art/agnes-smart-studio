"""Kimi Bridge MCP Server — CRUX ↔ Kimi CLI 桥接。

将 Kimi CLI 包装为 MCP stdio 服务器，让 CRUX 可以：
- kimi_explore  — 委托代码探索（只读：Glob/Grep/ReadFile）
- kimi_think   — 委托深度分析（架构审查/方案设计）
- kimi_code    — 委托代码实现（完整读写能力）

架构：
    CRUX → MCP Client → kimi_bridge.py (stdio) → kimi CLI subprocess
                                                      ↓
                                              --agent-file 控制权限

Agent 文件:
    kimi_explore → read-only agent (排除 WriteFile/StrReplaceFile/Shell)
    kimi_code    → default agent (完整工具集)

通信:
    JSON-RPC 2.0 over stdin/stdout (newline-delimited)
    工具调用 → 构造 kimi prompt → 等待子进程完成 → 返回结果

参考:
    - claude-code-kimi-agent (zcyyyds-test) — agent YAML 权限控制
    - kimi-plugin-cross-platform (luhfilho) — 多宿主适配器模式
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

__all__ = ["KimiBridgeServer", "run_kimi_bridge"]

# ── 常量 ───────────────────────────────────────────────────────

KIMI_BINARY = shutil.which("kimi") or os.path.expanduser("~/.kimi-code/bin/kimi.EXE") or os.path.expanduser("~/.kimi-code/bin/kimi")
AGENTS_DIR = Path(__file__).resolve().parent / "kimi_agents"
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

# Agent 定义：只读探索模式
READONLY_AGENT_YAML = """version: 1
agent:
  name: crux-explore
  description: Read-only code exploration agent for CRUX Studio
  extend: default
  exclude_tools:
    - "kimi_cli.tools.file:WriteFile"
    - "kimi_cli.tools.file:StrReplaceFile"
    - "kimi_cli.tools.shell:Shell"
"""

# Agent 定义：完整代码实现模式
FULL_AGENT_YAML = """version: 1
agent:
  name: crux-code
  description: Full code implementation agent for CRUX Studio
  extend: default
"""

MCP_PROTOCOL_VERSION = "2024-11-05"
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

# 工具定义
TOOL_DEFS = [
    {
        "name": "kimi_explore",
        "description": "委托 Kimi 做只读代码探索：读文件、搜索、Glob。不进写操作，安全可并行。适合定位 bug/理解代码结构。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "探索任务描述（中文/英文均可）"},
                "work_dir": {"type": "string", "description": "工作目录（默认当前项目根）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 120）", "default": 120},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "kimi_think",
        "description": "委托 Kimi 做深度分析：架构审查、方案设计、代码审查。不触碰文件系统。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "分析任务描述"},
                "model": {"type": "string", "description": "模型别名（默认 default）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 300）", "default": 300},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "kimi_code",
        "description": "委托 Kimi 执行完整编码任务：读-改-写-验证。CRUX 负责规划，Kimi 负责实现。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {"type": "string", "description": "实现计划（CRUX 规划好传给 Kimi 执行）"},
                "work_dir": {"type": "string", "description": "工作目录（默认当前项目根）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 600）", "default": 600},
            },
            "required": ["plan"],
        },
    },
    {
        "name": "kimi_status",
        "description": "检查 Kimi CLI 状态：是否安装、是否登录、版本号。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

TOOL_MAP = {t["name"]: t for t in TOOL_DEFS}


def _find_kimi() -> str | None:
    """定位 kimi 可执行文件。"""
    p = shutil.which("kimi")
    if p:
        return p
    for base in [
        os.path.expanduser("~/.kimi-code/bin/kimi.EXE"),
        os.path.expanduser("~/.kimi-code/bin/kimi"),
        os.path.expanduser("~/kimi-code/bin/kimi"),
    ]:
        p2 = os.path.expanduser(base)
        if os.path.isfile(p2):
            return p2
    return None


def _check_kimi_status() -> dict:
    """检查 Kimi CLI 状态。"""
    kimi = _find_kimi()
    if not kimi:
        return {"installed": False, "error": "kimi CLI 未找到。请安装: npm i -g kimi-cli 或从 https://github.com/MoonshotAI/kimi-cli 下载"}

    try:
        r = subprocess.run([kimi, "--version"], capture_output=True, text=True, timeout=10)
        version = r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        version = "unknown"

    # 检查是否登录
    logged_in = False
    try:
        r2 = subprocess.run([kimi, "-p", "echo ok", "--output-format", "text"], capture_output=True, text=True, timeout=20)
        logged_in = "failed to run prompt" not in r2.stderr.lower() and r2.returncode == 0
    except Exception:
        pass

    return {
        "installed": True,
        "path": kimi,
        "version": version,
        "logged_in": logged_in,
        "hint": None if logged_in else "请运行 'kimi login' 完成认证",
    }


def _get_agent_file(mode: str) -> str:
    """获取或创建 agent YAML 文件路径。"""
    if mode == "explore":
        path = AGENTS_DIR / "crux-explore.yaml"
        path.write_text(READONLY_AGENT_YAML, encoding="utf-8")
    elif mode == "code":
        path = AGENTS_DIR / "crux-code.yaml"
        path.write_text(FULL_AGENT_YAML, encoding="utf-8")
    else:
        path = AGENTS_DIR / "crux-code.yaml"
        path.write_text(FULL_AGENT_YAML, encoding="utf-8")
    return str(path)


def _run_kimi_prompt(prompt: str, *, work_dir: str | None = None, timeout: int = 120, mode: str = "code", model: str | None = None) -> dict:
    """执行 kimi -p 并返回结构化结果。"""
    kimi = _find_kimi()
    if not kimi:
        return {"success": False, "error": "kimi CLI 未安装", "output": ""}

    work_dir = work_dir or os.getcwd()
    agent_file = _get_agent_file(mode)

    cmd = [
        kimi,
        "-p", prompt,
        "--agent-file", agent_file,
        "-w", work_dir,
        "--output-format", "text",
        "-y",  # 自动批准（仅限 explore 模式安全；code 模式需用户确认）
    ]
    if model:
        cmd.extend(["-m", model])

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=work_dir)
        output = (r.stdout or "") + (r.stderr or "")
        success = r.returncode == 0 and "error:" not in r.stderr.lower()
        return {
            "success": success,
            "output": output.strip()[:10000],  # 截断
            "rc": r.returncode,
            "mode": mode,
            "work_dir": work_dir,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Kimi 任务超时 ({timeout}s)", "output": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "output": ""}


def _make_jsonrpc_response(id_val, result=None, error=None):
    """构造 JSON-RPC 2.0 响应。"""
    resp = {"jsonrpc": "2.0", "id": id_val}
    if error:
        resp["error"] = error
    else:
        resp["result"] = result
    return resp


def _make_jsonrpc_error(id_val, code, message):
    return _make_jsonrpc_response(id_val, error={"code": code, "message": message})


# ── MCP Server ──────────────────────────────────────────────────


class KimiBridgeServer:
    """Kimi Bridge MCP Server — stdio JSON-RPC 2.0。"""

    def __init__(self):
        self._initialized = False
        try:
            sys.stdout.reconfigure(newline="\n", encoding="utf-8", write_through=True)
            sys.stdin.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    def _send(self, msg: dict):
        """发送 JSON-RPC 响应（单行）。"""
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _handle_initialize(self, req_id, params):
        self._initialized = True
        return _make_jsonrpc_response(req_id, result={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "kimi-bridge", "version": "1.0.0"},
        })

    def _handle_tools_list(self, req_id, params=None):
        status = _check_kimi_status()
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

        if tool_name == "kimi_status":
            status = _check_kimi_status()
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": json.dumps(status, ensure_ascii=False, indent=2)}],
            })

        status = _check_kimi_status()
        if not status["installed"]:
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": "❌ Kimi CLI 未安装。安装: npm i -g kimi-cli"}],
                "isError": True,
            })
        if not status.get("logged_in"):
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": "❌ Kimi 未登录。请运行: kimi login"}],
                "isError": True,
            })

        if tool_name == "kimi_explore":
            prompt = arguments.get("prompt", "")
            work_dir = arguments.get("work_dir") or os.getcwd()
            timeout = int(arguments.get("timeout", 120))
            # 增强 prompt：添加只读约束
            enhanced = f"[ROLE: READ-ONLY CODE EXPLORER]\n{prompt}\n\n⚠ You have NO write/shell tools. Read and report only."
            result = _run_kimi_prompt(enhanced, work_dir=work_dir, timeout=timeout, mode="explore")
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": result.get("output", "")}],
                "structuredContent": result,
            })

        elif tool_name == "kimi_think":
            prompt = arguments.get("prompt", "")
            model = arguments.get("model")
            timeout = int(arguments.get("timeout", 300))
            enhanced = f"[ROLE: DEEP ANALYSIS]\n{prompt}\n\nAnalyze thoroughly. No filesystem writes."
            result = _run_kimi_prompt(enhanced, timeout=timeout, mode="code", model=model)
            return _make_jsonrpc_response(req_id, result={
                "content": [{"type": "text", "text": result.get("output", "")}],
                "structuredContent": result,
            })

        elif tool_name == "kimi_code":
            plan = arguments.get("plan", "")
            work_dir = arguments.get("work_dir") or os.getcwd()
            timeout = int(arguments.get("timeout", 600))
            enhanced = f"[ROLE: CODE IMPLEMENTER]\nExecute the following plan:\n\n{plan}\n\nImplement, verify, report."
            result = _run_kimi_prompt(enhanced, work_dir=work_dir, timeout=timeout, mode="code")
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
                continue  # 跳过通知，不回复

            resp = self._dispatch(method, req_id, params)
            self._send(resp)


def run_kimi_bridge():
    """入口：启动 Kimi Bridge MCP Server。"""
    server = KimiBridgeServer()
    server.run()


if __name__ == "__main__":
    run_kimi_bridge()
