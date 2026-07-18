"""Snapshot tests for TUI rendering — syrupy captures output, detects regressions.

First run:  pytest tests/tui/snapshot/ --snapshot-update  (generate baselines)
Then:       pytest tests/tui/snapshot/                  (verify against baselines)
"""

from __future__ import annotations

import pytest

# ═══════════════════════════════════════════════════════════════
# terminal_splash — logo, borders, status lamps (pure functions)
# ═══════════════════════════════════════════════════════════════


class TestSplashComponents:
    """Snapshot pure rendering functions from terminal_splash."""

    def test_logo_lines_snapshot(self, snapshot):
        from ui.terminal_splash import build_logo_lines

        lines = build_logo_lines()
        assert "\n".join(lines) == snapshot

    def test_border_line_default(self, snapshot):
        from ui.terminal_splash import build_border_line

        assert build_border_line() == snapshot

    def test_border_line_custom(self, snapshot):
        from ui.terminal_splash import build_border_line

        assert build_border_line(char="─", top=False) == snapshot

    def test_scanline(self, snapshot):
        from ui.terminal_splash import build_scanline

        assert build_scanline() == snapshot

    @pytest.mark.parametrize(
        ("label", "on_state"),
        [
            ("Python", True),
            ("Git", False),
            ("API", True),
        ],
    )
    def test_status_lamp(self, snapshot, label, on_state):
        from ui.terminal_splash import _make_status_lamp

        assert _make_status_lamp(label, on_state) == snapshot

    @pytest.mark.parametrize("label", ["CRUX", "DEEPSEEK", "QWEN-3.6"])
    def test_mode_tag(self, snapshot, label):
        from ui.terminal_splash import _mode_tag

        assert _mode_tag(label, "primary") == snapshot


# ═══════════════════════════════════════════════════════════════
# msg_prefix — message role prefix formatting
# ═══════════════════════════════════════════════════════════════


class TestMsgPrefix:
    """Snapshot message prefix formatting."""

    @pytest.mark.parametrize("msg_type", ["user", "assistant", "system", "tool", "error", "warning"])
    def test_prefix_compact(self, snapshot, msg_type):
        from ui.msg_prefix import get_prefix

        assert get_prefix(msg_type, "compact") == snapshot

    @pytest.mark.parametrize("msg_type", ["user", "assistant", "error"])
    def test_prefix_full(self, snapshot, msg_type):
        from ui.msg_prefix import get_prefix

        assert get_prefix(msg_type, "full") == snapshot


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
