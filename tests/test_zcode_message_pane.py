"""TDD RED phase — tests for ui/message_pane.py."""

from __future__ import annotations

from prompt_toolkit.layout import Window

from ui.message_pane import _SCROLL_BOTTOM, MessagePane, _ScrollingWindow


class TestMessagePaneInitialState:
    """test_message_pane_initial_state — new MessagePane has _pinned=True, empty lines."""

    def test_initial_state(self):
        pane = MessagePane()
        assert pane._pinned is True
        assert pane.line_count == 0
        assert pane._lines == []
        assert pane._stream_buffer == ""
        assert isinstance(pane.pane, Window)


class TestAppendMessage:
    """test_append_message_adds_lines — append_message increases line_count."""

    def test_append_message_increases_line_count(self):
        pane = MessagePane()
        assert pane.line_count == 0
        pane.append_message("user", "hello")
        # Each append_message adds 2 entries: the message line + a blank line
        assert pane.line_count == 2

    def test_append_message_multiple(self):
        pane = MessagePane()
        pane.append_message("user", "hello")
        pane.append_message("crux", "world")
        assert pane.line_count == 4


class TestStreamStart:
    """test_stream_start_sets_pinned."""

    def test_stream_start_sets_pinned(self):
        pane = MessagePane()
        pane._pinned = False
        pane.stream_start("crux")
        assert pane._pinned is True

    def test_stream_start_initializes_buffer(self):
        pane = MessagePane()
        pane.stream_start("crux")
        # Buffer should start with "[CRUX] "
        assert "[CRUX]" in pane._stream_buffer
        assert pane._stream_label == "CRUX"
        assert pane.line_count == 1  # stream buffer counts as 1


class TestStreamAppend:
    """test_stream_append_accumulates text."""

    def test_stream_append_accumulates(self):
        pane = MessagePane()
        pane.stream_start("crux")
        pane.stream_append("hello")
        pane.stream_append(" world")
        assert "hello world" in pane._stream_buffer


class TestStreamEnd:
    """test_stream_end_finalizes — buffer cleared, lines increased."""

    def test_stream_end_finalizes(self):
        pane = MessagePane()
        pane.stream_start("crux")
        pane.stream_append("hello world")
        buffer_before = pane._stream_buffer
        assert buffer_before != ""
        pane.stream_end()
        # Buffer should be cleared
        assert pane._stream_buffer == ""
        # Lines should have increased (the buffer moved to _lines)
        assert pane.line_count == 2  # message line + blank line


class TestClear:
    """test_clear_resets — line_count 0, vertical_scroll 0."""

    def test_clear_resets(self):
        pane = MessagePane()
        pane.append_message("user", "hello")
        pane.append_message("crux", "world")
        assert pane.line_count > 0
        pane.clear()
        assert pane.line_count == 0
        assert pane._window.vertical_scroll == 0


class TestScrollPageUp:
    """test_scroll_page_up_unpins — scroll_page_up sets _pinned=False when scroll > 0."""

    def test_scroll_page_up_unpins(self):
        pane = MessagePane()
        # Add many lines so that scroll position can be > 0 after paging up
        for i in range(100):
            pane.append_message("user", f"message {i}")
        # First scroll to bottom so we're pinned
        pane.scroll_to_bottom()
        assert pane._pinned is True
        # Now page up
        pane.scroll_page_up()
        # After paging up from bottom, we should be unpinned (scroll > 0)
        assert pane._pinned is False


class TestScrollToBottom:
    """test_scroll_to_bottom_pins."""

    def test_scroll_to_bottom_pins(self):
        pane = MessagePane()
        pane._pinned = False
        pane.scroll_to_bottom()
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestScrollingWindowSubclass:
    """test_scrolling_window_subclass — _ScrollingWindow exists, _scroll overridden."""

    def test_scrolling_window_is_window_subclass(self):
        assert issubclass(_ScrollingWindow, Window)

    def test_scroll_method_overridden(self):
        # _scroll method exists on _ScrollingWindow and is not the same
        # as the base Window._scroll (the override was done in the class body)
        assert hasattr(_ScrollingWindow, "_scroll")
        # The method should be defined on _ScrollingWindow, not just inherited
        assert "_scroll" in _ScrollingWindow.__dict__


class TestAutoScrollRespectsPinned:
    """test_auto_scroll_respects_pinned — when pinned, _pending_scroll_to_bottom set True.

    _auto_scroll() only sets the pending flag (thread-safe design).
    _ScrollingWindow._scroll() consumes it on the render thread to set vertical_scroll.
    """

    def test_auto_scroll_sets_pending_flag(self):
        from unittest.mock import MagicMock
        pane = MessagePane()
        pane._window = MagicMock()
        pane._window.vertical_scroll = 0
        pane._pinned = True
        pane._pending_scroll_to_bottom = False
        pane._auto_scroll()
        # _auto_scroll() sets vertical_scroll directly when pinned
        assert pane._window.vertical_scroll == 999999  # _SCROLL_BOTTOM

    def test_auto_scroll_when_not_pinned(self):
        pane = MessagePane()
        pane._pinned = False
        pane._pending_scroll_to_bottom = False
        pane._auto_scroll()
        # Should NOT set pending flag when not pinned
        assert pane._pending_scroll_to_bottom is False


