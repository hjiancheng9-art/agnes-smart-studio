"""Tests for core.hooks — lifecycle hook system."""

import json
from unittest.mock import patch


class TestHookType:
    def test_enum_values(self):
        from core.hooks import HookType
        assert HookType.USER_PROMPT_SUBMIT.value == "user_prompt_submit"
        assert HookType.PRE_TOOL_USE.value == "pre_tool_use"
        assert HookType.POST_TOOL_USE.value == "post_tool_use"
        assert HookType.CHAT_TURN_START.value == "chat_turn_start"
        assert HookType.CHAT_TURN_END.value == "chat_turn_end"


class TestHookEvent:
    def test_default_values(self):
        from core.hooks import HookEvent, HookType
        event = HookEvent(hook_type=HookType.PRE_TOOL_USE)
        assert event.data == {}
        assert event.result is None
        assert event.stop_processing is False

    def test_with_values(self):
        from core.hooks import HookEvent, HookType
        event = HookEvent(
            hook_type=HookType.PRE_TOOL_USE,
            data={"key": "val"},
            result="original",
            stop_processing=True,
        )
        assert event.data == {"key": "val"}
        assert event.result == "original"
        assert event.stop_processing is True


class TestHookDataclass:
    def test_hook_creation(self):
        from core.hooks import Hook, HookType

        def handler(event):
            return event

        h = Hook(name="test", hook_type=HookType.PRE_TOOL_USE, handler=handler, priority=5)
        assert h.name == "test"
        assert h.priority == 5
        assert h.enabled is True


class TestHookManager:
    def _make_manager(self, tmp_path):
        """Create a HookManager with config pointing to tmp_path."""
        from core.hooks import HookManager
        mgr = HookManager.__new__(HookManager)
        mgr._hooks = {}
        mgr._lock = mgr._lock if hasattr(mgr, '_lock') else __import__('threading').Lock()
        return mgr

    def test_register_and_list(self):
        from core.hooks import HookType

        def handler(event):
            return event

        mgr = self._make_manager(None)
        result = mgr.register("test_hook", HookType.PRE_TOOL_USE, handler, priority=5)
        assert result is True
        hooks = mgr.list_hooks()
        assert len(hooks) == 1
        assert hooks[0]["name"] == "test_hook"
        assert hooks[0]["type"] == "pre_tool_use"
        assert hooks[0]["priority"] == 5
        assert hooks[0]["enabled"] is True

    def test_register_duplicate(self):
        from core.hooks import HookType

        def h1(e): return e
        def h2(e): return e

        mgr = self._make_manager(None)
        assert mgr.register("dup", HookType.PRE_TOOL_USE, h1) is True
        assert mgr.register("dup", HookType.POST_TOOL_USE, h2) is False

    def test_unregister(self):
        from core.hooks import HookType

        def handler(e): return e

        mgr = self._make_manager(None)
        mgr.register("to_remove", HookType.PRE_TOOL_USE, handler)
        assert mgr.unregister("to_remove") is True
        assert mgr.list_hooks() == []

    def test_unregister_nonexistent(self):
        mgr = self._make_manager(None)
        assert mgr.unregister("nope") is False

    def test_enable_disable(self):
        from core.hooks import HookType

        def handler(e): return e

        mgr = self._make_manager(None)
        mgr.register("toggle", HookType.PRE_TOOL_USE, handler)
        mgr.disable("toggle")
        hooks = mgr.list_hooks()
        assert hooks[0]["enabled"] is False
        mgr.enable("toggle")
        hooks = mgr.list_hooks()
        assert hooks[0]["enabled"] is True

    def test_enable_nonexistent(self):
        mgr = self._make_manager(None)
        # Should not raise
        mgr.enable("nope")

    def test_fire_single_hook(self):
        from core.hooks import HookType

        def handler(event):
            event.result = "handled"
            return event

        mgr = self._make_manager(None)
        mgr.register("test", HookType.POST_TOOL_USE, handler)
        event = mgr.fire(HookType.POST_TOOL_USE, data={"tool": "read_file"})
        assert event.result == "handled"
        assert event.data == {"tool": "read_file"}

    def test_fire_priority_order(self):
        from core.hooks import HookType

        results = []

        def low_handler(event):
            results.append("low")
            return event

        def high_handler(event):
            results.append("high")
            return event

        mgr = self._make_manager(None)
        mgr.register("low", HookType.PRE_TOOL_USE, low_handler, priority=1)
        mgr.register("high", HookType.PRE_TOOL_USE, high_handler, priority=10)
        mgr.fire(HookType.PRE_TOOL_USE)
        assert results == ["high", "low"]

    def test_fire_stop_processing(self):
        from core.hooks import HookType

        results = []

        def first_handler(event):
            results.append("first")
            event.stop_processing = True
            return event

        def second_handler(event):
            results.append("second")
            return event

        mgr = self._make_manager(None)
        mgr.register("first", HookType.POST_TOOL_USE, first_handler, priority=10)
        mgr.register("second", HookType.POST_TOOL_USE, second_handler, priority=5)
        mgr.fire(HookType.POST_TOOL_USE)
        assert results == ["first"]

    def test_fire_skips_disabled(self):
        from core.hooks import HookType

        results = []

        def handler(event):
            results.append("called")
            return event

        mgr = self._make_manager(None)
        mgr.register("disabled", HookType.POST_TOOL_USE, handler)
        mgr.disable("disabled")
        mgr.fire(HookType.POST_TOOL_USE)
        assert results == []

    def test_fire_handler_exception_caught(self):
        from core.hooks import HookType

        def bad_handler(event):
            raise RuntimeError("oops")

        mgr = self._make_manager(None)
        mgr.register("bad", HookType.POST_TOOL_USE, bad_handler)
        # Should not raise, exception is logged
        event = mgr.fire(HookType.POST_TOOL_USE)
        assert event.hook_type == HookType.POST_TOOL_USE

    def test_fire_no_hooks(self):
        from core.hooks import HookType
        mgr = self._make_manager(None)
        event = mgr.fire(HookType.PRE_TOOL_USE)
        assert event.data == {}
        assert event.result is None

    def test_load_from_config_missing_file(self, tmp_path):
        from core.hooks import HookManager
        config_dir = tmp_path / "output"
        config_dir.mkdir()
        mgr = HookManager.__new__(HookManager)
        mgr._hooks = {}
        mgr._lock = __import__('threading').Lock()
        # _load_from_config with non-existent hooks.json should not raise
        mgr._load_from_config = HookManager._load_from_config.__get__(mgr)
        with patch("core.hooks.OUTPUT_DIR", config_dir):
            mgr._load_from_config()
        assert mgr._hooks == {}

    def test_load_from_config_valid(self, tmp_path):
        from core.hooks import HookManager
        config_dir = tmp_path / "output"
        config_dir.mkdir()
        hooks_json = [
            {
                "name": "test",
                "type": "post_tool_use",
                "handler_module": "builtins",
                "handler_func": "len",
                "priority": 5,
            }
        ]
        (config_dir / "hooks.json").write_text(
            json.dumps(hooks_json), encoding="utf-8"
        )
        mgr = HookManager.__new__(HookManager)
        mgr._hooks = {}
        mgr._lock = __import__('threading').Lock()
        with patch("core.hooks.OUTPUT_DIR", config_dir):
            mgr._load_from_config()
        assert "test" in mgr._hooks

    def test_load_from_config_incomplete_entry(self, tmp_path):
        from core.hooks import HookManager
        config_dir = tmp_path / "output"
        config_dir.mkdir()
        hooks_json = [{"name": "incomplete"}]  # missing type, handler_module, handler_func
        (config_dir / "hooks.json").write_text(
            json.dumps(hooks_json), encoding="utf-8"
        )
        mgr = HookManager.__new__(HookManager)
        mgr._hooks = {}
        mgr._lock = __import__('threading').Lock()
        with patch("core.hooks.OUTPUT_DIR", config_dir):
            mgr._load_from_config()
        assert "incomplete" not in mgr._hooks

    def test_load_from_config_bad_type(self, tmp_path):
        from core.hooks import HookManager
        config_dir = tmp_path / "output"
        config_dir.mkdir()
        hooks_json = [
            {
                "name": "bad_type",
                "type": "nonexistent_type",
                "handler_module": "builtins",
                "handler_func": "len",
            }
        ]
        (config_dir / "hooks.json").write_text(
            json.dumps(hooks_json), encoding="utf-8"
        )
        mgr = HookManager.__new__(HookManager)
        mgr._hooks = {}
        mgr._lock = __import__('threading').Lock()
        with patch("core.hooks.OUTPUT_DIR", config_dir):
            mgr._load_from_config()
        assert "bad_type" not in mgr._hooks


