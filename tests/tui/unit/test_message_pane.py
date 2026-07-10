"""Tests for message_pane.py — message rendering, scroll, rich content."""
import pytest


class TestMessagePane:
    """MessagePane manages the chat message buffer."""

    @pytest.fixture
    def pane(self):
        from ui.message_pane import MessagePane
        return MessagePane()

    def test_creation(self, pane):
        assert pane is not None

    def test_append_message(self, pane):
        try:
            pane.append_message("user", "Hello world")
        except Exception as e:
            pytest.fail(f"append_message raised: {e}")

    def test_append_long(self, pane):
        try:
            pane.append_message("assistant", "x" * 10000)
        except Exception as e:
            pytest.fail(f"long message raised: {e}")

    def test_append_chinese(self, pane):
        try:
            pane.append_message("user", "你好世界！测试。" * 50)
        except Exception as e:
            pytest.fail(f"Chinese raised: {e}")

    def test_append_markdown(self, pane):
        try:
            pane.append_message("assistant", "## Title\n**bold**\n```py\nx=1\n```")
        except Exception as e:
            pytest.fail(f"Markdown raised: {e}")

    def test_append_emoji(self, pane):
        try:
            pane.append_message("user", "🔥🚀 Testing 🎉")
        except Exception as e:
            pytest.fail(f"Emoji raised: {e}")

    def test_messages_attribute(self, pane):
        assert pane.line_count >= 0
