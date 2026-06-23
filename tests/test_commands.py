"""Unit tests for the command registry and dispatch table.

Protects the v2 command system refactor (commands.py CommandDef + build_dispatch_table)
from regressions. Every command handler in the table must resolve to a real method
on CruxCLI via getattr reflection.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.commands import (
    COMMANDS, CommandDef, build_dispatch_table, get_by_category,
    get_all, register, auto_category,
)


class TestCommandRegistry:
    def test_all_commands_have_required_fields(self):
        for cmd in COMMANDS:
            assert isinstance(cmd, CommandDef)
            assert cmd.key, f"command missing key: {cmd}"
            assert cmd.name.startswith("/"), f"name must start with /: {cmd.name}"
            assert cmd.desc, f"command missing desc: {cmd.key}"
            assert cmd.category, f"command missing category: {cmd.key}"

    def test_no_duplicate_keys(self):
        keys = [c.key for c in COMMANDS]
        assert len(keys) == len(set(keys)), f"duplicate keys: {[k for k in keys if keys.count(k)>1]}"

    def test_exit_has_quit_q_aliases(self):
        exit_cmd = next(c for c in COMMANDS if c.key == "exit")
        assert "quit" in exit_cmd.aliases
        assert "q" in exit_cmd.aliases

    def test_help_has_all_alias(self):
        help_cmd = next(c for c in COMMANDS if c.key == "help")
        assert "all" in help_cmd.aliases

    def test_get_all_returns_copy(self):
        a = get_all()
        b = get_all()
        assert a == b
        assert a is not b

    def test_get_by_category_groups_correctly(self):
        cats = get_by_category()
        assert "创意生产" in cats
        assert "对话" in cats
        assert "任务工程" in cats
        assert "诊断配置" in cats
        # 每个分类至少有命令
        for cat, cmds in cats.items():
            assert len(cmds) > 0, f"empty category: {cat}"


class TestAutoCategory:
    def test_creative_keywords(self):
        assert auto_category("/img", "生成图片") == "创意生产"
        assert auto_category("/video", "生成视频") == "创意生产"

    def test_dialog_keywords(self):
        assert auto_category("/help", "帮助") == "对话"
        assert auto_category("/clear", "清空") == "对话"

    def test_engineering_keywords(self):
        assert auto_category("/plan", "规划任务") == "任务工程"
        assert auto_category("/deploy", "部署") == "任务工程"

    def test_diag_fallback(self):
        # 无匹配关键词 → 默认诊断配置
        assert auto_category("/xyz", "unknown") == "诊断配置"


class TestRegister:
    """register() 测试。

    注意：register() 会就地修改全局 COMMANDS 列表，为避免污染其他测试
    （特别是 test_cli_dispatch.py 的 handler 可达性检查），每个测试方法
    前后用 snapshot/restore 保存并恢复 COMMANDS 原状。
    """

    def setup_method(self):
        # 深拷贝当前 COMMANDS，测试后恢复
        self._snapshot = [type(c)(**c.__dict__) for c in COMMANDS]

    def teardown_method(self):
        COMMANDS[:] = self._snapshot

    def test_register_new_command(self):
        initial = len(COMMANDS)
        register("testcmd", "/testcmd", "<arg>", "test desc", "对话")
        assert any(c.key == "testcmd" for c in COMMANDS)
        assert len(COMMANDS) == initial + 1

    def test_register_update_existing(self):
        # 更新 img 的 desc，保留原 handler（_chat_img_inline）
        original = next(c for c in COMMANDS if c.key == "img")
        register("img", "/img", "<new>", "updated desc", "创意生产",
                 handler=original.handler)
        cmd = next(c for c in COMMANDS if c.key == "img")
        assert cmd.desc == "updated desc"
        assert cmd.handler == original.handler  # handler 未被清空

    def test_register_auto_category(self):
        register("autocat1", "/autocat1", "", "生成图片", "")
        cmd = next(c for c in COMMANDS if c.key == "autocat1")
        assert cmd.category == "创意生产"


class TestDispatchTable:
    def test_table_includes_all_keys(self):
        table = build_dispatch_table()
        for cmd in COMMANDS:
            assert cmd.key in table, f"key {cmd.key} missing from table"

    def test_table_includes_aliases(self):
        table = build_dispatch_table()
        assert "quit" in table
        assert "q" in table
        assert "all" in table

    def test_table_entry_format(self):
        table = build_dispatch_table()
        for key, (handler, cmd_def) in table.items():
            assert isinstance(handler, str), f"handler not str for {key}"
            assert isinstance(cmd_def, CommandDef), f"cmd_def wrong type for {key}"

    def test_handler_names_follow_convention(self):
        """Each handler is either _chat_<key>, _inline_<key>, or a custom _chat_xxx."""
        table = build_dispatch_table()
        for key, (handler, _cmd_def) in table.items():
            if key in ("exit", "quit", "q"):
                continue
            # handler 必须是 _ 开头的方法名
            assert handler is not None and handler.startswith("_"), f"handler {handler} for /{key} doesn't start with _"
