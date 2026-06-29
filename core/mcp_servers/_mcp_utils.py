"""MCP Bridge 共享工具 — 二进制查找、版本检测、MCP 消息格式"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any

# ── MCP JSON-RPC 消息构造 ──────────────────────────────────

def make_result(req_id: str | None, data: Any) -> str:
    """构造 MCP result 响应 JSON。"""
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": data}, ensure_ascii=False)


def make_error(req_id: str | None, code: int, message: str) -> str:
    """构造 MCP error 响应 JSON。"""
    return json.dumps({
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": code, "message": message}
    }, ensure_ascii=False)


def make_tool_result(req_id: str | None, text: str, is_error: bool = False, meta: dict | None = None) -> str:
    """构造 tool_call result（tool 级别的返回）。"""
    content = [{"type": "text", "text": text}]
    result = {"content": content, "isError": is_error}
    if meta:
        result["meta"] = meta
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, ensure_ascii=False)


# ── 二进制查找 ─────────────────────────────────────────────

def find_binary(name: str) -> str | None:
    """在 PATH 中查找二进制文件。"""
    return shutil.which(name)


def find_binary_at(paths: list[str]) -> str | None:
    """从多个候选路径中查找存在的二进制。"""
    for p in paths:
        expanded = os.path.expanduser(os.path.expandvars(p))
        if os.path.isfile(expanded):
            return expanded
    return None


# ── 子进程运行（UTF-8 安全） ──────────────────────────────

def run_subprocess(
    cmd: list[str],
    *,
    timeout: float = 30,
    input_data: str | None = None,
    env_add: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """以 UTF-8 编码运行子进程，Windows GBK 区域友好。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["LANG"] = "en_US.UTF-8"
    if env_add:
        env.update(env_add)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        input=input_data,
        cwd=cwd,
        env=env,
    )


def get_version(binary: str, version_flag: str = "--version") -> str:
    """获取二进制版本号（静默容错）。"""
    try:
        r = run_subprocess([binary, version_flag], timeout=10)
        return (r.stdout.strip() or r.stderr.strip())[:200]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "unknown"


# ── MCP 健康检查 ──────────────────────────────────────────

def check_binary_health(name: str, binary: str | None) -> tuple[bool, str]:
    """检查二进制是否可用，返回 (ok, version_or_error)。"""
    if not binary:
        return False, f"{name} binary not found in PATH"
    version = get_version(binary)
    if version == "unknown":
        return False, f"{name} binary not executable"
    return True, version


# ── 工具注册辅助 ──────────────────────────────────────────

def build_tools_json(tools: list[dict[str, Any]]) -> str:
    """构造 tools/list 响应 JSON。"""
    return json.dumps({
        "jsonrpc": "2.0",
        "result": {"tools": tools},
        "id": None,
    }, ensure_ascii=False)
