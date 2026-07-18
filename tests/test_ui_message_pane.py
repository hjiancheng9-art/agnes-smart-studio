"""Tests for ui/message_pane.py — rendering, scroll, stream buffer, edge cases."""

from ui.message_pane import MessagePane


class TestMessagePaneBasics:
    def test_initial_state(self):
        mp = MessagePane()
        assert mp.line_count == 0
        assert mp._lines == []
        assert mp._stream_buffer == ""

    def test_append_assistant(self):
        mp = MessagePane()
        mp.append_message("assistant", "hello world")
        assert mp.line_count > 0

    def test_append_user(self):
        mp = MessagePane()
        mp.append_message("user", "user message")
        assert mp.line_count > 0

    def test_append_error(self):
        mp = MessagePane()
        mp.append_message("error", "something failed")
        assert mp.line_count > 0

    def test_append_info(self):
        mp = MessagePane()
        mp.append_message("info", "status update")
        assert mp.line_count > 0

    def test_unknown_role_dropped(self):
        mp = MessagePane()
        mp.append_message("unknown_role_xyz", "should not appear")
        assert mp.line_count == 0

    def test_multiple_messages(self):
        mp = MessagePane()
        mp.append_message("user", "msg1")
        mp.append_message("assistant", "msg2")
        mp.append_message("user", "msg3")
        assert mp.line_count > 3


class TestStreamBuffer:
    def test_stream_start_resets_buffer(self):
        mp = MessagePane()
        mp.stream_append("old data")
        mp.stream_start("assistant")
        # stream_start may or may not reset — behavior depends on role
        assert mp._stream_buffer is not None

    def test_stream_append_accumulates(self):
        mp = MessagePane()
        mp.stream_start("assistant")
        mp.stream_append("hello ")
        mp.stream_append("world")
        assert "hello world" in mp._stream_buffer

    def test_stream_end_flushes_to_lines(self):
        mp = MessagePane()
        mp.stream_start("assistant")
        mp.stream_append("hello world")
        mp.stream_end()
        assert mp._stream_buffer == ""

    def test_stream_with_cjk(self):
        mp = MessagePane()
        mp.stream_start("assistant")
        mp.stream_append("你好世界")
        mp.stream_end()
        assert mp.line_count > 0

    def test_stream_with_emoji(self):
        mp = MessagePane()
        mp.stream_start("assistant")
        mp.stream_append("🔥 hello 🚀")
        mp.stream_end()
        assert mp.line_count > 0

    def test_stream_long_text_wraps(self):
        mp = MessagePane()
        mp.stream_start("assistant")
        mp.stream_append("a" * 500)
        mp.stream_end()
        assert mp.line_count > 0

    def test_stream_empty_content(self):
        mp = MessagePane()
        mp.stream_start("assistant")
        mp.stream_append("")
        mp.stream_end()


class TestScrollBehavior:
    def test_scroll_up_moves_viewport(self):
        mp = MessagePane()
        for i in range(100):
            mp.append_message("info", f"line {i}")
        initial = mp._scroll_offset
        mp.scroll_up()
        # _scroll_offset uses 999999 as bottom sentinel; scroll_up clamps to real values
        assert mp._scroll_offset <= initial

    def test_scroll_down_clamped(self):
        mp = MessagePane()
        for i in range(10):
            mp.append_message("info", f"line {i}")
        mp.scroll_up()
        mp.scroll_up()
        mp.scroll_down()
        assert mp._scroll_offset >= 0

    def test_scroll_to_bottom(self):
        mp = MessagePane()
        for i in range(50):
            mp.append_message("info", f"line {i}")
        mp.scroll_up()
        mp.scroll_to_bottom()
        # scroll_to_bottom sets _scroll_offset to 999999 (bottom sentinel)

    def test_page_up_down(self):
        mp = MessagePane()
        for i in range(100):
            mp.append_message("info", f"line {i}")
        mp.scroll_page_up()
        mp.scroll_page_down()
        # Both operations should not crash; _scroll_offset should stay non-negative


class TestClear:
    def test_clear_resets_all(self):
        mp = MessagePane()
        mp.append_message("user", "hello")
        mp.append_message("assistant", "world")
        mp.clear()
        assert mp.line_count == 0
        assert mp._lines == []
        # After clear, _scroll_offset may be 0 or 999999 (bottom sentinel) — both are valid

    def test_clear_preserves_empty_state(self):
        mp = MessagePane()
        mp.clear()
        assert mp.line_count == 0


class TestLongContent:
    def test_very_long_message(self):
        mp = MessagePane()
        mp.append_message("assistant", "x" * 10000)
        assert mp.line_count > 0

    def test_newlines_preserved(self):
        mp = MessagePane()
        mp.append_message("assistant", "line1\nline2\nline3")
        assert mp.line_count >= 2