class TestSafetyFilter:
    def test_detects_dangerous_pattern(self):
        from core.hooks import _safety_filter_handler, HookEvent, HookType
        event = HookEvent(
            hook_type=HookType.USER_PROMPT_SUBMIT,
            data={"prompt": "run rm -rf / now"},
            result="",
        )
        result = _safety_filter_handler(event)
        assert "[SAFETY WARNING]" in result.result

    def test_safe_prompt_unchanged(self):
        from core.hooks import _safety_filter_handler, HookEvent, HookType
        event = HookEvent(
            hook_type=HookType.USER_PROMPT_SUBMIT,
            data={"prompt": "write a hello world program"},
            result="hello response",
        )
        result = _safety_filter_handler(event)
        assert result.result == "hello response"

    def test_empty_prompt(self):
        from core.hooks import _safety_filter_handler, HookEvent, HookType
        event = HookEvent(
            hook_type=HookType.USER_PROMPT_SUBMIT,
            data={"prompt": ""},
        )
        result = _safety_filter_handler(event)
        assert result.result is None


class TestHelperFunctions:
    def test_on_prompt_submit(self):
        from core.hooks import on_prompt_submit, hook_manager

        def handler(e):
            return e
        result = on_prompt_submit("test_prompt", handler, priority=3)
        assert result is True
        # Clean up
        hook_manager.unregister("test_prompt")

    def test_on_pre_tool(self):
        from core.hooks import on_pre_tool, hook_manager

        def handler(e):
            return e
        result = on_pre_tool("test_pre", handler)
        assert result is True
        hook_manager.unregister("test_pre")

    def test_on_post_tool(self):
        from core.hooks import on_post_tool, hook_manager

        def handler(e):
            return e
        result = on_post_tool("test_post", handler)
        assert result is True
        hook_manager.unregister("test_post")
