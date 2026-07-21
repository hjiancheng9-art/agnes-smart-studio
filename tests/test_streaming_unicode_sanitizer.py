"""Tests for utils/streaming_unicode_sanitizer.py — streaming surrogate repair."""

from utils.streaming_unicode_sanitizer import StreamingUnicodeSanitizer


class TestStreamingUnicodeSanitizer:
    """Tests for StreamingUnicodeSanitizer — stateful streaming unicode repair."""

    def test_clean_text_passes_through(self):
        s = StreamingUnicodeSanitizer()
        assert s.feed("hello world") == "hello world"
        assert s.feed("") == ""
        assert s.finish() == ""

    def test_lone_high_surrogate_replaced(self):
        s = StreamingUnicodeSanitizer()
        result = s.feed("bad \ud800 char")
        assert "\ud800" not in result
        assert "\ufffd" in result

    def test_lone_low_surrogate_replaced(self):
        s = StreamingUnicodeSanitizer()
        result = s.feed("bad \udfff char")
        assert "\udfff" not in result
        assert "\ufffd" in result

    def test_surrogate_pair_across_chunks(self):
        s = StreamingUnicodeSanitizer()
        out1 = s.feed("hello \ud83d")
        assert out1 == "hello "
        assert s._pending_high == "\ud83d"

        out2 = s.feed("\ude00 world")
        assert "\ud83d" not in out2
        assert "\ude00" not in out2
        assert "world" in out2
        assert s.repaired_count == 1

    def test_orphan_high_surrogate_at_finish(self):
        s = StreamingUnicodeSanitizer()
        out = s.feed("text \ud83d")
        assert "\ud83d" not in out
        assert s._pending_high == "\ud83d"

        flushed = s.finish()
        assert flushed == "\ufffd"
        assert s.repaired_count == 1

    def test_orphan_high_surrogate_across_chunks(self):
        s = StreamingUnicodeSanitizer()
        out1 = s.feed("pre \ud83d")
        assert out1 == "pre "

        out2 = s.feed("X rest")
        assert "\ufffd" in out2
        assert "X rest" in out2
        assert s.repaired_count == 1

    def test_finish_with_no_pending(self):
        s = StreamingUnicodeSanitizer()
        s.feed("clean text")
        assert s.finish() == ""
        assert s.repaired_count == 0

    def test_none_input_returns_empty(self):
        s = StreamingUnicodeSanitizer()
        assert s.feed(None) == ""

    def test_multiple_surrogate_pairs(self):
        s = StreamingUnicodeSanitizer()
        s.feed("\ud83d")
        s.feed("\ude00 \ud83d")
        s.feed("\ude0d end")
        assert s.repaired_count == 2

    def test_surrogate_pair_within_single_chunk(self):
        s = StreamingUnicodeSanitizer()
        emoji = "\ud83d\ude00"
        result = s.feed("hello " + emoji + " world")
        # The sanitizer joins the valid pair into the real character
        # and counts it as a repair (the pair was split-then-rejoined)
        assert "\ufffd" not in result
        assert s.repaired_count == 1
        assert len(result) > len("hello  world")  # emoji is present

    def test_high_then_another_high(self):
        s = StreamingUnicodeSanitizer()
        out1 = s.feed("\ud83d")
        assert out1 == ""
        out2 = s.feed("\ud83d")
        assert out2.count("\ufffd") == 1
        assert s._pending_high == "\ud83d"

    def test_static_is_high_surrogate(self):
        assert StreamingUnicodeSanitizer._is_high_surrogate(0xD800) is True
        assert StreamingUnicodeSanitizer._is_high_surrogate(0xDBFF) is True
        assert StreamingUnicodeSanitizer._is_high_surrogate(0xDC00) is False
        assert StreamingUnicodeSanitizer._is_high_surrogate(0x0041) is False

    def test_static_is_low_surrogate(self):
        assert StreamingUnicodeSanitizer._is_low_surrogate(0xDC00) is True
        assert StreamingUnicodeSanitizer._is_low_surrogate(0xDFFF) is True
        assert StreamingUnicodeSanitizer._is_low_surrogate(0xDBFF) is False

    def test_join_surrogate_pair_produces_correct_codepoint(self):
        result = StreamingUnicodeSanitizer._join_surrogate_pair(0xD83D, 0xDE00)
        assert result == "\U0001f600"
        assert ord(result) == 0x1F600
