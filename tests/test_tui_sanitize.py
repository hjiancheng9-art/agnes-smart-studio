"""Tests for input sanitizer and _shorten in tui_v2.py."""

import pytest


class TestSanitizeInput:
    @pytest.fixture
    def sanitize(self):
        from ui.tui_v2 import TuiAppV2

        return TuiAppV2._sanitize_input

    def test_ansi_colors_stripped(self, sanitize):
        assert sanitize("\033[31mError\033[0m: something") == "Error: something"

    def test_ansi_bold_stripped(self, sanitize):
        assert sanitize("\033[1;31mCRITICAL\033[0m failure") == "CRITICAL failure"

    def test_osc_sequences_stripped(self, sanitize):
        assert sanitize("\033]0;window title\007real content") == "real content"

    def test_null_bytes_stripped(self, sanitize):
        assert sanitize("hello\x00world") == "helloworld"

    def test_bell_stripped(self, sanitize):
        assert sanitize("alert\x07message") == "alertmessage"

    def test_mixed_dangerous_chars(self, sanitize):
        dirty = "\033[1;31mERROR\033[0m: \x00build failed\x07 at line 42"
        assert sanitize(dirty) == "ERROR: build failed at line 42"

    def test_clean_text_unchanged(self, sanitize):
        assert sanitize("normal text 123") == "normal text 123"

    def test_empty_string(self, sanitize):
        assert sanitize("") == ""

    def test_only_dangerous_chars(self, sanitize):
        assert sanitize("\033[31m\x00\x07") == ""

    def test_compiler_error_output(self, sanitize):
        """Simulate pasting a real compiler/tool error message."""
        compiler_output = (
            "\033[1;31merror\033[0m: \033[1mexpected ';'\033[0m after declaration\n"
            "\033[1;36m  -->\033[0m src/main.rs:42:13\n"
            "\033[1;36m   |\033[0m\n"
            "\033[1;36m42 |\033[0m     let x = 5\n"
            "\033[1;36m   |\033[0m             \033[1;31m^\033[0m expected ';'\n"
        )
        result = sanitize(compiler_output)
        assert "error" in result
        assert "\033" not in result
        assert "src/main.rs:42:13" in result

    def test_preserves_unicode(self, sanitize):
        assert sanitize("你好世界 🎉 café") == "你好世界 🎉 café"

    def test_preserves_file_paths(self, sanitize):
        path = r"C:\Users\test\project\src\main.py:42:13"
        assert sanitize(path) == path


class TestShorten:
    @pytest.fixture
    def shorten(self):
        from ui.tui_v2 import TuiAppV2

        return TuiAppV2._shorten

    def test_short_text(self, shorten):
        assert shorten("hello") == "hello"

    def test_long_text_truncated(self, shorten):
        result = shorten("x" * 100, limit=20)
        assert len(result) <= 21
        assert result.endswith("…")

    def test_newlines_replaced(self, shorten):
        assert "\n" not in shorten("hello\nworld")
        assert "\r" not in shorten("hello\rworld")
