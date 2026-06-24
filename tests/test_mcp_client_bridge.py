"""MCP Client Bridge 全链路测试 (P-5: 零测试模块优先覆盖)。

验证 4 个 MCP bridge executor:
  - mcp_list_servers / mcp_list_tools / mcp_call_tool / mcp_read_resource

覆盖路径:
  - executor 函数 → get_mcp_client() → MCPClient 方法调用
  - 空配置 / 未配置 server / 未连接 / 已连接
  - JSON arguments 解析错误
  - 返回值格式一致性 (JSON 字符串)
  - 无真实 MCP server 子进程 (全 mock)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.mcp_client import (
    MCP_TOOL_DEFS,
    MCP_EXECUTOR_MAP,
    _exec_mcp_list_servers,
    _exec_mcp_list_tools,
    _exec_mcp_call_tool,
    _exec_mcp_read_resource,
)


# ════════════════════════════════════════════════════════════
#  基础结构验证
# ════════════════════════════════════════════════════════════

class TestMCPBridgeDefinitions:
    """MCP_TOOL_DEFS + MCP_EXECUTOR_MAP 结构完整性。"""

    def test_four_tools_defined(self):
        assert len(MCP_TOOL_DEFS) == 4

    def test_tool_def_has_required_fields(self):
        for td in MCP_TOOL_DEFS:
            fn = td["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert fn["name"].startswith("mcp_")

    def test_executor_map_keys_match_defs(self):
        def_names = {d["function"]["name"] for d in MCP_TOOL_DEFS}
        assert set(MCP_EXECUTOR_MAP.keys()) == def_names

    def test_executor_map_values_are_callable(self):
        for name, fn in MCP_EXECUTOR_MAP.items():
            assert callable(fn), f"{name} executor not callable"

    def test_mcp_call_tool_required_params(self):
        """mcp_call_tool 需要 server_name + tool_name, arguments 可选。"""
        call_def = next(d for d in MCP_TOOL_DEFS
                        if d["function"]["name"] == "mcp_call_tool")
        required = call_def["function"]["parameters"].get("required", [])
        assert "server_name" in required
        assert "tool_name" in required
        assert "arguments" not in required  # 可选

    def test_mcp_read_resource_required_params(self):
        """mcp_read_resource 需要 server_name + uri。"""
        read_def = next(d for d in MCP_TOOL_DEFS
                         if d["function"]["name"] == "mcp_read_resource")
        required = read_def["function"]["parameters"].get("required", [])
        assert "server_name" in required
        assert "uri" in required


# ════════════════════════════════════════════════════════════
#  _exec_mcp_list_servers
# ════════════════════════════════════════════════════════════

class TestExecListServers:
    """mcp_list_servers executor: 空/非空配置。"""

    @patch("core.mcp_client.get_mcp_client")
    def test_empty_config(self, mock_get):
        mock_client = MagicMock()
        mock_client.list_servers.return_value = []
        mock_get.return_value = mock_client
        result = _exec_mcp_list_servers()
        data = json.loads(result)
        assert data == []

    @patch("core.mcp_client.get_mcp_client")
    def test_with_servers(self, mock_get):
        mock_client = MagicMock()
        mock_client.list_servers.return_value = [
            {"name": "claude", "command": "claude", "enabled": True},
            {"name": "codex", "command": "npx", "enabled": False},
        ]
        mock_get.return_value = mock_client
        result = _exec_mcp_list_servers()
        data = json.loads(result)
        assert len(data) == 2
        assert data[0]["name"] == "claude"

    @patch("core.mcp_client.get_mcp_client")
    def test_returns_json_string(self, mock_get):
        mock_client = MagicMock()
        mock_client.list_servers.return_value = [{"name": "x"}]
        mock_get.return_value = mock_client
        result = _exec_mcp_list_servers()
        # 必须是可 parse 的 JSON 字符串
        parsed = json.loads(result)
        assert isinstance(parsed, list)


# ════════════════════════════════════════════════════════════
#  _exec_mcp_list_tools
# ════════════════════════════════════════════════════════════

class TestExecListTools:
    """mcp_list_tools executor: 未配置 / auto-connect 失败 / 已连接。"""

    @patch("core.mcp_client.get_mcp_client")
    def test_server_not_configured(self, mock_get):
        """未配置的 server → connect 返回 error。"""
        mock_client = MagicMock()
        mock_client._processes = {}
        mock_client.connect.return_value = {"error": "Server 'foo' not configured"}
        mock_get.return_value = mock_client
        result = _exec_mcp_list_tools(server_name="foo")
        data = json.loads(result)
        assert "error" in data

    @patch("core.mcp_client.get_mcp_client")
    def test_auto_connect_failure(self, mock_get):
        """auto-connect 失败 → 直接返回 error, 不 crash。"""
        mock_client = MagicMock()
        mock_client._processes = {}
        mock_client.connect.return_value = {"error": "Failed to start"}
        mock_get.return_value = mock_client
        result = _exec_mcp_list_tools(server_name="broken")
        data = json.loads(result)
        assert "error" in data

    @patch("core.mcp_client.get_mcp_client")
    def test_already_connected(self, mock_get):
        """已连接的 server → 不调 connect, 直接 list_tools。"""
        mock_client = MagicMock()
        mock_client._processes = {"claude": MagicMock()}
        mock_client.list_tools.return_value = [
            {"name": "read_file", "description": "read a file"}
        ]
        mock_get.return_value = mock_client
        result = _exec_mcp_list_tools(server_name="claude")
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["name"] == "read_file"
        mock_client.connect.assert_not_called()

    @patch("core.mcp_client.get_mcp_client")
    def test_auto_connect_success(self, mock_get):
        """首次调用自动连接 → list_tools。"""
        mock_client = MagicMock()
        mock_client._processes = {}
        mock_client.connect.return_value = {"status": "connected"}
        mock_client.list_tools.return_value = []
        mock_get.return_value = mock_client
        result = _exec_mcp_list_tools(server_name="claude")
        data = json.loads(result)
        assert isinstance(data, list)
        mock_client.connect.assert_called_once_with("claude")


# ════════════════════════════════════════════════════════════
#  _exec_mcp_call_tool
# ════════════════════════════════════════════════════════════

class TestExecCallTool:
    """mcp_call_tool executor: JSON 解析 / auto-connect / 错误路径。"""

    @patch("core.mcp_client.get_mcp_client")
    def test_invalid_json_arguments(self, mock_get):
        """arguments 不是合法 JSON → 返回解析错误。"""
        mock_client = MagicMock()
        mock_client._processes = {"claude": MagicMock()}
        mock_get.return_value = mock_client
        result = _exec_mcp_call_tool(
            server_name="claude",
            tool_name="read_file",
            arguments="not-json{{{",
        )
        data = json.loads(result)
        assert "error" in data
        assert "Invalid JSON" in data["error"]

    @patch("core.mcp_client.get_mcp_client")
    def test_empty_arguments_ok(self, mock_get):
        """arguments 为空字符串 → 传 None 给 call_tool。"""
        mock_client = MagicMock()
        mock_client._processes = {"claude": MagicMock()}
        mock_client.call_tool.return_value = {"result": "ok"}
        mock_get.return_value = mock_client
        result = _exec_mcp_call_tool(
            server_name="claude",
            tool_name="ping",
        )
        data = json.loads(result)
        # call_tool 被调用, arguments 应为 None
        mock_client.call_tool.assert_called_once()
        call_args = mock_client.call_tool.call_args
        assert call_args[0][2] is None  # arguments=None

    @patch("core.mcp_client.get_mcp_client")
    def test_valid_json_arguments(self, mock_get):
        """合法 JSON arguments → 正确解析并传给 call_tool。"""
        mock_client = MagicMock()
        mock_client._processes = {"claude": MagicMock()}
        mock_client.call_tool.return_value = {"result": "hello"}
        mock_get.return_value = mock_client
        result = _exec_mcp_call_tool(
            server_name="claude",
            tool_name="greet",
            arguments='{"name": "world"}',
        )
        data = json.loads(result)
        assert data["result"] == "hello"
        call_args = mock_client.call_tool.call_args
        assert call_args[0][2] == {"name": "world"}

    @patch("core.mcp_client.get_mcp_client")
    def test_auto_connect_on_first_call(self, mock_get):
        """首次调用 → auto-connect → call_tool。"""
        mock_client = MagicMock()
        mock_client._processes = {}
        mock_client.connect.return_value = {"status": "connected"}
        mock_client.call_tool.return_value = {"result": "done"}
        mock_get.return_value = mock_client
        result = _exec_mcp_call_tool(
            server_name="claude",
            tool_name="ping",
        )
        mock_client.connect.assert_called_once_with("claude")
        mock_client.call_tool.assert_called_once()

    @patch("core.mcp_client.get_mcp_client")
    def test_connect_failure(self, mock_get):
        """auto-connect 失败 → 返回 error, 不 crash。"""
        mock_client = MagicMock()
        mock_client._processes = {}
        mock_client.connect.return_value = {"error": "timeout"}
        mock_get.return_value = mock_client
        result = _exec_mcp_call_tool(
            server_name="claude",
            tool_name="ping",
        )
        data = json.loads(result)
        assert "error" in data
        mock_client.call_tool.assert_not_called()


# ════════════════════════════════════════════════════════════
#  _exec_mcp_read_resource
# ════════════════════════════════════════════════════════════

class TestExecReadResource:
    """mcp_read_resource executor: auto-connect / 未连接 / 空参。"""

    @patch("core.mcp_client.get_mcp_client")
    def test_auto_connect_and_read(self, mock_get):
        """首次调用 → auto-connect → read_resource。"""
        mock_client = MagicMock()
        mock_client._processes = {}
        mock_client.connect.return_value = {"status": "connected"}
        mock_client.read_resource.return_value = {"contents": "hello"}
        mock_get.return_value = mock_client
        result = _exec_mcp_read_resource(
            server_name="claude",
            uri="file:///tmp/test.txt",
        )
        data = json.loads(result)
        assert data["contents"] == "hello"
        mock_client.connect.assert_called_once_with("claude")
        mock_client.read_resource.assert_called_once_with("claude", "file:///tmp/test.txt")

    @patch("core.mcp_client.get_mcp_client")
    def test_already_connected(self, mock_get):
        """已连接 → 不调 connect, 直接 read。"""
        mock_client = MagicMock()
        mock_client._processes = {"claude": MagicMock()}
        mock_client.read_resource.return_value = {"contents": "cached"}
        mock_get.return_value = mock_client
        result = _exec_mcp_read_resource(
            server_name="claude",
            uri="file:///x",
        )
        data = json.loads(result)
        assert data["contents"] == "cached"
        mock_client.connect.assert_not_called()

    @patch("core.mcp_client.get_mcp_client")
    def test_connect_failure(self, mock_get):
        """auto-connect 失败 → 返回 error。"""
        mock_client = MagicMock()
        mock_client._processes = {}
        mock_client.connect.return_value = {"error": "not configured"}
        mock_get.return_value = mock_client
        result = _exec_mcp_read_resource(
            server_name="missing",
            uri="x://y",
        )
        data = json.loads(result)
        assert "error" in data


# ════════════════════════════════════════════════════════════
#  通用: executor 与 ToolRegistry 集成
# ════════════════════════════════════════════════════════════

class TestMCPBridgeRegistryIntegration:
    """验证 MCP bridge executor 在 ToolRegistry 中的注册和执行。"""

    @patch("core.mcp_client.get_mcp_client")
    def test_mcp_tools_registered_when_mcp_true(self, mock_get):
        """load(mcp=True) 后 4 个 MCP 工具都注册。"""
        mock_get.return_value = MagicMock(
            list_servers=lambda: [],
            _processes={},
        )
        from core.tools import ToolRegistry
        reg = ToolRegistry()
        reg.load(mcp=True)
        for name in MCP_EXECUTOR_MAP:
            assert reg.has(name), f"{name} should be registered with mcp=True"

    def test_mcp_tools_not_registered_when_mcp_false(self):
        """load(mcp=False) 后 MCP 工具不在注册表。"""
        from core.tools import ToolRegistry
        reg = ToolRegistry()
        reg.load(mcp=False)
        for name in MCP_EXECUTOR_MAP:
            assert not reg.has(name), f"{name} should NOT be registered with mcp=False"

    @patch("core.mcp_client.get_mcp_client")
    def test_execute_list_servers_through_registry(self, mock_get):
        """通过 registry.execute() 调用 mcp_list_servers。"""
        mock_client = MagicMock()
        mock_client.list_servers.return_value = [{"name": "test"}]
        mock_get.return_value = mock_client
        from core.tools import ToolRegistry
        reg = ToolRegistry()
        reg.load(mcp=True)
        result = reg.execute("mcp_list_servers", {})
        data = json.loads(result)
        assert isinstance(data, list)
