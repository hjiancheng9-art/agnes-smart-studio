"""InputRouter / FocusState / ClipboardAdapter 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestFocusState:
    def test_initial_state(self):
        from ui.input_router import FocusState
        f = FocusState()
        assert not f.enabled
        assert f.index == -1
        assert f.total == 0

    def test_next_activates(self):
        from ui.input_router import FocusState
        f = FocusState()
        f.total = 3
        idx = f.next()
        assert f.enabled
        assert idx == 2  # last message

    def test_prev_activates(self):
        from ui.input_router import FocusState
        f = FocusState()
        f.total = 3
        idx = f.prev()
        assert f.enabled
        assert idx == 2

    def test_next_and_prev_navigate(self):
        from ui.input_router import FocusState
        f = FocusState()
        f.total = 5
        f.next()  # index=4
        f.prev()  # index=3
        f.prev()  # index=2
        assert f.index == 2
        f.next()  # index=3
        assert f.index == 3

    def test_next_clamps(self):
        from ui.input_router import FocusState
        f = FocusState()
        f.total = 2
        f.next()  # 1
        f.next()  # still 1
        assert f.index == 1

    def test_prev_clamps(self):
        from ui.input_router import FocusState
        f = FocusState()
        f.total = 2
        f.next()  # 1
        f.prev()  # 0
        f.prev()  # still 0
        assert f.index == 0

    def test_is_focused(self):
        from ui.input_router import FocusState
        f = FocusState()
        f.total = 3
        f.next()  # index=2
        assert f.is_focused(2)
        assert not f.is_focused(0)
        assert not f.is_focused(1)


class TestClipboardAdapter:
    def test_available(self):
        from ui.input_router import ClipboardAdapter
        clip = ClipboardAdapter()
        assert isinstance(clip.available, bool)

    def test_copy_returns_bool(self):
        from ui.input_router import ClipboardAdapter
        clip = ClipboardAdapter()
        ok = clip.copy("test123")
        assert isinstance(ok, bool)
        if ok:
            import pyperclip
            assert pyperclip.paste() == "test123"

    def test_copy_and_report_success(self):
        from ui.input_router import ClipboardAdapter
        clip = ClipboardAdapter()
        ok, msg = clip.copy_and_report("hello world", "Test copy")
        if ok:
            assert "Test copy" in msg
            assert "hello world" in msg

    def test_copy_empty_text(self):
        from ui.input_router import ClipboardAdapter
        clip = ClipboardAdapter()
        ok = clip.copy("")
        assert not ok


class TestInputMode:
    def test_enum_values(self):
        from ui.input_router import InputMode
        assert InputMode.NORMAL.value == "normal"
        assert InputMode.FOCUS_MESSAGE.value == "focus"
        assert InputMode.DETAIL_VIEW.value == "detail"
        assert InputMode.COPY_MODE.value == "copy"
        assert InputMode.NATIVE_SELECT.value == "native"


class TestInputRouter:
    def test_default_mode(self):
        from ui.input_router import InputRouter
        router = InputRouter()
        assert router.mode.value == "normal"

    def test_set_mode(self):
        from ui.input_router import InputMode, InputRouter
        router = InputRouter()
        router.set_mode(InputMode.FOCUS_MESSAGE)
        assert router.mode == InputMode.FOCUS_MESSAGE

    def test_mode_change_callback(self):
        from ui.input_router import InputMode, InputRouter
        router = InputRouter()
        changes = []
        router.on_mode_change(lambda m: changes.append(m))
        router.set_mode(InputMode.DETAIL_VIEW)
        assert changes == [InputMode.DETAIL_VIEW]

    def test_dispatch_finds_handler(self):
        from ui.input_router import InputMode, InputRouter
        router = InputRouter()
        called = []
        router.add_handler("up", InputMode.NORMAL, lambda: called.append("up") or True)
        consumed = router.dispatch("up")
        assert consumed
        assert called == ["up"]

    def test_dispatch_mode_filtering(self):
        from ui.input_router import InputMode, InputRouter
        router = InputRouter()
        normal_called = []
        focus_called = []
        # Register NORMAL before FOCUS
        router.add_handler("c", InputMode.NORMAL, lambda: normal_called.append("n") or True)
        router.add_handler("c", InputMode.FOCUS_MESSAGE, lambda: focus_called.append("f") or True)

        # Normal mode: NORMAL handler fires (no mode-specific match)
        router.dispatch("c")
        assert normal_called == ["n"]
        assert focus_called == []

        # Focus mode: FOCUS handler fires first (exact match)
        router.set_mode(InputMode.FOCUS_MESSAGE)
        router.dispatch("c")
        assert normal_called == ["n"]   # NORMAL not fired
        assert focus_called == ["f"]

    def test_dispatch_no_match(self):
        from ui.input_router import InputRouter
        router = InputRouter()
        consumed = router.dispatch("x")
        assert not consumed

    def test_remove_handlers(self):
        from ui.input_router import InputMode, InputRouter
        router = InputRouter()
        called = []
        router.add_handler("d", InputMode.NORMAL, lambda: called.append("d") or True)
        router.remove_handlers("d")
        consumed = router.dispatch("d")
        assert not consumed
