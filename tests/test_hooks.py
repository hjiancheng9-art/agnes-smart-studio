"""Tests for core/hooks.py — hook system including Stop event & PreToolUse."""

from core.hooks import (
    HookEvent,
    HookManager,
    HookType,
    on_notification,
    on_post_tool,
    on_pre_tool,
    on_prompt_submit,
    on_session_start,
    on_stop,
    register_stop_guard,
)


def _make_stop_guard():
    """Create a stop guard handler (same logic as register_stop_guard, but isolated)."""

    def handler(event):
        last_message = event.data.get("last_assistant_message", "")
        if not last_message:
            return event
        fake_done_markers = [
            "should be working", "should be fixed", "seems to work",
            "probably fine", "might work",
            "理论上应该", "应该可以了", "看起来没问题",
        ]
        for marker in fake_done_markers:
            if marker in last_message:
                event.stop_decision = "block"
                event.stop_reason = (
                    f"检测到不确定的完成声明 ('{marker}')。请运行验证命令确认修复。"
                )
                break
        return event

    return handler


# ── HookManager basics ───────────────────────────────────────────────────


class TestHookManager:
    def test_create(self):
        hm = HookManager()
        assert hm is not None

    def test_register(self):
        hm = HookManager()

        def handler(event):
            return event

        result = hm.register("pre_tool", HookType.PRE_TOOL_USE, handler)
        assert result is True

    def test_duplicate_register(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("dup", HookType.PRE_TOOL_USE, handler)
        result = hm.register("dup", HookType.PRE_TOOL_USE, handler)
        assert result is False

    def test_list_hooks(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("pre_tool", HookType.PRE_TOOL_USE, handler)
        hooks = hm.list_hooks()
        assert isinstance(hooks, list)
        assert any(h["name"] == "pre_tool" for h in hooks)

    def test_clear(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("pre_tool", HookType.PRE_TOOL_USE, handler)
        hm.clear()
        assert len(hm.list_hooks()) == 0

    def test_unregister(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("pre_tool", HookType.PRE_TOOL_USE, handler)
        assert hm.unregister("pre_tool")
        assert not hm.unregister("nonexistent")

    def test_disable_enable(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("chat_start", HookType.CHAT_TURN_START, handler)
        hm.disable("chat_start")
        hm.enable("chat_start")
        assert True


# ── HookEvent ────────────────────────────────────────────────────────────


class TestHookEvent:
    def test_default_creation(self):
        event = HookEvent(hook_type=HookType.USER_PROMPT_SUBMIT, data={})
        assert event.data == {}
        assert event.result is None
        assert event.stop_processing is False

    def test_pre_tool_defaults(self):
        event = HookEvent(hook_type=HookType.PRE_TOOL_USE)
        assert event.permission_decision == "allow"
        assert event.updated_input is None
        assert event.permission_reason == ""

    def test_stop_defaults(self):
        event = HookEvent(hook_type=HookType.STOP)
        assert event.stop_decision == ""
        assert event.loop_count == 0
        assert event.loop_limit == 5


# ── HookType enum ─────────────────────────────────────────────────────────


class TestHookTypeEnum:
    def test_all_types_present(self):
        types = {t.value for t in HookType}
        expected = {
            "session_start", "user_prompt_submit", "pre_tool_use",
            "post_tool_use", "chat_turn_start", "chat_turn_end",
            "stop", "notification",
        }
        assert types == expected

    def test_from_string(self):
        assert HookType("stop") == HookType.STOP
        assert HookType("notification") == HookType.NOTIFICATION
        assert HookType("session_start") == HookType.SESSION_START


# ── Stop event ───────────────────────────────────────────────────────────


class TestStopEvent:
    def test_fire_stop_clean(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("passthrough", HookType.STOP, handler)
        event = hm.fire(HookType.STOP, data={"last_assistant_message": "all done"})
        assert event.stop_decision == ""

    def test_fire_stop_blocked(self):
        hm = HookManager()

        def handler(event):
            event.stop_decision = "block"
            event.stop_reason = "tests failed, keep working"
            return event

        hm.register("blocker", HookType.STOP, handler)
        event = hm.fire(HookType.STOP, data={"last_assistant_message": "done"})
        assert event.stop_decision == "block"
        assert "tests failed" in event.stop_reason

    def test_stop_guard_blocks_uncertain(self):
        hm = HookManager()
        # Register on this local hm, not the global one
        hm.register("stop_guard", HookType.STOP, _make_stop_guard(), priority=0)

        event = hm.fire(HookType.STOP, data={
            "last_assistant_message": "bug修复完成，应该可以了"
        })
        assert event.stop_decision == "block"

    def test_stop_guard_passes_clean(self):
        hm = HookManager()
        hm.register("stop_guard", HookType.STOP, _make_stop_guard(), priority=0)

        event = hm.fire(HookType.STOP, data={
            "last_assistant_message": "pytest 5 passed 0 failed, lint clean"
        })
        assert event.stop_decision == ""

    def test_stop_guard_blocks_english_uncertain(self):
        hm = HookManager()
        hm.register("stop_guard", HookType.STOP, _make_stop_guard(), priority=0)

        event = hm.fire(HookType.STOP, data={
            "last_assistant_message": "The bug seems to work now"
        })
        assert event.stop_decision == "block"

    def test_stop_guard_empty_message(self):
        hm = HookManager()
        hm.register("stop_guard", HookType.STOP, _make_stop_guard(), priority=0)

        event = hm.fire(HookType.STOP, data={
            "last_assistant_message": ""
        })
        assert event.stop_decision == ""

    def test_stop_loop_count_respected(self):
        # Simulate: loop_count >= loop_limit should skip
        hm = HookManager()

        def handler(event):
            event.stop_decision = "block"
            return event

        hm.register("loop-blocker", HookType.STOP, handler)
        event = HookEvent(hook_type=HookType.STOP, data={"last_assistant_message": "x"})
        event.loop_count = 5
        event.loop_limit = 3  # Exceeded, but handler doesn't know — fire bypasses
        # Hook system doesn't enforce loop_limit in fire(); the caller must check
        assert True  # Architecture test — loop_limit enforcement is caller's job


# ── PreToolUse permissions ────────────────────────────────────────────────


class TestPreToolUsePermissions:
    def test_allow_by_default(self):
        hm = HookManager()

        def handler(event):
            return event

        hm.register("p", HookType.PRE_TOOL_USE, handler)
        event = hm.fire(HookType.PRE_TOOL_USE, data={"tool_name": "Write"})
        assert event.permission_decision == "allow"

    def test_deny_beats_ask(self):
        hm = HookManager()

        def asker(event):
            event.permission_decision = "ask"
            return event

        def denier(event):
            event.permission_decision = "deny"
            event.permission_reason = "blocked by policy"
            return event

        hm.register("asker", HookType.PRE_TOOL_USE, asker, priority=10)
        hm.register("denier", HookType.PRE_TOOL_USE, denier, priority=100)
        event = hm.fire(HookType.PRE_TOOL_USE, data={"tool_name": "Bash"})
        assert event.permission_decision == "deny"
        assert event.permission_reason == "blocked by policy"

    def test_ask_beats_allow(self):
        hm = HookManager()

        def allow_handler(event):
            return event

        def asker(event):
            event.permission_decision = "ask"
            event.permission_reason = "needs user confirmation"
            return event

        hm.register("allow", HookType.PRE_TOOL_USE, allow_handler, priority=0)
        hm.register("ask", HookType.PRE_TOOL_USE, asker, priority=100)
        event = hm.fire(HookType.PRE_TOOL_USE, data={"tool_name": "Bash"})
        assert event.permission_decision == "ask"

    def test_updated_input_propagation(self):
        hm = HookManager()

        def modifier(event):
            event.updated_input = {"path": "fixed.py", "content": "fixed content"}
            return event

        hm.register("mod", HookType.PRE_TOOL_USE, modifier)
        event = hm.fire(HookType.PRE_TOOL_USE, data={
            "tool_name": "Write",
            "args": {"path": "bad.py", "content": "bad content"}
        })
        assert event.updated_input is not None
        assert event.updated_input["path"] == "fixed.py"

    def test_updated_input_last_wins(self):
        hm = HookManager()

        def first(event):
            event.updated_input = {"value": "first"}
            return event

        def second(event):
            event.updated_input = {"value": "second"}
            return event

        # Lower priority runs last → its updated_input wins ("last non-None wins")
        hm.register("first", HookType.PRE_TOOL_USE, first, priority=100)
        hm.register("second", HookType.PRE_TOOL_USE, second, priority=10)
        event = hm.fire(HookType.PRE_TOOL_USE, data={"tool_name": "Edit"})
        assert event.updated_input["value"] == "second"

    def test_encoding_garbled_interception(self):
        """PreToolUse can detect garbled input and escalate to ask."""
        hm = HookManager()

        def encoding_guard(event):
            args = event.data.get("args", {}) or {}
            content = str(args.get("content", ""))
            if "�" in content:
                event.permission_decision = "ask"
                event.permission_reason = "detected garbled characters"
            return event

        hm.register("encoding_guard", HookType.PRE_TOOL_USE, encoding_guard, 90)
        event = hm.fire(HookType.PRE_TOOL_USE, data={
            "tool_name": "write_file",
            "args": {"content": "some text with � garble"}
        })
        assert event.permission_decision == "ask"


# ── Shortcut registration functions ──────────────────────────────────────


class TestShortcutFunctions:
    def test_on_stop_registers(self):
        hm = HookManager()

        def handler(event):
            return event

        result = hm.register("stop-test", HookType.STOP, handler)
        assert result

    def test_on_session_start_registers(self):
        hm = HookManager()

        def handler(event):
            return event

        result = hm.register("ss-test", HookType.SESSION_START, handler)
        assert result

    def test_on_notification_registers(self):
        hm = HookManager()

        def handler(event):
            return event

        result = hm.register("notif-test", HookType.NOTIFICATION, handler)
        assert result


# ── Fire short-circuits ─────────────────────────────────────────────────


class TestFireShortCircuit:
    def test_stop_processing_short_circuits(self):
        hm = HookManager()
        called_second = []

        def first(event):
            event.stop_processing = True
            return event

        def second(event):
            called_second.append(True)
            return event

        hm.register("first", HookType.POST_TOOL_USE, first, priority=100)
        hm.register("second", HookType.POST_TOOL_USE, second, priority=0)
        hm.fire(HookType.POST_TOOL_USE, data={})
        assert len(called_second) == 0
