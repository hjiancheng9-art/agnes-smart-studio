"""Snapshot tests for TUI rendering — syrupy captures output, detects regressions.

First run:  pytest tests/tui/snapshot/ --snapshot-update  (generate baselines)
Then:       pytest tests/tui/snapshot/                  (verify against baselines)
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
# markdown_renderer — inline markdown → rich text
# ═══════════════════════════════════════════════════════════════


class TestMarkdownRenderer:
    """Snapshot markdown-to-rich-text rendering."""

    def test_inline_code(self, snapshot):
        from ui.markdown_renderer import _render_inline

        assert _render_inline("use `function()` here") == snapshot

    def test_inline_bold(self, snapshot):
        from ui.markdown_renderer import _render_inline

        assert _render_inline("this is **important** text") == snapshot

    def test_inline_italic(self, snapshot):
        from ui.markdown_renderer import _render_inline

        assert _render_inline("this is *emphasized* text") == snapshot

    def test_inline_link(self, snapshot):
        from ui.markdown_renderer import _render_inline

        assert _render_inline("see [docs](https://example.com)") == snapshot

    def test_inline_mixed(self, snapshot):
        from ui.markdown_renderer import _render_inline

        assert _render_inline("`code` and **bold** and *italic*") == snapshot
