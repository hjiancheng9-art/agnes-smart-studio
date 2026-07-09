"""Tests for core/commands.py — 命令定义"""

from core.commands import CommandDef


class TestCommandDef:
    def test_create(self):
        cmd = CommandDef(
            key="test",
            name="test",
            args="",
            desc="测试命令",
            category="dev",
            long_desc="测试命令的详细描述",
            aliases=("t",),
            handler="core.test_handler",
        )
        assert cmd.key == "test"
        assert cmd.name == "test"
        assert cmd.desc == "测试命令"
        assert cmd.category == "dev"

    def test_defaults(self):
        cmd = CommandDef(
            key="simple",
            name="simple",
            args="",
            desc="简单命令",
            category="general",
        )
        assert cmd.long_desc == ""
        assert cmd.aliases == ()
        assert cmd.handler is None

    def test_is_dataclass(self):
        assert hasattr(CommandDef, "__dataclass_fields__")
