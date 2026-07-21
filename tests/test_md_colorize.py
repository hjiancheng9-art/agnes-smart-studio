"""Tests for markdown syntax highlighting in plain text REPL."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.colors import ANSI


def test_inline_code_has_yellow_color():
    """Inline code `code` should be wrapped in yellow ANSI."""
    from crux_repl import _md_colorize

    c = ANSI
    result = _md_colorize("Use `code` here", c)
    assert c["yellow"] in result, "Inline code should have yellow color"
    assert "code" in result, "Code content should be present"


def test_bold_uses_bold_ansi():
    """**bold** should use bold ANSI escape."""
    from crux_repl import _md_colorize

    c = ANSI
    result = _md_colorize("This is **bold** text", c)
    assert c["bold"] in result, "Bold should use ANSI bold"
    assert "bold" in result, "Text content should be present"


def test_italic_uses_italic_ansi():
    """*italic* should use italic ANSI escape."""
    from crux_repl import _md_colorize

    c = ANSI
    result = _md_colorize("This is *italic* text", c)
    assert c["italic"] in result, "Italic should use ANSI italic"
    assert "italic" in result, "Text content should be present"


def test_link_has_underline_and_blue():
    """[text](url) should show text with underline+blue."""
    from crux_repl import _md_colorize

    c = ANSI
    result = _md_colorize("Click [here](http://example.com)", c)
    assert c["underline"] in result, "Link should have underline"
    assert c["blue"] in result, "Link should have blue color"
    assert "here" in result, "Link text should be visible"


def test_plain_text_not_modified():
    """Plain text without markdown should be unchanged."""
    from crux_repl import _md_colorize

    result = _md_colorize("Hello world", ANSI)
    assert result == "Hello world", "Plain text should not be modified"


def test_base_color_restored():
    """After each highlight, base color c["ai"] should be restored."""
    from crux_repl import _md_colorize

    c = ANSI
    result = _md_colorize("`a` normal `b`", c)
    assert result.count(c["ai"]) == 2, "Base color restored after each highlight"
