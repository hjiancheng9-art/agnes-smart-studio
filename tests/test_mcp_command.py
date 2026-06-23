"""Tests for /mcp CLI command and MCP bridge tool injection.

验证：
1. /mcp 命令注册到 COMMANDS 并正确路由到 _chat_mcp handler
2. ToolRegistry.load(mcp=True) 注入 4 个 MCP bridge tools
3. get_registry() 单例初始加载自带 mcp=True
4. _chat_mcp handler 对各子命令的正确响应
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── 命令注册 ──────────────────────────────────────────────────


class TestMCPCommandRegistration:
    """/mcp 命令应注册到 COMMANDS 并正确路由。"""

    def test_mcp_in_commands(self):
        from core.commands import get_all
        keys = [c.key for c in get_all()]
        assert "mcp" in keys

    def test_mcp_command_def(self):
        from core.commands import get_all
        cmd = next(c for c in get_all() if c.key == "mcp")
        assert cmd.name == "/mcp"
        assert cmd.handler == "_chat_mcp"
        assert cmd.category == "诊断配置"

    def test_mcp_in_dispatch_table(self):
        from core.commands import build_dispatch_table
        table = build_dispatch_table()
        assert "mcp" in table
        handler, cmd_def = table["mcp"]
        assert handler == "_chat_mcp"

    def test_mcp_handler_reachable_on_cli(self):
        from ui.cli import AgnesCLI
        assert hasattr(AgnesCLI, "_chat_mcp")

    def test_total_command_count_includes_mcp(self):
        from core.commands import get_all
        # /mcp 使总数至少 33
        assert len(get_all()) >= 33


# ── ToolRegistry 注入 ───────────────────────────────────────────


class TestMCPToolInjection:
    """ToolRegistry.load(mcp=True) 应注入 4 个 MCP bridge tools。"""

    def test_mcp_tools_injected_with_flag(self):
        from core.tools import ToolRegistry
        reg = ToolRegistry()
        reg.load(mcp=True)
        names = reg.tool_names
        for expected in ("mcp_list_servers", "mcp_list_tools",
                        "mcp_call_tool", "mcp_read_resource"):
            assert expected in names, f"{expected} missing from tool_names"

    def test_mcp_tools_not_injected_without_flag(self):
        from core.tools import ToolRegistry
        reg = ToolRegistry()
        reg.load(mcp=False)
        names = reg.tool_names
        for unexpected in ("mcp_list_servers", "mcp_list_tools",
                           "mcp_call_tool", "mcp_read_resource"):
            assert unexpected not in names, \
                f"{unexpected} should not be present without mcp=True"

    def test_mcp_executors_registered(self):
        from core.tools import ToolRegistry
        reg = ToolRegistry()
        reg.load(mcp=True)
        # 每个 MCP tool 都必须有 executor
        for name in ("mcp_list_servers", "mcp_list_tools",
                     "mcp_call_tool", "mcp_read_resource"):
            assert name in reg._executors, f"executor missing for {name}"

    def test_mcp_tool_modules_tracked(self):
        from core.tools import ToolRegistry
        reg = ToolRegistry()
        reg.load(mcp=True)
        for name in ("mcp_list_servers", "mcp_list_tools",
                     "mcp_call_tool", "mcp_read_resource"):
            assert reg._tool_modules.get(name) == "core.mcp_client", \
                f"module tracking wrong for {name}"


class TestGetRegistryMCP:
    """get_registry() 单例初始加载应自带 mcp=True。"""

    def test_get_registry_singleton_includes_mcp_tools(self):
        """全局单例应包含 MCP bridge tools。"""
        # 先清理单例以获得干净状态
        import core.tools as tools_mod
        tools_mod._registry = None
        try:
            reg = tools_mod.get_registry()
            names = reg.tool_names
            for expected in ("mcp_list_servers", "mcp_list_tools",
                            "mcp_call_tool", "mcp_read_resource"):
                assert expected in names, \
                    f"{expected} missing from get_registry() singleton"
        finally:
            # 恢复单例（下次 load 时会自动处理）
            tools_mod._registry = None

    def test_reload_registry_preserves_mcp(self):
        """reload_registry() 重建后应仍包含 MCP tools。"""
        import core.tools as tools_mod
        tools_mod._registry = None
        try:
            reg = tools_mod.reload_registry()
            names = reg.tool_names
            assert "mcp_call_tool" in names
        finally:
            tools_mod._registry = None


# ── _chat_mcp handler 子命令 ──────────────────────────────────


class TestChatMCPHandler:
    """_chat_mcp handler 各子命令的正确响应。"""

    def _make_cli_and_session(self):
        """构造 AgnesCLI 和 mock session。"""
        from ui.cli import AgnesCLI

        cli = AgnesCLI.__new__(AgnesCLI)
        # mock 掉 _prompt_user / print_mode_banner 避免真实交互
        cli._prompt_user = MagicMock(return_value="")
        cli.print_mode_banner = MagicMock()

        # mock session（不需要真实 API）
        session = MagicMock()
        session.code_mode = False
        session.agent_mode = False
        session.active_skill = ""
        session.mode = "chat"
        return cli, session

    def test_mcp_list_empty(self):
        """空服务器列表时应显示提示信息。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.list_servers.return_value = []

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "")
        mock_client.list_servers.assert_called_once()

    def test_mcp_list_with_servers(self):
        """有服务器时应正常列出。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.list_servers.return_value = [
            {"name": "claude", "command": "claude-code", "args": ["mcp"],
             "enabled": True},
            {"name": "fs", "command": "node", "args": ["/server.js"],
             "enabled": True},
        ]
        mock_client._processes = {}  # 未连接

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "list")
        mock_client.list_servers.assert_called_once()

    def test_mcp_add_success(self):
        """add 子命令应调用 client.add_server。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.add_server.return_value = {"status": "ok", "server": {}}

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "add claude -- claude-code mcp")

        mock_client.add_server.assert_called_once_with(
            name="claude", command="claude-code",
            args=["mcp"],
        )

    def test_mcp_add_duplicate(self):
        """add 重复名称时应显示警告。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.add_server.return_value = {"error": "Server 'claude' already exists"}

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "add claude -- claude-code mcp")

        mock_client.add_server.assert_called_once()

    def test_mcp_add_missing_separator(self):
        """add 缺少 -- 分隔符时应显示用法提示。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "add claude claude-code")

        mock_client.add_server.assert_not_called()

    def test_mcp_remove_success(self):
        """remove 成功时应调用 client.remove_server。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.remove_server.return_value = True

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "remove claude")

        mock_client.remove_server.assert_called_once_with("claude")

    def test_mcp_remove_not_found(self):
        """remove 不存在的服务器时应显示警告。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.remove_server.return_value = False

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "remove nonexistent")

        mock_client.remove_server.assert_called_once_with("nonexistent")

    def test_mcp_connect_success(self):
        """connect 成功时应显示连接信息。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.connect.return_value = {
            "status": "connected", "name": "claude",
            "capabilities": {"tools": [{"name": "read_file"}]},
        }

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "connect claude")

        mock_client.connect.assert_called_once_with("claude")

    def test_mcp_connect_failure(self):
        """connect 失败时应显示错误。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.connect.return_value = {"error": "Server 'claude' not configured"}

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "connect claude")

        mock_client.connect.assert_called_once_with("claude")

    def test_mcp_disconnect_success(self):
        """disconnect 成功时应调用 client.disconnect。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.disconnect.return_value = {"status": "disconnected", "name": "claude"}

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "disconnect claude")

        mock_client.disconnect.assert_called_once_with("claude")

    def test_mcp_tools_success(self):
        """tools 子命令应列出远程服务器工具。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.list_tools.return_value = [
            {"name": "read_file", "description": "Read a file"},
            {"name": "write_file", "description": "Write a file"},
        ]

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "tools claude")

        mock_client.list_tools.assert_called_once_with("claude")

    def test_mcp_tools_not_connected(self):
        """tools 服务器未连接时应显示错误。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()
        mock_client.list_tools.return_value = [
            {"error": "Server 'claude' not connected"}
        ]

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "tools claude")

        mock_client.list_tools.assert_called_once_with("claude")

    def test_mcp_unknown_subcommand(self):
        """未知子命令应显示可用子命令列表。"""
        cli, session = self._make_cli_and_session()
        mock_client = MagicMock()

        with patch("core.mcp_client.get_mcp_client", return_value=mock_client):
            cli._chat_mcp(session, "foobar")

        # 不应调用任何 client 方法
        mock_client.list_servers.assert_not_called()

