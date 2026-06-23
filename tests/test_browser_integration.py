"""Tests for #7 browser_tools runtime integration.

验证 browser_tools 真正被 ToolRegistry + ChatSession 调用。
此前 BROWSER_TOOL_DEFS / BROWSER_EXECUTOR_MAP 是零调用方孤岛。

覆盖路径:
1. ToolRegistry.load(browser=True) 注册 6 个 browser_* 工具 + 执行器
2. ChatSession.toggle_browser() 切换 toggle + 重建 tools + system prompt
3. /browser 命令注册 + dispatch 路由到 _inline_browser handler
4. browser_providers 工具可正常执行（纯本地，无外部依赖）
"""
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _mocked_session():
    """构造一个 mock client 的 ChatSession（不打真实 API）。"""
    from core.chat import ChatSession
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter([])
    return ChatSession(mock_client)


class TestToolRegistryBrowserLoad:
    """ToolRegistry.load(browser=True) 应注册 6 个 browser_* 工具。"""

    def test_browser_tools_registered_on_load(self):
        from core.tools import ToolRegistry
        # 用不存在的 config_path 避免加载 tools.json 中的 browser_screenshot
        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        count = reg.load(browser=True)
        # 至少 3 builtin + 6 browser = 9
        assert count >= 9
        # 所有 6 个 browser_tools 模块的工具应注册
        expected = {"browser_generate", "browser_check", "browser_download",
                    "browser_providers", "browser_setup", "browser_cancel"}
        for name in expected:
            assert reg.has(name), f"browser tool '{name}' not registered"
        assert len(expected) == 6

    def test_browser_tools_not_loaded_by_default(self):
        """默认 load() 不含 browser 工具。"""
        from core.tools import ToolRegistry
        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        count = reg.load()
        browser_names = [n for n in reg.tool_names if n.startswith("browser_")]
        assert len(browser_names) == 0

    def test_browser_executors_mapped(self):
        """browser_* 工具均有 executor 映射，execute 不抛 KeyError。"""
        from core.tools import ToolRegistry
        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        reg.load(browser=True)
        # browser_providers 是无参的纯本地工具，可安全执行
        result = reg.execute("browser_providers", {})
        data = json.loads(result)
        assert "providers" in data
        assert data["total"] == 8  # 8 个 provider

    def test_browser_generate_executor_exists(self):
        """browser_generate executor 存在且可被调用（参数校验拒绝空 prompt）。"""
        from core.tools import ToolRegistry
        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        reg.load(browser=True)
        # 缺少 required 参数 prompt → 校验拒绝
        result = reg.execute("browser_generate", {"provider": "dalle"})
        assert "缺少必需参数" in result

    def test_browser_unknown_provider(self):
        """未知 provider 应返回错误。"""
        from core.browser_tools import execute_browser_generate
        result = json.loads(execute_browser_generate(provider="nonexistent", prompt="test"))
        assert result["success"] is False
        assert "未知 provider" in result["error"]


class TestToggleBrowserIntegration:
    """ChatSession.toggle_browser() 应切换状态 + 重建工具 + prompt。"""

    def test_toggle_browser_default_off(self):
        session = _mocked_session()
        assert session.browser_enabled is False

    def test_toggle_browser_on(self):
        session = _mocked_session()
        is_on = session.toggle_browser()
        assert is_on is True
        assert session.browser_enabled is True
        # 工具应包含 browser_tools 模块的 6 个工具
        browser_core = {"browser_generate", "browser_check", "browser_download",
                        "browser_providers", "browser_setup", "browser_cancel"}
        tool_set = set(session.tools.tool_names)
        assert browser_core.issubset(tool_set)

    def test_toggle_browser_off(self):
        session = _mocked_session()
        session.toggle_browser()  # on
        is_on = session.toggle_browser()  # off
        assert is_on is False
        assert session.browser_enabled is False
        # browser_tools 模块的 6 个核心工具不应存在
        browser_core = {"browser_generate", "browser_check", "browser_download",
                        "browser_providers", "browser_setup", "browser_cancel"}
        tool_set = set(session.tools.tool_names)
        assert browser_core.isdisjoint(tool_set)

    def test_toggle_browser_rebuilds_system_prompt(self):
        """toggle 后 system message 应包含 Browser Companion 使用说明。"""
        session = _mocked_session()
        session.toggle_browser()
        system_msg = session.messages[0]["content"]
        assert "Browser Companion" in system_msg
        assert "browser_generate" in system_msg

    def test_toggle_browser_off_removes_prompt(self):
        """关闭 browser 后 system message 不再包含 Browser 说明。"""
        session = _mocked_session()
        session.toggle_browser()  # on
        session.toggle_browser()  # off
        system_msg = session.messages[0]["content"]
        assert "Browser Companion" not in system_msg


class TestBrowserCommandRegistration:
    """/browser 命令应注册到 COMMANDS 并正确路由。"""

    def test_browser_in_commands(self):
        from core.commands import get_all
        keys = [c.key for c in get_all()]
        assert "browser" in keys

    def test_browser_command_def(self):
        from core.commands import get_all
        cmd = next(c for c in get_all() if c.key == "browser")
        assert cmd.name == "/browser"
        assert cmd.handler == "_inline_browser"

    def test_browser_in_dispatch_table(self):
        from core.commands import build_dispatch_table
        table = build_dispatch_table()
        assert "browser" in table
        handler, cmd_def = table["browser"]
        assert handler == "_inline_browser"

    def test_browser_providers_list(self):
        """browser_providers 应返回 8 个平台。"""
        from core.browser_tools import execute_browser_providers
        data = json.loads(execute_browser_providers())
        assert data["total"] == 8
        names = [p["id"] for p in data["providers"]]
        assert "kling" in names
        assert "dalle" in names
        assert "gemini" in names

    def test_browser_tool_categories(self):
        """browser_* 工具应归类到「🌐 网页生成」。"""
        from core.tools import ToolRegistry
        # 用不存在的 config 避免加载 tools.json 中额外的 browser_screenshot
        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        reg.load(browser=True)
        cats = reg.tool_categories
        assert "🌐 网页生成" in cats
        # 来自 browser_tools 模块的 6 个核心工具
        assert len(cats["🌐 网页生成"]) >= 6
