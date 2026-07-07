"""
TDD tests for Markdown Renderer (ui/markdown_renderer.py)
"""
from __future__ import annotations

from ui.markdown_renderer import clear_cache, render_markdown


class TestMarkdownRenderer:
    def test_plain_text(self):
        result = render_markdown("Hello world")
        assert len(result) >= 1
        assert any("Hello world" in t for _, t in result)

    def test_bold(self):
        result = render_markdown("**bold text**")
        has_bold = any(s == 'bold' for s, _ in result)
        assert has_bold

    def test_italic(self):
        result = render_markdown("*italic text*")
        has_italic = any(s == 'italic' for s, _ in result)
        assert has_italic

    def test_inline_code(self):
        result = render_markdown("some `inline code` here")
        has_inline = any('inline code' in t for _, t in result)
        assert has_inline

    def test_header(self):
        result = render_markdown("# Main Title")
        has_bold_underline = any('bold' in s and 'underline' in s for s, _ in result)
        assert has_bold_underline

    def test_subheader(self):
        result = render_markdown("## Subtitle")
        has_bold = any('bold' in s for s, _ in result)
        assert has_bold

    def test_list(self):
        result = render_markdown("- Item 1\n- Item 2\n- Item 3")
        items = [t for _, t in result if 'Item' in t]
        assert len(items) >= 3

    def test_code_block(self):
        result = render_markdown("```python\nx = 1\nprint(x)\n```")
        # Should have Pygments-styled fragments (non-empty styles)
        styled = [s for s, _ in result if s]
        assert len(styled) > 0, "Code block should have syntax highlights"

    def test_code_block_cache(self):
        code = "```python\nprint('hello')\n```"
        r1 = render_markdown(code)
        r2 = render_markdown(code)
        assert r1 == r2, "Cached result should be identical"

    def test_blockquote(self):
        result = render_markdown("> quoted text")
        assert any("quoted text" in t for _, t in result)

    def test_complex_document(self):
        doc = """# Header
## Subheader

This has **bold** and *italic* and `code`.

```python
def hello(name):
    return f'Hello {name}'
```

> A blockquote.

- List item 1
- List item 2
"""
        result = render_markdown(doc)
        assert len(result) > 10, "Complex doc should produce many fragments"

    def test_no_ansi_codes(self):
        """Pygments output should NOT contain raw ANSI escape codes."""
        result = render_markdown("```python\nx = 1\n```")
        for style, text in result:
            assert '\x1b[' not in text, f"ANSI code found: {repr(text[:50])}"

    def test_clear_cache(self):
        clear_cache()  # Should not raise
        # Still works after cache clear
        result = render_markdown("**bold**")
        assert len(result) > 0
