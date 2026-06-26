"""Tests for #9 /extend toggle + notebook/audio_tools integration.

验证 /extend 命令统一管理 notebook/audio/browser 三个扩展工具集。
覆盖:
1. /extend 命令注册 + dispatch 路由
2. ToolRegistry.load(notebook=True/audio=True) 注册工具
3. ChatSession.toggle_notebook/toggle_audio 切换 + prompt 重建
4. notebook/audio 工具执行（纯本地无外部依赖）
5. /extend handler 存在并可调用
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _mocked_session():
    """构造一个 mock client 的 ChatSession（不打真实 API）。"""
    from core.chat import ChatSession

    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter([])
    return ChatSession(mock_client)


# ============================================================
#  /extend 命令注册
# ============================================================


class TestExtendCommandRegistration:
    """/extend 命令应注册到 COMMANDS 并正确路由。"""

    def test_extend_in_commands(self):
        from core.commands import get_all

        keys = [c.key for c in get_all()]
        assert "extend" in keys

    def test_extend_command_def(self):
        from core.commands import get_all

        cmd = next(c for c in get_all() if c.key == "extend")
        assert cmd.name == "/extend"
        assert cmd.handler == "_chat_extend"
        assert cmd.category == "诊断配置"

    def test_extend_in_dispatch_table(self):
        from core.commands import build_dispatch_table

        table = build_dispatch_table()
        assert "extend" in table
        handler, cmd_def = table["extend"]
        assert handler == "_chat_extend"

    def test_extend_handler_in_mixin(self):
        from ui.mixins.diag import DiagCommandsMixin

        assert hasattr(DiagCommandsMixin, "_chat_extend")
        assert callable(DiagCommandsMixin._chat_extend)


# ============================================================
#  Notebook 工具集成
# ============================================================


class TestNotebookToolIntegration:
    """ToolRegistry.load(notebook=True) 应注册 5 个 notebook_* 工具。"""

    def test_notebook_tools_registered_on_load(self):
        from core.tools import ToolRegistry

        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        count = reg.load(notebook=True)
        # 至少 3 builtin + 5 notebook = 8
        assert count >= 8
        expected = {"notebook_open", "notebook_edit_cell", "notebook_add_cell", "notebook_run_cell", "notebook_save"}
        for name in expected:
            assert reg.has(name), f"notebook tool '{name}' not registered"

    def test_notebook_tools_not_loaded_by_default(self):
        from core.tools import ToolRegistry

        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        reg.load()
        nb_names = [n for n in reg.tool_names if n.startswith("notebook_")]
        assert len(nb_names) == 0

    def test_notebook_in_tool_categories(self):
        from core.tools import ToolRegistry

        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        reg.load(notebook=True)
        cats = reg.tool_categories
        assert "📓 Notebook" in cats
        assert len(cats["📓 Notebook"]) == 5


class TestToggleNotebook:
    """ChatSession.toggle_notebook() 应切换状态 + 重建工具 + prompt。"""

    def test_toggle_notebook_default_off(self):
        session = _mocked_session()
        assert session.notebook_enabled is False

    def test_toggle_notebook_on(self):
        session = _mocked_session()
        is_on = session.toggle_notebook()
        assert is_on is True
        assert session.notebook_enabled is True
        nb_core = {"notebook_open", "notebook_edit_cell", "notebook_add_cell", "notebook_run_cell", "notebook_save"}
        tool_set = set(session.tools.tool_names)
        assert nb_core.issubset(tool_set)

    def test_toggle_notebook_off(self):
        session = _mocked_session()
        session.toggle_notebook()  # on
        is_on = session.toggle_notebook()  # off
        assert is_on is False
        nb_core = {"notebook_open", "notebook_edit_cell", "notebook_add_cell", "notebook_run_cell", "notebook_save"}
        tool_set = set(session.tools.tool_names)
        assert nb_core.isdisjoint(tool_set)

    def test_toggle_notebook_rebuilds_prompt(self):
        session = _mocked_session()
        session.toggle_notebook()
        system_msg = session.messages[0]["content"]
        assert "Notebook" in system_msg


# ============================================================
#  Audio 工具集成
# ============================================================


class TestAudioToolIntegration:
    """ToolRegistry.load(audio=True) 应注册 4 个音频工具。"""

    def test_audio_tools_registered_on_load(self):
        from core.tools import ToolRegistry

        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        count = reg.load(audio=True)
        # 至少 3 builtin + 4 audio = 7
        assert count >= 7
        expected = {"tts_narration", "generate_bgm", "generate_sfx", "audio_mixdown"}
        for name in expected:
            assert reg.has(name), f"audio tool '{name}' not registered"

    def test_audio_tools_not_loaded_by_default(self):
        from core.tools import ToolRegistry

        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        reg.load()
        audio_names = {
            n for n in reg.tool_names if n in {"tts_narration", "generate_bgm", "generate_sfx", "audio_mixdown"}
        }
        assert len(audio_names) == 0

    def test_audio_in_tool_categories(self):
        from core.tools import ToolRegistry

        reg = ToolRegistry(config_path=ROOT / "tests" / "__nonexistent__.json")
        reg.load(audio=True)
        cats = reg.tool_categories
        assert "🎵 音频" in cats
        assert len(cats["🎵 音频"]) == 4


class TestToggleAudio:
    """ChatSession.toggle_audio() 应切换状态 + 重建工具 + prompt。"""

    def test_toggle_audio_default_off(self):
        session = _mocked_session()
        assert session.audio_enabled is False

    def test_toggle_audio_on(self):
        session = _mocked_session()
        is_on = session.toggle_audio()
        assert is_on is True
        assert session.audio_enabled is True
        audio_core = {"tts_narration", "generate_bgm", "generate_sfx", "audio_mixdown"}
        tool_set = set(session.tools.tool_names)
        assert audio_core.issubset(tool_set)

    def test_toggle_audio_off(self):
        session = _mocked_session()
        session.toggle_audio()  # on
        is_on = session.toggle_audio()  # off
        assert is_on is False
        audio_core = {"tts_narration", "generate_bgm", "generate_sfx", "audio_mixdown"}
        tool_set = set(session.tools.tool_names)
        assert audio_core.isdisjoint(tool_set)

    def test_toggle_audio_rebuilds_prompt(self):
        session = _mocked_session()
        session.toggle_audio()
        system_msg = session.messages[0]["content"]
        assert "音频" in system_msg


# ============================================================
#  组合：notebook + audio + browser 同时启用
# ============================================================


class TestCombinedExtensions:
    """三个扩展可同时启用，工具数累加。"""

    def test_all_extensions_on(self):
        session = _mocked_session()
        session.toggle_notebook()
        session.toggle_audio()
        session.toggle_browser()
        tool_set = set(session.tools.tool_names)
        # notebook 5 + audio 4 + browser 6 = 15 个扩展工具
        nb_core = {"notebook_open", "notebook_edit_cell", "notebook_add_cell", "notebook_run_cell", "notebook_save"}
        audio_core = {"tts_narration", "generate_bgm", "generate_sfx", "audio_mixdown"}
        browser_core = {
            "browser_generate",
            "browser_check",
            "browser_download",
            "browser_providers",
            "browser_setup",
            "browser_cancel",
        }
        assert nb_core.issubset(tool_set)
        assert audio_core.issubset(tool_set)
        assert browser_core.issubset(tool_set)

    def test_extensions_independent_toggle(self):
        """notebook 开关不影响 audio 状态。"""
        session = _mocked_session()
        session.toggle_notebook()  # nb on
        session.toggle_audio()  # audio on
        # 切 notebook 不应影响 audio
        session.toggle_notebook()  # nb off
        assert session.notebook_enabled is False
        assert session.audio_enabled is True
