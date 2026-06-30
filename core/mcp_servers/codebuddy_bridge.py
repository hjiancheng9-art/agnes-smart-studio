"""CodeBuddy Bridge MCP Server — CRUX ↔ CodeBuddy CLI 桥接。

将 CodeBuddy CLI 包装为 MCP stdio 服务器，让 CRUX 可以：
- codebuddy_exec   — 委派编码任务（读-改-写）
- codebuddy_review — 代码审查
- codebuddy_think  — 深度分析/架构设计
- codebuddy_search — 代码搜索/探索（只读）
- codebuddy_status — 检查 CodeBuddy 状态
"""

from ._mcp_utils import run_subprocess
import os
import sys
import json
import subprocess
import asyncio
import signal
from typing import Any, Optional

# ── 工具定义 ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "codebuddy_exec",
        "description": "委托 CodeBuddy 执行完整编码任务：读-改-写-验证。"
                       "CRUX 规划，CodeBuddy 实现。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "description": "实现计划（清晰的步骤描述）"
                },
                "work_dir": {
                    "type": "string",
                    "description": "工作目录（默认当前项目根）"
                },
                "model": {
                    "type": "string",
                    "description": "模型名称（如 sonnet, opus, haiku, auto，默认 auto）"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认 600）",
                    "default": 600
                }
            },
            "required": ["plan"]
        }
    },
    {
        "name": "codebuddy_review",
        "description": "委托 CodeBuddy 执行代码审查。使用其内置审查能力检查质量/安全。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "审查目标：文件路径 或 描述（如 'git diff'、'recent changes'）"
                },
                "focus": {
                    "type": "string",
                    "enum": ["all", "bugs", "security", "style", "performance"],
                    "description": "审查焦点（默认 all）"
                },
                "work_dir": {
                    "type": "string",
                    "description": "工作目录"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认 300）",
                    "default": 300
                }
            },
            "required": ["target"]
        }
    },
    {
        "name": "codebuddy_think",
        "description": "委托 CodeBuddy 做深度分析：架构审查、方案设计、技术调研。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "分析任务描述"
                },
                "model": {
                    "type": "string",
                    "description": "模型名称（如 opus, sonnet, auto，默认 auto）"
                },
                "work_dir": {
                    "type": "string",
                    "description": "工作目录"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认 300）",
                    "default": 300
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "codebuddy_search",
        "description": "委托 CodeBuddy 做只读代码搜索/探索：读文件、搜索、Grep、Glob。"
                       "安全可并行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "探索任务描述"
                },
                "work_dir": {
                    "type": "string",
                    "description": "工作目录"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认 120）",
                    "default": 120
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "codebuddy_status",
        "description": "检查 CodeBuddy CLI 状态：是否安装、版本号、可用模型等。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


# ── 辅助函数 ──────────────────────────────────────────────

def find_codebuddy_cli() -> Optional[str]:
    """Find the CodeBuddy CLI executable."""
    candidates = [
        r"C:\Users\huangjiancheng\AppData\Roaming\npm\codebuddy.cmd",
        r"C:\Users\huangjiancheng\AppData\Roaming\npm\codebuddy",
        "codebuddy",
        "codebuddy.cmd",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
        try:
            r = run_subprocess(["where", c], timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip().split('\n')[0]
        except Exception:
            continue
    return None


def run_codebuddy(prompt: str = "", *, work_dir: str = None, model: str = None,
                  timeout: int = 600, extra_flags: list = None,
                  allow_tools: bool = True) -> dict:
    """Run CodeBuddy CLI non-interactively and return structured result."""
    cb = find_codebuddy_cli()
    if not cb:
        return {"ok": False, "error": "CodeBuddy CLI not found", "output": ""}

    cmd = [cb, "-p", prompt]
    if work_dir and os.path.isdir(work_dir):
        cmd = [cb, "-p", prompt]
        # Set working directory via subprocess cwd
    if model and model != "auto":
        cmd.extend(["--model", model])
    if allow_tools:
        cmd.append("--skip-permissions")
    if extra_flags:
        cmd.extend(extra_flags)

    try:
        r = run_subprocess(
            cmd,
            cwd=work_dir or None,
            timeout=timeout
        )
        return {
            "ok": r.returncode == 0,
            "output": r.stdout or "",
            "error": r.stderr or "",
            "rc": r.returncode
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout after {timeout}s", "output": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "output": ""}


def get_status() -> dict:
    """Check CodeBuddy CLI status."""
    cb = find_codebuddy_cli()
    result = {
        "installed": cb is not None,
        "path": cb,
        "version": "unknown",
        "models": [],
        "mcp_servers": [],
        "error": None
    }

    if not cb:
        result["error"] = "CodeBuddy CLI not found"
        return result

    try:
        r = run_subprocess([cb, "--version"], timeout=10)
        if r.returncode == 0:
            result["version"] = r.stdout.strip()
    except Exception as e:
        result["error"] = str(e)

    # Check MCP server list
    try:
        r = run_subprocess([cb, "mcp", "list"], timeout=10)
        if r.returncode == 0:
            result["mcp_servers"] = r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return result


# ── MCP stdio 服务器 ──────────────────────────────────────

async def handle_request(request: dict) -> dict:
    """Handle a single MCP request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "codebuddy-bridge",
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {}
                }
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        }

    elif method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "codebuddy_status":
                status = get_status()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(status, ensure_ascii=False)}]
                    }
                }

            elif tool_name == "codebuddy_exec":
                plan = arguments.get("plan", "")
                work_dir = arguments.get("work_dir")
                model = arguments.get("model", "auto")
                timeout = arguments.get("timeout", 600)
                result = run_codebuddy(
                    f"Execute this coding plan:\n\n{plan}",
                    work_dir=work_dir, model=model, timeout=timeout
                )
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                    }
                }

            elif tool_name == "codebuddy_review":
                target = arguments.get("target", "")
                focus = arguments.get("focus", "all")
                work_dir = arguments.get("work_dir")
                timeout = arguments.get("timeout", 300)
                prompt = f"Review the following code with focus on {focus}:\n{target}"
                result = run_codebuddy(prompt, work_dir=work_dir, timeout=timeout, allow_tools=False)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                    }
                }

            elif tool_name == "codebuddy_think":
                prompt = arguments.get("prompt", "")
                model = arguments.get("model", "auto")
                work_dir = arguments.get("work_dir")
                timeout = arguments.get("timeout", 300)
                result = run_codebuddy(prompt, work_dir=work_dir, model=model,
                                       timeout=timeout, allow_tools=False)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                    }
                }

            elif tool_name == "codebuddy_search":
                prompt = arguments.get("prompt", "")
                work_dir = arguments.get("work_dir")
                timeout = arguments.get("timeout", 120)
                result = run_codebuddy(
                    f"Search/explore the codebase (read-only): {prompt}",
                    work_dir=work_dir, timeout=timeout, allow_tools=False
                )
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                    }
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(e)}
            }

    elif method == "notifications/initialized":
        return None  # No response for notifications

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}
        }


def main():
    """MCP stdio main loop — thread-based, Windows-compatible."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = asyncio.run(handle_request(request))
            if response:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            pass


if __name__ == "__main__":
    main()