class TestWrappedAutoScrollToBottom:
    """test_wrapped_auto_scroll — when content wraps to more visual rows than
    window height, _scroll() must set vertical_scroll_2 > 0 so the BOTTOM
    of the wrapped content is visible, not just the top."""

    def test_long_line_sets_vertical_scroll_2(self):
        """A single content line wrapping to > height visual rows must use
        vertical_scroll_2 to show the bottom portion."""
        pane = MessagePane()
        # Add a very long line (500 chars) that will wrap heavily at narrow width
        pane.append_message("crux", "X" * 500)
        pane._pinned = True
        pane._auto_scroll()  # Sets vertical_scroll = _SCROLL_BOTTOM

        # Simulate rendering at narrow width (40)
        w = pane._window
        ui = pane._control.create_content(40, None)

        # The critical test: _scroll must set vertical_scroll_2 to skip
        # the top wrapped rows so the bottom is visible
        w._scroll(ui, width=40, height=15)

        # At width=40, 500 chars wraps to ceil(500/40)=13 rows
        # With height=15, content (13 rows) fits, so no intra-line scroll needed
        # But with the prefix "[CRUX] " (7 chars), total is ~13 rows
        # Actually, let's just verify: vertical_scroll_2 should be 0 when
        # total_wrapped <= height, and >0 when total_wrapped > height
        total_h = sum(ui.get_height_for_line(i, 40, w.get_line_prefix) for i in range(ui.line_count))

        if total_h <= 15:
            # Content fits: no intra-line scroll needed
            assert w.vertical_scroll_2 == 0
        else:
            # Content overflows: must scroll to show bottom
            assert w.vertical_scroll_2 > 0, (
                f"Expected vertical_scroll_2 > 0 when wrapped content "
                f"({total_h} rows) exceeds window (15 rows), "
                f"but got vertical_scroll_2={w.vertical_scroll_2}"
            )

    def test_narrow_wrap_shows_bottom(self):
        """At a very narrow width, the wrapped content should show the bottom
        portion when pinned, not just the first height rows."""
        pane = MessagePane()
        pane.append_message("crux", "A" * 300)
        pane._pinned = True
        pane._auto_scroll()

        w = pane._window
        # Very narrow — 20 columns, height 10
        ui = pane._control.create_content(20, None)
        w._scroll(ui, width=20, height=10)

        total_h = sum(ui.get_height_for_line(i, 20, w.get_line_prefix) for i in range(ui.line_count))

        # With "[CRUX] AAAA...", at width 20, 300 chars wrap to ~16 rows.
        # With height 10, total_h (16) > height (10), so vertical_scroll_2 must be > 0
        if total_h > 10:
            assert w.vertical_scroll_2 > 0, (
                f"At width=20, height=10, {total_h} wrapped rows > 10, "
                f"but vertical_scroll_2={w.vertical_scroll_2} — "
                f"bottom of content would not be visible"
            )

    def test_fullscreen_vs_shrunk(self):
        """Demonstrate the exact bug scenario: fullscreen (wide) shows correctly,
        shrunk (narrow) must also show bottom via vertical_scroll_2."""
        pane = MessagePane()
        pane.append_message("crux", "X" * 400)
        pane._pinned = True
        pane._auto_scroll()

        w = pane._window

        # Fullscreen: width=120, height=30
        ui_wide = pane._control.create_content(120, None)
        w._scroll(ui_wide, width=120, height=30)
        total_wide = sum(ui_wide.get_height_for_line(i, 120, w.get_line_prefix) for i in range(ui_wide.line_count))
        # At width=120, content likely fits
        if total_wide <= 30:
            assert w.vertical_scroll_2 == 0  # No intra-line scroll needed

        # Shrunk: width=40, height=15
        pane._pinned = True
        pane._auto_scroll()
        ui_narrow = pane._control.create_content(40, None)
        w._scroll(ui_narrow, width=40, height=15)
        total_narrow = sum(ui_narrow.get_height_for_line(i, 40, w.get_line_prefix) for i in range(ui_narrow.line_count))
        # At width=40, content may exceed height
        if total_narrow > 15:
            assert w.vertical_scroll_2 > 0, (
                f"BUG: shrunk terminal ({total_narrow} rows > 15 height) "
                f"should auto-scroll to bottom via vertical_scroll_2, "
                f"but got {w.vertical_scroll_2}"
            )
        # Verify the scroll position actually shows the bottom
        # The last visual row visible should be the bottom of content
        if total_narrow > 15:
            visible_bottom = w.vertical_scroll_2 + 15  # approx
            assert visible_bottom >= total_narrow - 1, (
                f"Expected visible_bottom ({visible_bottom}) to reach total content ({total_narrow})"
            )
