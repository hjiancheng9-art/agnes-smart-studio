"""MCPClient 类全方法测试 (P-5: 零/低测试模块优先覆盖)。

补充 test_mcp_client_bridge.py 只覆盖 executor 函数的缺口，
这里覆盖 MCPClient 类本身的所有公开方法 + 私有通信协议：

    - __init__ / _cleanup_all (atexit 注册)
    - add_server / remove_server / list_servers (注册表)
    - connect (含 disabled / 重复 / Popen 失败 / 立即退出 / init 失败)
    - disconnect (含未连接)
    - list_tools / call_tool / list_resources / read_resource (含未连接)
    - _send_request (含所有错误分支: 已退出 / stdin closed / stdout closed /
      timeout / 空响应 / 非法 JSON / jsonrpc 版本错 / id 不匹配)
    - _send_notification (stdin closed / OSError 吞掉)
    - _terminate_process (terminate 失败 → kill fallback / 双重失败)
    - _save_config / _load_config (持久化 + 加载空 / 损坏文件)
    - get_mcp_client (单例)

设计原则：
    - 全部 mock subprocess.Popen，不起真实子进程
    - CONFIG_PATH 重定向到 tmp_path，不污染 output/mcp_servers.json
    - 每个测试独立构造 MCPClient 实例，避免全局状态污染
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import mcp_client as mcp_mod
from core.mcp_client import (
    MCPClient,
    MCPServerConfig,
    get_mcp_client,
)


# ════════════════════════════════════════════════════════════
#  Helpers / Fixtures
# ════════════════════════════════════════════════════════════


def _make_response(req_id: int, result=None, error=None) -> str:
    """Build a valid JSON-RPC 2.0 response line."""
    msg = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result if result is not None else {}
    return json.dumps(msg) + "\n"


class _FakeStream:
    """模拟子进程 stdin/stdout/stderr，可控的读写流。

    stdout 模式：根据收到的请求动态构造匹配 id 的响应（避免 _next_id 累积导致不匹配），
    或返回预设的固定响应序列。
    """

    def __init__(self, responses=None, read_data="", auto_match_id=False, result=None, error=None, fail_on_write=False):
        self._responses = list(responses) if responses else []
        self._written = []
        self._read_buf = io.StringIO(read_data)
        self._closed = False
        self._auto_match_id = auto_match_id
        self._default_result = result
        self._default_error = error
        self._fail_on_write = fail_on_write

    def write(self, data):
        if self._fail_on_write:
            raise OSError("broken pipe")
        self._written.append(data)

    def flush(self):
        pass

    def readline(self):
        if self._auto_match_id:
            # 从最后一次写入的请求里提取 id，构造匹配响应
            req = json.loads(self._written[-1])
            return _make_response(req["id"], result=self._default_result, error=self._default_error)
        if self._responses:
            return self._responses.pop(0)
        return ""

    def read(self):
        return self._read_buf.read()

    def close(self):
        self._closed = True


def _make_fake_proc(
    *,
    returncode=None,
    responses=None,
    stderr_data="",
    stdin=None,
    stdout=None,
    stderr=None,
    auto_match_id=False,
    result=None,
    error=None,
) -> MagicMock:
    """构造一个模拟的 Popen 对象。

    auto_match_id=True 时，stdout 会根据 stdin 写入的请求 id 动态返回匹配响应，
    避免 client._next_id 累积导致 response id mismatch。

    Note: 不使用 spec=subprocess.Popen，因为测试中 @patch 会替换该名字导致 spec 失败。
    """
    proc = MagicMock()
    proc.returncode = returncode
    shared_stream = _FakeStream(
        responses=responses,
        read_data=stderr_data,
        auto_match_id=auto_match_id,
        result=result,
        error=error,
    )
    proc.stdin = stdin if stdin is not None else shared_stream
    proc.stdout = stdout if stdout is not None else shared_stream
    proc.stderr = stderr if stderr is not None else _FakeStream(read_data=stderr_data)
    proc.poll.return_value = returncode
    proc.wait.return_value = returncode if returncode is not None else 0
    proc.terminate.return_value = None
    proc.kill.return_value = None
    return proc


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """重定向 CONFIG_PATH 到 tmp_path，避免污染真实 output/mcp_servers.json。"""
    monkeypatch.setattr(mcp_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(MCPClient, "CONFIG_PATH", tmp_path / "mcp_servers.json")
    # 重置单例
    monkeypatch.setattr(mcp_mod, "_mcp_client", None)
    yield


@pytest.fixture
def client():
    """Fresh MCPClient with empty config (no real subprocess)."""
    with patch.object(MCPClient, "_load_config", return_value=None):
        c = MCPClient()
    return c


# ════════════════════════════════════════════════════════════
#  MCPServerConfig dataclass
# ════════════════════════════════════════════════════════════


class TestMCPServerConfig:
    def test_defaults(self):
        cfg = MCPServerConfig(name="x", command="python")
        assert cfg.name == "x"
        assert cfg.command == "python"
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.enabled is True

    def test_custom_values(self):
        cfg = MCPServerConfig(
            name="s", command="node", args=["--foo"], env={"K": "V"}, enabled=False
        )
        assert cfg.args == ["--foo"]
        assert cfg.env == {"K": "V"}
        assert cfg.enabled is False


# ════════════════════════════════════════════════════════════
#  Server Registry: add_server / remove_server / list_servers
# ════════════════════════════════════════════════════════════


class TestServerRegistry:
    def test_add_server_returns_ok(self, client):
        result = client.add_server("claude", "claude", args=["--mcp"], env={"K": "V"})
        assert result["status"] == "ok"
        assert result["server"]["name"] == "claude"
        assert "claude" in client._servers

    def test_add_server_duplicate_returns_error(self, client):
        client.add_server("claude", "claude")
        result = client.add_server("claude", "claude")
        assert "error" in result
        assert "already exists" in result["error"]

    def test_add_server_persists_config(self, client):
        client.add_server("srv", "python", args=["m.py"])
        assert MCPClient.CONFIG_PATH.exists()
        data = json.loads(MCPClient.CONFIG_PATH.read_text(encoding="utf-8"))
        assert any(s["name"] == "srv" for s in data["servers"])

    def test_remove_server_existing(self, client):
        client.add_server("srv", "python")
        assert client.remove_server("srv") is True
        assert "srv" not in client._servers

    def test_remove_server_nonexistent(self, client):
        assert client.remove_server("nope") is False

    def test_remove_server_disconnects_if_connected(self, client):
        client.add_server("srv", "python")
        # Fake a connected process
        fake_proc = _make_fake_proc()
        client._processes["srv"] = fake_proc
        with patch.object(client, "_terminate_process") as mock_term:
            assert client.remove_server("srv") is True
            mock_term.assert_called_once_with("srv", fake_proc)
        assert "srv" not in client._processes

    def test_list_servers_empty(self, client):
        assert client.list_servers() == []

    def test_list_servers_returns_dicts(self, client):
        client.add_server("a", "python")
        client.add_server("b", "node")
        servers = client.list_servers()
        assert len(servers) == 2
        names = [s["name"] for s in servers]
        assert "a" in names and "b" in names


# ════════════════════════════════════════════════════════════
#  connect
# ════════════════════════════════════════════════════════════


class TestConnect:
    def test_connect_unknown_server(self, client):
        result = client.connect("nonexistent")
        assert "error" in result
        assert "not configured" in result["error"]

    def test_connect_disabled_server(self, client):
        client.add_server("srv", "python")
        client._servers["srv"].enabled = False
        result = client.connect("srv")
        assert "error" in result
        assert "disabled" in result["error"]

    def test_connect_already_connected(self, client):
        client.add_server("srv", "python")
        client._processes["srv"] = _make_fake_proc()
        result = client.connect("srv")
        assert "error" in result
        assert "already connected" in result["error"]

    @patch("core.mcp_client.subprocess.Popen")
    def test_connect_popen_failure(self, mock_popen, client):
        client.add_server("srv", "python")
        mock_popen.side_effect = OSError("no such command")
        result = client.connect("srv")
        assert "error" in result
        assert "Failed to start" in result["error"]

    @patch("core.mcp_client.subprocess.Popen")
    def test_connect_immediate_exit(self, mock_popen, client):
        client.add_server("srv", "python")
        # Process exits immediately — build proc BEFORE patch replaces Popen class
        # (mock spec can't be a Mock). We bypass _make_fake_proc's spec=subprocess.Popen.
        proc = MagicMock()
        proc.returncode = 1
        proc.poll.return_value = 1
        proc.stdin = _FakeStream()
        proc.stdout = _FakeStream()
        proc.stderr = _FakeStream(read_data="boom")
        mock_popen.return_value = proc
        result = client.connect("srv")
        assert "error" in result
        assert "exited immediately" in result["error"]
        assert "boom" in result["error"]

    @patch("core.mcp_client.subprocess.Popen")
    def test_connect_init_failure_cleans_up(self, mock_popen, client):
        client.add_server("srv", "python")
        # init response returns error
        proc = _make_fake_proc(auto_match_id=True, error={"code": -1, "message": "nope"})
        mock_popen.return_value = proc
        with patch.object(client, "_terminate_process") as mock_term:
            result = client.connect("srv")
            assert "error" in result
            assert "Initialize failed" in result["error"]
            # init 失败 → 进程被 terminate（源码行为：_processes 条目保留但进程被终止）
            mock_term.assert_called_once_with("srv", proc)

    @patch("core.mcp_client.subprocess.Popen")
    def test_connect_success(self, mock_popen, client):
        client.add_server("srv", "python")
        init_resp = {"capabilities": {"tools": True}}
        proc = _make_fake_proc(auto_match_id=True, result=init_resp)
        mock_popen.return_value = proc
        with patch.object(client, "_send_notification") as mock_notify:
            result = client.connect("srv")
            assert result["status"] == "connected"
            assert result["name"] == "srv"
            assert result["capabilities"] == init_resp
            mock_notify.assert_called_once_with(proc, "notifications/initialized")
        assert "srv" in client._processes

    @patch("core.mcp_client.subprocess.Popen")
    def test_connect_passes_env_override(self, mock_popen, client):
        client.add_server("srv", "python", env={"CUSTOM_VAR": "xyz"})
        proc = _make_fake_proc(auto_match_id=True, result={"capabilities": {}})
        mock_popen.return_value = proc
        client.connect("srv")
        # Verify env passed to Popen includes our override
        _, kwargs = mock_popen.call_args
        assert kwargs["env"]["CUSTOM_VAR"] == "xyz"


# ════════════════════════════════════════════════════════════
#  disconnect
# ════════════════════════════════════════════════════════════


class TestDisconnect:
    def test_disconnect_not_connected(self, client):
        result = client.disconnect("srv")
        assert "error" in result
        assert "not connected" in result["error"]

    def test_disconnect_connected(self, client):
        proc = _make_fake_proc()
        client._processes["srv"] = proc
        with patch.object(client, "_terminate_process") as mock_term:
            result = client.disconnect("srv")
            assert result["status"] == "disconnected"
            assert result["name"] == "srv"
            mock_term.assert_called_once_with("srv", proc)
        assert "srv" not in client._processes


# ════════════════════════════════════════════════════════════
#  list_tools / call_tool / list_resources / read_resource
# ════════════════════════════════════════════════════════════


class TestToolResourceOps:
    def test_list_tools_not_connected(self, client):
        result = client.list_tools("srv")
        assert isinstance(result, list)
        assert "error" in result[0]

    def test_list_tools_success(self, client):
        proc = _make_fake_proc(auto_match_id=True, result={"tools": [{"name": "foo"}]})
        client._processes["srv"] = proc
        result = client.list_tools("srv")
        assert result == [{"name": "foo"}]

    def test_list_tools_rpc_error(self, client):
        proc = _make_fake_proc(auto_match_id=True, error={"message": "denied"})
        client._processes["srv"] = proc
        result = client.list_tools("srv")
        assert isinstance(result, list)
        assert "error" in result[0]

    def test_call_tool_not_connected(self, client):
        result = client.call_tool("srv", "foo")
        assert "error" in result

    def test_call_tool_success(self, client):
        proc = _make_fake_proc(auto_match_id=True, result={"content": "hello"})
        client._processes["srv"] = proc
        result = client.call_tool("srv", "foo", {"x": 1})
        assert result == {"content": "hello"}

    def test_call_tool_no_arguments(self, client):
        proc = _make_fake_proc(auto_match_id=True, result={"ok": True})
        client._processes["srv"] = proc
        client.call_tool("srv", "ping")
        # Verify request was sent with just name (no arguments key)
        written = proc.stdin._written[0]
        parsed = json.loads(written)
        assert parsed["method"] == "tools/call"
        assert parsed["params"] == {"name": "ping"}

    def test_call_tool_rpc_error(self, client):
        proc = _make_fake_proc(auto_match_id=True, error={"message": "bad tool"})
        client._processes["srv"] = proc
        result = client.call_tool("srv", "foo")
        assert "error" in result

    def test_list_resources_not_connected(self, client):
        result = client.list_resources("srv")
        assert isinstance(result, list)
        assert "error" in result[0]

    def test_list_resources_success(self, client):
        proc = _make_fake_proc(auto_match_id=True, result={"resources": [{"uri": "file://x"}]})
        client._processes["srv"] = proc
        result = client.list_resources("srv")
        assert result == [{"uri": "file://x"}]

    def test_list_resources_rpc_error(self, client):
        proc = _make_fake_proc(auto_match_id=True, error={"message": "no"})
        client._processes["srv"] = proc
        result = client.list_resources("srv")
        assert isinstance(result, list)
        assert "error" in result[0]

    def test_read_resource_not_connected(self, client):
        result = client.read_resource("srv", "file://x")
        assert "error" in result

    def test_read_resource_success(self, client):
        proc = _make_fake_proc(auto_match_id=True, result={"contents": "data"})
        client._processes["srv"] = proc
        result = client.read_resource("srv", "file://x")
        assert result == {"contents": "data"}
        # Verify request had uri
        written = proc.stdin._written[0]
        parsed = json.loads(written)
        assert parsed["params"] == {"uri": "file://x"}

    def test_read_resource_rpc_error(self, client):
        proc = _make_fake_proc(auto_match_id=True, error={"message": "nope"})
        client._processes["srv"] = proc
        result = client.read_resource("srv", "file://x")
        assert "error" in result


# ════════════════════════════════════════════════════════════
#  _send_request — 所有错误分支
# ════════════════════════════════════════════════════════════


class TestSendRequestErrors:
    def test_process_already_exited(self, client):
        proc = _make_fake_proc(returncode=2)
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "exited with code 2" in result["error"]["message"]

    def test_process_already_exited_none_returncode(self, client):
        """returncode 非空字符串场景（罕见但覆盖分支）。"""
        proc = _make_fake_proc(returncode=-1)
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "exited with code -1" in result["error"]["message"]

    def test_write_to_closed_stdin_returns_error(self, client):
        """stdin is None → write failed."""
        proc = _make_fake_proc()
        proc.stdin = None
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "stdin is closed" in result["error"]["message"]

    def test_closed_stdout_returns_error(self, client):
        proc = _make_fake_proc()
        proc.stdout = None
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "stdout is closed" in result["error"]["message"]

    def test_empty_response(self, client):
        """readline 返回空字符串 + 进程仍在运行 → Empty response。"""
        proc = _make_fake_proc(responses=[""])  # empty response, returncode=None
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "Empty response" in result["error"]["message"]

    def test_empty_response_with_exited_process(self, client):
        """空响应 + 进程已退出 → 显示 exit code + stderr。"""
        proc = _make_fake_proc(returncode=3, responses=[""], stderr_data="fatal error")
        # returncode 非 None，所以会被早退分支拦截 → 但我们需要走 readline 分支
        # 先让 returncode=None 让写入成功，再在读取时改为 3
        proc.returncode = None
        proc.stderr = _FakeStream(read_data="fatal error")

        # 用一个特殊的 proc：readline 后 returncode 变成 3
        class _ExitAfterRead(_FakeStream):
            def __init__(self, parent_proc):
                super().__init__()
                self._parent = parent_proc

            def readline(self):
                self._parent.returncode = 3  # 进程在读后退出
                return ""

        proc.stdout = _ExitAfterRead(proc)
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "Server exited" in result["error"]["message"]
        assert "fatal error" in result["error"]["message"]

    def test_invalid_json_response(self, client):
        proc = _make_fake_proc(responses=["not-a-json-line\n"])
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "JSON parse error" in result["error"]["message"]

    def test_wrong_jsonrpc_version(self, client):
        bad = json.dumps({"jsonrpc": "1.0", "id": 1, "result": {}}) + "\n"
        proc = _make_fake_proc(responses=[bad])
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "Invalid JSON-RPC" in result["error"]["message"]

    def test_response_id_mismatch(self, client):
        """响应 id 不匹配 → mismatch error。"""
        # client._next_id 起点是 1
        bad = _make_response(999, result={})  # id=999 不等于 1
        proc = _make_fake_proc(responses=[bad])
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "Response ID mismatch" in result["error"]["message"]

    def test_request_id_increments(self, client):
        """连续两次请求，id 应递增。"""
        proc = _make_fake_proc(
            responses=[
                _make_response(1, result={"a": 1}),
                _make_response(2, result={"b": 2}),
            ]
        )
        r1 = client._send_request(proc, "m1")
        r2 = client._send_request(proc, "m2")
        assert r1.get("result") == {"a": 1}
        assert r2.get("result") == {"b": 2}

    def test_successful_roundtrip(self, client):
        """完整 happy path: 写入 + 读取 + 验证。"""
        resp = _make_response(1, result={"capabilities": {"tools": True}})
        proc = _make_fake_proc(responses=[resp])
        result = client._send_request(proc, "initialize", {"k": "v"})
        assert result["result"] == {"capabilities": {"tools": True}}
        # 验证请求确实被写入 stdin
        written = proc.stdin._written[0]
        parsed = json.loads(written)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["method"] == "initialize"
        assert parsed["params"] == {"k": "v"}

    def test_request_with_no_params(self, client):
        """params=None 时请求不应包含 params 键。"""
        resp = _make_response(1, result={})
        proc = _make_fake_proc(responses=[resp])
        client._send_request(proc, "ping")
        written = proc.stdin._written[0]
        parsed = json.loads(written)
        assert "params" not in parsed

    def test_timeout(self, monkeypatch, client):
        """readline 卡住超时 → timeout error。"""
        # 缩短超时避免真等 30 秒
        monkeypatch.setattr(MCPClient, "REQUEST_TIMEOUT", 0.2)

        class _BlockingStream(_FakeStream):
            def readline(self):
                import time

                time.sleep(1.0)  # 远超 0.2s 超时
                return ""

        proc = _make_fake_proc()
        proc.stdout = _BlockingStream()
        result = client._send_request(proc, "initialize")
        assert "error" in result
        assert "timed out" in result["error"]["message"]


# ════════════════════════════════════════════════════════════
#  _send_notification
# ════════════════════════════════════════════════════════════


class TestSendNotification:
    def test_notification_no_id(self, client):
        proc = _make_fake_proc()
        client._send_notification(proc, "notifications/initialized")
        written = proc.stdin._written[0]
        parsed = json.loads(written)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "notifications/initialized"
        assert "id" not in parsed  # notifications 不带 id

    def test_notification_stdin_none(self, client):
        proc = _make_fake_proc()
        proc.stdin = None
        # 应安静返回，不抛异常
        client._send_notification(proc, "notifications/initialized")

    def test_notification_swallows_oserror(self, client):
        proc = _make_fake_proc()
        # 用会抛 OSError 的 stdin 替换
        proc.stdin = _FakeStream(fail_on_write=True)
        # OSError 被吞掉，不抛异常
        client._send_notification(proc, "notifications/initialized")


# ════════════════════════════════════════════════════════════
#  _terminate_process
# ════════════════════════════════════════════════════════════


class TestTerminateProcess:
    def test_terminate_graceful(self, client):
        proc = _make_fake_proc()
        client._terminate_process("srv", proc)
        proc.terminate.assert_called_once()
        proc.wait.assert_called()

    def test_terminate_times_out_falls_back_to_kill(self, client):
        proc = _make_fake_proc()
        proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=5), 0]
        client._terminate_process("srv", proc)
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()

    def test_terminate_kill_also_times_out(self, client):
        """kill 后 wait 仍超时 → 静默吞掉，不抛。"""
        proc = _make_fake_proc()
        proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="x", timeout=5),
            subprocess.TimeoutExpired(cmd="x", timeout=2),
        ]
        # 不应抛异常
        client._terminate_process("srv", proc)
        proc.kill.assert_called_once()

    def test_terminate_oserror(self, client):
        proc = _make_fake_proc()
        proc.terminate.side_effect = OSError("nope")
        # OSError 被吞
        client._terminate_process("srv", proc)


# ════════════════════════════════════════════════════════════
#  _cleanup_all (atexit)
# ════════════════════════════════════════════════════════════


class TestCleanupAll:
    def test_cleanup_all_terminates_each(self, client):
        p1 = _make_fake_proc()
        p2 = _make_fake_proc()
        client._processes = {"a": p1, "b": p2}
        with patch.object(client, "_terminate_process") as mock_term:
            client._cleanup_all()
            assert mock_term.call_count == 2
            terminated_names = {call.args[0] for call in mock_term.call_args_list}
            assert terminated_names == {"a", "b"}

    def test_cleanup_all_swallows_errors(self, client):
        """_terminate_process 抛异常时不应中断 cleanup。"""
        client._processes = {"a": _make_fake_proc(), "b": _make_fake_proc()}
        with patch.object(client, "_terminate_process", side_effect=subprocess.SubprocessError):
            # 不应抛
            client._cleanup_all()
        # 全部都被尝试清理了
        assert len(client._processes) == 2  # _cleanup_all 不修改字典本身


# ════════════════════════════════════════════════════════════
#  Config Persistence: _save_config / _load_config
# ════════════════════════════════════════════════════════════


class TestConfigPersistence:
    def test_save_and_reload(self, tmp_path):
        """save → 新实例 load 能还原。"""
        with patch.object(MCPClient, "_load_config", return_value=None):
            c1 = MCPClient()
        c1.add_server("srv1", "python", args=["a.py"])
        c1.add_server("srv2", "node", env={"K": "V"})

        # 新实例应该从同一 CONFIG_PATH 加载
        c2 = MCPClient()
        names = {s.name for s in c2._servers.values()}
        assert names == {"srv1", "srv2"}
        assert c2._servers["srv2"].env == {"K": "V"}

    def test_load_nonexistent_config(self):
        """CONFIG_PATH 不存在时 _load_config 静默返回。"""
        # 默认 fixture: CONFIG_PATH 在 tmp_path，不存在
        # 用 spy 包装实例方法，确保真正调用而不是替换
        original = MCPClient._load_config
        call_count = {"n": 0}

        def spy(self):
            call_count["n"] += 1
            return original(self)

        with patch.object(MCPClient, "_load_config", spy):
            c = MCPClient()
            assert call_count["n"] == 1
        assert c._servers == {}

    def test_load_corrupted_config(self, tmp_path):
        """损坏的 config 文件 → 静默忽略，不抛。"""
        MCPClient.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        MCPClient.CONFIG_PATH.write_text("{ this is not valid json", encoding="utf-8")
        # 不应抛
        c = MCPClient()
        assert c._servers == {}

    def test_load_skips_empty_name(self, tmp_path):
        """name 为空的条目被跳过。"""
        MCPClient.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        MCPClient.CONFIG_PATH.write_text(
            json.dumps(
                {
                    "servers": [
                        {"name": "", "command": "python"},  # 跳过
                        {"name": "real", "command": "node"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        c = MCPClient()
        assert set(c._servers.keys()) == {"real"}

    def test_load_uses_defaults_for_missing_fields(self, tmp_path):
        """加载时缺失字段使用 MCPServerConfig 默认值。"""
        MCPClient.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        MCPClient.CONFIG_PATH.write_text(
            json.dumps({"servers": [{"name": "minimal", "command": "python"}]}),
            encoding="utf-8",
        )
        c = MCPClient()
        srv = c._servers["minimal"]
        assert srv.args == []
        assert srv.env == {}
        assert srv.enabled is True  # default


# ════════════════════════════════════════════════════════════
#  get_mcp_client singleton
# ════════════════════════════════════════════════════════════


class TestGetMcpClient:
    def test_singleton_returns_same_instance(self):
        c1 = get_mcp_client()
        c2 = get_mcp_client()
        assert c1 is c2

    def test_singleton_is_mcpclient(self):
        assert isinstance(get_mcp_client(), MCPClient)
