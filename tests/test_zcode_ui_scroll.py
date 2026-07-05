"""TDD RED phase — tests for scroll state machine in ui/message_pane.py."""

from __future__ import annotations

from prompt_toolkit.layout import Window

from ui.message_pane import _SCROLL_BOTTOM, MessagePane, _ScrollingWindow


class TestNewPaneIsPinned:
    """test_new_pane_is_pinned — New MessagePane._pinned is True."""

    def test_new_pane_is_pinned(self):
        pane = MessagePane()
        assert pane._pinned is True


class TestAppendMessageAutoScrolls:
    """test_append_message_auto_scrolls — Append 50 messages, verify _pinned stays True
    and _auto_scroll sets vertical_scroll to _SCROLL_BOTTOM."""

    def test_append_message_auto_scrolls(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestScrollUpUnpins:
    """test_scroll_up_unpins — Append 50 messages, call scroll_up(), verify _pinned
    becomes False."""

    def test_scroll_up_unpins(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        # Should be at bottom, pinned
        assert pane._pinned is True
        pane.scroll_up()
        assert pane._pinned is False


class TestScrollUpThenDownToBottomRepins:
    """test_scroll_up_then_down_to_bottom_repins — Append 50 messages, scroll_up(),
    then scroll_to_bottom(), verify _pinned becomes True."""

    def test_scroll_up_then_down_to_bottom_repins(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        pane.scroll_up()
        assert pane._pinned is False
        pane.scroll_to_bottom()
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestScrollPageUpUnpins:
    """test_scroll_page_up_unpins — scroll_page_up() when not at top sets _pinned to False."""

    def test_scroll_page_up_unpins(self):
        pane = MessagePane()
        for i in range(100):
            pane.append_message("user", f"message {i}")
        pane.scroll_to_bottom()
        assert pane._pinned is True
        pane.scroll_page_up()
        assert pane._pinned is False


class TestScrollPageDownRepinsAtBottom:
    """test_scroll_page_down_repins_at_bottom — scroll_page_down() when at/near bottom
    sets _pinned to True."""

    def test_scroll_page_down_repins_at_bottom(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        # Manually set to near-bottom and unpinned
        pane._window.vertical_scroll = pane.line_count - pane._window_height() - 5
        pane._pinned = False
        pane.scroll_page_down()
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestScrollToTopAlwaysUnpins:
    """test_scroll_to_top_always_unpins — scroll_to_top() sets _pinned to False."""

    def test_scroll_to_top_always_unpins(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        pane._pinned = True
        pane.scroll_to_top()
        assert pane._pinned is False
        assert pane._window.vertical_scroll == 0


class TestScrollToBottomAlwaysPins:
    """test_scroll_to_bottom_always_pins — scroll_to_bottom() sets _pinned to True."""

    def test_scroll_to_bottom_always_pins(self):
        pane = MessagePane()
        pane._pinned = False
        pane.scroll_to_bottom()
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestStreamStartForcesPin:
    """test_stream_start_forces_pin — Even if _pinned=False, stream_start() resets
    _pinned to True."""

    def test_stream_start_forces_pin(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        pane.scroll_up()
        assert pane._pinned is False
        pane.stream_start("crux")
        assert pane._pinned is True


class TestScrollingWindowExists:
    """test_scrolling_window_exists — _ScrollingWindow class is defined and is subclass
    of Window."""

    def test_scrolling_window_is_defined(self):
        assert _ScrollingWindow is not None

    def test_scrolling_window_is_window_subclass(self):
        assert issubclass(_ScrollingWindow, Window)

    def test_scroll_method_overridden(self):
        assert "_scroll" in _ScrollingWindow.__dict__
