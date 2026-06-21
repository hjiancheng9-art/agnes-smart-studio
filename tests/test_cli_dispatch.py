"""Integration test: AgnesCLI Mixin composition + dispatch table integrity.

This is the regression guard for the cli.py Mixin refactor. It verifies that:
1. AgnesCLI can be imported (all Mixins compose without MRO errors)
2. Every handler in the dispatch table resolves via getattr
3. Core lifecycle methods exist (__init__, run, _chat, _stream_chat, etc.)
4. The command count matches expectations

If this test fails, the Mixin composition is broken.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestCLIComposition:
    def test_agnes_cli_importable(self):
        """AgnesCLI 必须能导入（Mixin 组合无 MRO 冲突）。"""
        from ui.cli import AgnesCLI
        assert AgnesCLI is not None

    def test_all_dispatch_handlers_reachable(self):
        """dispatch 表里每个 handler 必须能 getattr 到真实方法。"""
        from ui.cli import AgnesCLI
        from core.commands import build_dispatch_table

        table = build_dispatch_table()
        methods = {m for m in dir(AgnesCLI) if not m.startswith("__")}

        missing = []
        for cmd_key, (handler_name, _cmd_def) in table.items():
            # exit/quit/q 在 _chat 主循环里特殊处理，不需要 handler
            if cmd_key in ("exit", "quit", "q"):
                continue
            if handler_name not in methods:
                missing.append((cmd_key, handler_name))

        assert not missing, f"{len(missing)} handlers missing from AgnesCLI: {missing}"

    def test_core_methods_exist(self):
        """核心生命周期方法必须存在。"""
        from ui.cli import AgnesCLI
        required = [
            "__init__", "close", "__enter__", "__exit__",
            "run", "_chat",
            # 基础层 (SharedMixin)
            "_stream_chat", "_dispatch_command", "_prompt_user",
            "_ask_rating", "_extract_path_and_text", "_select_provider",
            "_pick_size", "_mode_hint", "_read_multiline",
            # 各 Mixin 的代表方法
            "_inline_clear", "_chat_help", "_chat_generate",
            "_chat_plan", "_chat_commit", "_self_diagnose",
            "_t2i", "_pipeline",
        ]
        for m in required:
            assert hasattr(AgnesCLI, m), f"AgnesCLI missing method: {m}"

    def test_mixin_inheritance_chain(self):
        """AgnesCLI 必须继承所有 7 个 Mixin。"""
        from ui.cli import AgnesCLI
        from ui.mixins import (
            SharedMixin, InlineCommandsMixin, CreativeCommandsMixin,
            EngineeringCommandsMixin, GitCommandsMixin, DiagCommandsMixin,
            GeneratorsMenuMixin,
        )
        mro = AgnesCLI.__mro__
        for mixin in [SharedMixin, InlineCommandsMixin, CreativeCommandsMixin,
                      EngineeringCommandsMixin, GitCommandsMixin, DiagCommandsMixin,
                      GeneratorsMenuMixin]:
            assert mixin in mro, f"{mixin.__name__} not in AgnesCLI MRO"

    def test_command_count_at_least_30(self):
        """命令总数至少 30（防止意外删除命令）。"""
        from core.commands import COMMANDS
        assert len(COMMANDS) >= 30, f"only {len(COMMANDS)} commands, expected >= 30"

    def test_dispatch_constants_defined(self):
        """dispatch 返回值常量必须在 SharedMixin 定义。"""
        from ui.cli import AgnesCLI
        assert hasattr(AgnesCLI, "_DISPATCH_OK")
        assert hasattr(AgnesCLI, "_DISPATCH_UNKNOWN")
        assert hasattr(AgnesCLI, "_DISPATCH_EXIT")
        assert AgnesCLI._DISPATCH_EXIT == "EXIT"
