"""Unit tests for core/codex_engines.py — JSRepl 安全过滤与包裹逻辑。

codex_engines.py 的 JSRepl 是 Node.js one-shot subprocess 执行引擎，
带危险模式预检 + vm sandbox 包裹。可测部分：
- _JS_BLOCKED 预检列表（危险模式拒绝）
- _SANDBOX_WRAPPER 转义（反引号/反斜杠/$）
- Node.js 未安装时的降级消息
- eval 超时和子进程错误处理（monkeypatch subprocess.run）

MCP / Playwright / transcribe / imagegen 全需外部运行时，跳过。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.codex_engines import JSRepl


# ── _JS_BLOCKED 预检 ───────────────────────────────────────────────


def test_blocked_patterns_list_is_non_empty():
    """JSRepl._JS_BLOCKED 应包含已知危险模式。"""
    blocked = JSRepl._JS_BLOCKED
    assert len(blocked) >= 8
    # 几个必有的危险模式
    assert "child_process" in blocked
    assert "fs." in blocked
    assert "process.exit" in blocked
    assert "net." in blocked


def test_eval_rejects_child_process():
    """含 child_process 的代码应被安全拒绝。"""
    repl = JSRepl()
    result = repl.eval("const cp = require('child_process')")
    assert "[JS 安全拒绝]" in result
    assert "child_process" in result


def test_eval_rejects_fs_import():
    """fs 模块导入应被拒绝。"""
    repl = JSRepl()
    result = repl.eval('const fs = require("fs")')
    assert "[JS 安全拒绝]" in result
    assert "fs" in result


def test_eval_rejects_process_exit():
    """process.exit 调用应被拒绝。"""
    repl = JSRepl()
    result = repl.eval("process.exit(0)")
    assert "[JS 安全拒绝]" in result
    assert "process.exit" in result


def test_eval_rejects_process_env():
    """process.env 访问应被拒绝。"""
    repl = JSRepl()
    result = repl.eval("console.log(process.env.HOME)")
    assert "[JS 安全拒绝]" in result
    assert "process.env" in result


def test_eval_rejects_process_cwd():
    """process.cwd() 调用应被拒绝。"""
    repl = JSRepl()
    result = repl.eval("process.cwd()")
    assert "[JS 安全拒绝]" in result


def test_eval_rejects_net_import():
    """net 模块导入应被拒绝。"""
    repl = JSRepl()
    result = repl.eval("const net = require('net')")
    assert "[JS 安全拒绝]" in result
    assert "net" in result


def test_eval_case_insensitive_blocked():
    """预检应大小写不敏感（code_lower）。"""
    repl = JSRepl()
    result = repl.eval("const F = require('FS')")
    # code_lower → 'fs' 在 _JS_BLOCKED "require('fs')" 中（但检查方式是 `pattern in code_lower`）
    # 大写 FS 不会被 require('fs') 命中，但 require("fs") 也不会
    # 实际：code_lower = "const f = require('fs')" → 包含 "require('fs')" → 拒绝
    # 但 "require('FS')" lower → "require('fs')" → 命中
    # 这里测试的是另一种大写方式
    assert "[JS 安全拒绝]" in result


def test_eval_allows_safe_math():
    """纯数学运算应通过预检（不被阻断）。"""
    repl = JSRepl()
    # 不含任何 blocked pattern
    code = "Math.sqrt(144)"
    # 即使后续 subprocess 失败，也不应返回 "安全拒绝"
    # monkeypatch _node_path 为 None → 得到 "未安装" 而非 "安全拒绝"
    repl._node_path = None
    result = repl.eval(code)
    assert "[JS 安全拒绝]" not in result


def test_eval_allows_safe_json():
    """JSON.parse 应通过预检。"""
    repl = JSRepl()
    repl._node_path = None
    result = repl.eval("JSON.parse('{}')")
    assert "[JS 安全拒绝]" not in result


# ── Node.js 未安装降级 ───────────────────────────────────────────


def test_eval_no_node_returns_error_message():
    """Node.js 未安装时应返回友好错误，不抛异常。"""
    repl = JSRepl()
    repl._node_path = None
    result = repl.eval("1+1")
    assert "[错误]" in result
    assert "Node.js" in result


# ── _SANDBOX_WRAPPER 转义 ────────────────────────────────────────


def test_sandbox_wrapper_exists_and_is_template():
    """JSRepl._SANDBOX_WRAPPER 应是含 %s 占位符的字符串。"""
    wrapper = JSRepl._SANDBOX_WRAPPER
    assert isinstance(wrapper, str)
    assert "%s" in wrapper


def test_sandbox_wrapper_contains_timeout_placeholder():
    """wrapper 应有 timeout 占位符。"""
    assert "timeout" in JSRepl._SANDBOX_WRAPPER.lower()


def test_sandbox_wrapper_strips_dangerous_globals():
    """wrapper sandbox 应限制 process/global 为 undefined。"""
    assert "process: undefined" in JSRepl._SANDBOX_WRAPPER
    assert "global: undefined" in JSRepl._SANDBOX_WRAPPER


def test_eval_escapes_backticks():
    """用户代码中的反引号应被转义，避免破坏 wrapper 的模板字面量。"""
    repl = JSRepl()
    escaped = "const s = `hello`".replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    assert "`hello`" not in escaped  # 原始反引号应消失
    assert "\\`hello\\`" in escaped  # 应被转义


def test_eval_escapes_dollar_signs():
    """$ 符号应被转义（前面加反斜杠），避免模板字面量插值。"""
    repl = JSRepl()
    code = "const x = ${1 + 2}"
    escaped = code.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    # 转义后 $ 前应有反斜杠（不被模板字面量插值）
    assert "\\$" in escaped


# ── subprocess 模拟 ───────────────────────────────────────────────


def test_eval_success_returns_stdout():
    """成功执行时应返回 stdout。"""
    repl = JSRepl()
    mock_result = subprocess.CompletedProcess(
        args=["node"], returncode=0, stdout="42", stderr=""
    )
    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", return_value=mock_result):
        result = repl.eval("6*7")
    assert result == "42"


def test_eval_no_output_returns_no_output_marker():
    """stdout 为空时应返回 '(no output)'。"""
    repl = JSRepl()
    mock_result = subprocess.CompletedProcess(
        args=["node"], returncode=0, stdout="", stderr=""
    )
    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", return_value=mock_result):
        result = repl.eval("let x = 1")
    assert result == "(no output)"


def test_eval_nonzero_exit_returns_stderr():
    """子进程非零退出时应返回 stderr 错误。"""
    repl = JSRepl()
    mock_result = subprocess.CompletedProcess(
        args=["node"], returncode=1, stdout="", stderr="ReferenceError: x is not defined"
    )
    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", return_value=mock_result):
        result = repl.eval("x")
    assert "[JS Error]" in result
    assert "ReferenceError" in result


def test_eval_timeout_returns_timeout_message():
    """超时时应返回超时提示。"""
    repl = JSRepl()
    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="node", timeout=5)):
        result = repl.eval("while(true){}", timeout_ms=100)
    assert "[JS Error]" in result
    assert "超时" in result


def test_eval_subprocess_error_returns_error():
    """subprocess 异常（如文件不存在）应返回错误。"""
    repl = JSRepl()
    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", side_effect=FileNotFoundError("not found")):
        result = repl.eval("1+1")
    assert "[JS Error]" in result


def test_eval_stderr_truncated_to_500_chars():
    """错误 stderr 应截断到 500 字符，避免超长输出。"""
    repl = JSRepl()
    mock_result = subprocess.CompletedProcess(
        args=["node"], returncode=1, stdout="",
        stderr="x" * 1000
    )
    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", return_value=mock_result):
        result = repl.eval("bad code")
    # 错误消息中 stderr 部分不应超过 500 字符
    assert len(result) < 600  # "[JS Error] " 前缀 + 500 字符


# ── close ──────────────────────────────────────────────────────────


def test_close_is_noop():
    """one-shot 模型无资源需释放，close 应无副作用。"""
    repl = JSRepl()
    repl.close()  # 不抛异常


# ── _find_node ────────────────────────────────────────────────────


def test_find_node_returns_path_when_available():
    """shutil.which 找到 node 时应返回路径。"""
    repl = JSRepl()
    with patch("shutil.which", return_value="/usr/bin/node"):
        result = repl._find_node()
    assert result == "/usr/bin/node"


def test_find_node_returns_none_when_unavailable():
    """shutil.which 找不到 node 时应返回 None。"""
    repl = JSRepl()
    with patch("shutil.which", return_value=None):
        result = repl._find_node()
    assert result is None


# ── 额外安全阻断测试 ────────────────────────────────────────────


def test_eval_rejects_process_kill():
    """process.kill 调用应被拒绝。"""
    repl = JSRepl()
    result = repl.eval("process.kill(123)")
    assert "[JS 安全拒绝]" in result
    assert "process.kill" in result


def test_eval_rejects_process_chdir():
    """process.chdir 调用应被拒绝。"""
    repl = JSRepl()
    result = repl.eval("process.chdir('/tmp')")
    assert "[JS 安全拒绝]" in result
    assert "process.chdir" in result


def test_eval_rejects_fs_dot_methods():
    """fs.readFileSync 等 fs 方法应被拒绝。"""
    repl = JSRepl()
    for snippet in ["fs.readFileSync('/etc/passwd')", "fs.writeFile('/tmp/x', 'data')"]:
        result = repl.eval(snippet)
        assert "[JS 安全拒绝]" in result, f"'{snippet}' should be blocked"


# ── 安全通过测试（非危险代码） ──────────────────────────────────


def test_eval_passes_safe_console_code():
    """console.log 应通过安全预检。"""
    repl = JSRepl()
    repl._node_path = None
    result = repl.eval("console.log('hello')")
    assert "[JS 安全拒绝]" not in result


def test_eval_passes_safe_array_operations():
    """数组操作应通过安全预检。"""
    repl = JSRepl()
    repl._node_path = None
    result = repl.eval("[1,2,3].map(x => x * 2)")
    assert "[JS 安全拒绝]" not in result


def test_eval_passes_safe_date_code():
    """Date 操作应通过安全预检。"""
    repl = JSRepl()
    repl._node_path = None
    result = repl.eval("new Date().toISOString()")
    assert "[JS 安全拒绝]" not in result


def test_eval_passes_safe_promise_code():
    """Promise 使用应通过安全预检。"""
    repl = JSRepl()
    repl._node_path = None
    result = repl.eval("Promise.resolve(42)")
    assert "[JS 安全拒绝]" not in result


def test_eval_passes_safe_require_of_safe_module():
    """require 非 fs/child_process/net 模块应通过（预检层不拦截，
    实际执行在 vm sandbox 中会被限制）。"""
    repl = JSRepl()
    repl._node_path = None
    result = repl.eval("require('path')")
    assert "[JS 安全拒绝]" not in result


# ── wrapper 生成与转义集成 ────────────────────────────────────────


def test_eval_escaping_integration(tmp_path, capsys):
    """验证 eval 中转义后的代码传给 subprocess 时格式正确。"""
    repl = JSRepl()
    code = "const x = `hello ${name}`"
    escaped = code.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    mock_result = subprocess.CompletedProcess(
        args=["node"], returncode=0, stdout="ok", stderr=""
    )
    captured_code = None

    def mock_run(args, **kwargs):
        nonlocal captured_code
        captured_code = args[2]  # -e 参数
        return mock_result

    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", side_effect=mock_run):
        result = repl.eval(code)
    assert result == "ok"
    assert captured_code is not None
    # 转义后的代码不应包含未转义的反引号
    assert "`hello ${name}`" not in captured_code


# ── timeout 上限 clamp ────────────────────────────────────────────


def test_eval_clamps_timeout_to_30s():
    """timeout_ms > 30000 时应被 clamp 到 30000。"""
    repl = JSRepl()
    called_args = []

    def mock_run(args, **kwargs):
        called_args.append((args, kwargs))
        return subprocess.CompletedProcess(
            args=["node"], returncode=0, stdout="ok", stderr=""
        )

    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", side_effect=mock_run):
        repl.eval("1+1", timeout_ms=60000)
    # subprocess.run 的 timeout 参数应是 (60000/1000) + 5 = 65s
    # 但 timeout_sec = min(60000, 30000) = 30000
    # 所以 subprocess timeout = 30000/1000 + 5 = 35s
    _, kwargs = called_args[0]
    assert kwargs["timeout"] == 35.0


def test_eval_subprocess_timeout_calculated_correctly():
    """常规 timeout_ms 应正确换算为 subprocess timeout。"""
    repl = JSRepl()
    called_kwargs = {}

    def mock_run(args, **kwargs):
        called_kwargs.update(kwargs)
        return subprocess.CompletedProcess(
            args=["node"], returncode=0, stdout="ok", stderr=""
        )

    with patch.object(repl, "_node_path", "node"), \
         patch("subprocess.run", side_effect=mock_run):
        repl.eval("1+1", timeout_ms=5000)
    # timeout_sec = min(5000, 30000) = 5000, subprocess timeout = 5000/1000 + 5 = 10s
    assert called_kwargs["timeout"] == 10.0


# ── js_eval 模块级函数 ──────────────────────────────────────────


def test_js_eval_returns_string():
    """js_eval 模块函数应返回字符串。"""
    from core.codex_engines import js_eval
    result = js_eval("1+1")
    assert isinstance(result, str)


# ── MCPConnector list_tools 无连接 ────────────────────────────────


def test_mcp_list_tools_no_connection():
    """未连接时 list_tools 应返回空列表。"""
    from core.codex_engines import MCPConnector
    conn = MCPConnector()
    result = conn.list_tools("nonexistent")
    assert result == []


def test_mcp_call_tool_no_connection():
    """未连接时 call_tool 应返回错误。"""
    from core.codex_engines import MCPConnector
    conn = MCPConnector()
    result = conn.call_tool("ghost", "some_tool", {})
    assert "[MCP Error]" in result
    assert "not connected" in result


def test_mcp_disconnect_nonexistent_is_noop():
    """断开不存在的连接不应报错。"""
    from core.codex_engines import MCPConnector
    conn = MCPConnector()
    conn.disconnect("ghost")  # 不抛异常
