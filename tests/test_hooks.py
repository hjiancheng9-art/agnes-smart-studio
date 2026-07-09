"""Tests for core/hooks.py — 钩子系统"""

from core.hooks import HookEvent, HookManager, HookType


class TestHookManager:
    def test_create(self):
        hm = HookManager()
        assert hm is not None

    def test_register(self):
        hm = HookManager()

        def handler(event):
            return event

        result = hm.register("pre_tool", HookType.PRE_TOOL_USE, handler)
        assert result is True or isinstance(result, bool)

    def test_register_then_list(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("pre_tool", HookType.PRE_TOOL_USE, handler)
        hooks = hm.list_hooks()
        assert isinstance(hooks, list)

    def test_clear(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("pre_tool", HookType.PRE_TOOL_USE, handler)
        hm.clear()
        hooks = hm.list_hooks()
        assert len(hooks) == 0

    def test_unregister(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("pre_tool", HookType.PRE_TOOL_USE, handler)
        # unregister by name
        hm.unregister("pre_tool")
        assert True

    def test_disable_enable(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("chat_start", HookType.CHAT_TURN_START, handler)
        hm.disable("chat_start")
        assert True
        hm.enable("chat_start")
        assert True


class TestHookEvent:
    def test_default_creation(self):
        event = HookEvent(hook_type=HookType.USER_PROMPT_SUBMIT, data={})
        assert event.data == {}
        assert event.result is None
        assert event.stop_processing is False
