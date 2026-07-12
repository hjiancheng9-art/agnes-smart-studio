"""Tests for ThinkingPanel in ui/widgets_v2.py."""

import pytest
import threading


class TestThinkingPanel:
    @pytest.fixture
    def panel(self):
        from ui.widgets_v2 import ThinkingPanel
        return ThinkingPanel()

    def test_initial_state(self, panel):
        assert not panel.visible
        assert not panel.content
        assert not panel._pinned

    def test_append_makes_visible(self, panel):
        panel.append("thinking...")
        assert panel.visible
        assert "thinking..." in panel.content

    def test_clear_hides_when_not_pinned(self, panel):
        panel.append("some thought")
        panel.clear()
        assert not panel.visible
        assert panel.content == ""

    def test_clear_keeps_when_pinned(self, panel):
        panel.toggle_pin()
        panel.append("important thought")
        panel.clear()
        assert panel.visible  # pinned, should stay visible

    def test_done_hides_when_not_pinned(self, panel):
        panel.append("transient thought")
        panel.done()
        assert not panel.visible

    def test_done_keeps_when_pinned(self, panel):
        panel.toggle_pin()
        panel.append("persistent thought")
        panel.done()
        assert panel.visible  # pinned

    def test_append_visible_race(self, panel):
        """append() sets _visible inside lock, not outside."""
        def racer():
            for _ in range(50):
                panel.append("x")
                panel.clear()

        threads = [threading.Thread(target=racer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # After all racers finish, state should be consistent
        after = panel.content
        after_visible = panel.visible
        if not after and not panel._pinned:
            assert not after_visible, f"visible={after_visible} but content empty"

    def test_content_cap(self, panel):
        """Content cap blocks FURTHER appends once limit is reached."""
        big = "x" * 200000
        panel.append(big)
        # First append goes through (cap checks BEFORE, and 0 < 131072)
        assert len(panel.content) == 200000
        # Second append should be blocked (200000 >= 131072)
        before = len(panel.content)
        panel.append("more")
        assert len(panel.content) == before  # blocked, no growth

    def test_toggle_pin(self, panel):
        assert not panel._pinned
        panel.toggle_pin()
        assert panel._pinned
        panel.toggle_pin()
        assert not panel._pinned

    def test_render_empty_when_invisible(self, panel):
        result = panel.render(80)
        assert len(result) == 0

    def test_render_shows_content(self, panel):
        panel.append("I am thinking deeply about this problem.")
        result = panel.render(80)
        assert len(result) > 0
        text = "".join(t for _, t in result)
        assert "I am thinking" in text

    def test_render_capped_lines(self, panel):
        """Render should cap visual lines at MAX_LINES."""
        many_lines = "\n".join(f"line {i}" for i in range(50))
        panel.append(many_lines)
        result = panel.render(80)
        text = "".join(t for _, t in result)
        # Should show tail, not head
        assert "line 49" in text
