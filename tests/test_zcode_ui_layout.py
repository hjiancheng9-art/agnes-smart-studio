"""TDD RED phase — UI layout, activity log, and rendering tests for TuiApp."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.output import DummyOutput

from ui.status_bar import StatusBar
from ui.tui_app import TuiApp


# ── Fixtures ──────────────────────────────────────────────────


def _make_mock_session():
    """Create a mock ChatSession with minimal attributes."""
    session = MagicMock()
    session.model = "deepseek-v4-pro"
    session.messages = []
    session.send_stream = MagicMock(return_value=iter([]))
    return session


def _make_mock_cli():
    """Create a mock CruxCLI."""
    cli = MagicMock()
    cli.dispatch = MagicMock(return_value=True)
    return cli


def _make_tui(**kwargs):
    """Create a TuiApp with mocked dependencies. Uses DummyOutput to avoid
    requiring a real Windows console during tests."""
    session = kwargs.pop("session", _make_mock_session())
    cli = kwargs.pop("cli", _make_mock_cli())
    startup_banner = kwargs.pop("startup_banner", "")
    with patch("prompt_toolkit.output.defaults.create_output", return_value=DummyOutput()):
        return TuiApp(session=session, cli=cli, startup_banner=startup_banner, **kwargs)


# ── Activity Log Tests ───────────────────────────────────────


class TestActivityLogStartsEmpty:
    """test_activity_log_starts_empty — New TuiApp has empty _activity_log."""

    def test_activity_log_starts_empty(self):
        tui = _make_tui()
        assert tui._activity_log == []
        assert len(tui._activity_log) == 0


class TestActivityLogPersistsAfterThinking:
    """test_activity_log_persists_after_thinking — Activity log persists across
    thinking state changes.
    """

    def test_activity_log_persists_after_thinking(self):
        tui = _make_tui()
        tui._activity_log.append(("●", "class:message-tool", "test entry"))
        tui._thinking = True
        assert len(tui._activity_log) == 1
        tui._thinking = False
        assert len(tui._activity_log) == 1
        assert tui._activity_log[0] == ("●", "class:message-tool", "test entry")


class TestActivityLogClearedOnNewMessage:
    """test_activity_log_cleared_on_new_message — _on_accept clears the activity log
    when a new user message is sent.
    """

    def test_activity_log_cleared_on_new_message(self):
        tui = _make_tui()
        tui._activity_log.append(("●", "class:message-tool", "previous tool"))
        tui._activity_log.append(("✓", "class:success", "previous done"))
        assert len(tui._activity_log) == 2
        # Simulate user typing a message and pressing enter
        tui.input_buffer.text = "hello world"
        tui._on_accept(tui.input_buffer)
        assert tui._activity_log == []

    def test_activity_log_not_cleared_on_empty_message(self):
        tui = _make_tui()
        tui._activity_log.append(("●", "class:message-tool", "previous tool"))
        tui.input_buffer.text = ""
        tui._on_accept(tui.input_buffer)
        # Empty message should not clear the log
        assert len(tui._activity_log) == 1


# ── Layout Tests ─────────────────────────────────────────────


class TestLayoutHasFiveZones:
    """test_layout_has_five_zones — _make_app() returns Application with HSplit root
    containing: message_pane, separator, activity_window, input, status_bar.
    """

    def test_layout_has_five_zones(self):
        tui = _make_tui()
        app = tui._make_app()
        assert isinstance(app, Application)
        root = app.layout.container
        assert isinstance(root, HSplit)
        children = root.children
        assert len(children) == 5, f"Expected 5 zones, got {len(children)}"

        # Zone 0: message_pane
        assert children[0] is tui.message_pane.pane

        # Zone 1: separator (Window with FormattedTextControl)
        assert isinstance(children[1], Window)

        # Zone 2: activity_window (Window with FormattedTextControl)
        assert isinstance(children[2], Window)

        # Zone 3: input (Window with BufferControl)
        assert isinstance(children[3], Window)
        assert isinstance(children[3].content, BufferControl)

        # Zone 4: status_bar (Window with FormattedTextControl)
        assert isinstance(children[4], Window)

    def test_input_window_has_buffer_control(self):
        tui = _make_tui()
        app = tui._make_app()
        root = app.layout.container
        input_window = root.children[3]
        assert isinstance(input_window.content, BufferControl)
        assert input_window.content.buffer is tui.input_buffer


class TestSeparatorVisibleWhenActivity:
    """test_separator_visible_when_activity — separator height reflects activity log."""

    def test_separator_visible_when_activity(self):
        tui = _make_tui()
        app = tui._make_app()
        root = app.layout.container
        separator = root.children[1]

        # No activity → height 0
        tui._activity_log.clear()
        assert separator.height() == 0

    def test_separator_hidden_when_empty(self):
        tui = _make_tui()
        app = tui._make_app()
        root = app.layout.container
        separator = root.children[1]

        # Activity → height 1
        tui._activity_log.append(("●", "class:message-tool", "running tool"))
        assert separator.height() == 1


class TestActivityWindowHeight:
    """test_activity_window_height — activity window height reflects log size."""

    def test_activity_window_zero_when_empty(self):
        tui = _make_tui()
        app = tui._make_app()
        root = app.layout.container
        activity_window = root.children[2]
        tui._activity_log.clear()
        assert activity_window.height() == 0

    def test_activity_window_grows_with_log(self):
        tui = _make_tui()
        app = tui._make_app()
        root = app.layout.container
        activity_window = root.children[2]
        tui._activity_log.append(("●", "class:message-tool", "entry1"))
        assert activity_window.height() == 1
        tui._activity_log.append(("●", "class:message-tool", "entry2"))
        assert activity_window.height() == 2

    def test_activity_window_capped_at_eight(self):
        tui = _make_tui()
        app = tui._make_app()
        root = app.layout.container
        activity_window = root.children[2]
        for i in range(20):
            tui._activity_log.append(("●", "class:message-tool", f"entry{i}"))
        assert activity_window.height() == 8


# ── Prompt Tests ─────────────────────────────────────────────


class TestPromptShowsThinkingIndicator:
    """test_prompt_shows_thinking_indicator — prompt reflects _thinking state."""

    def test_prompt_shows_star_when_thinking(self):
        tui = _make_tui()
        tui._thinking = True
        app = tui._make_app()
        root = app.layout.container
        input_window = root.children[3]
        ctrl = input_window.content
        # The BeforeInput processor's text function contains the prompt
        processors = ctrl.input_processors or ctrl.processors
        for p in processors:
            if hasattr(p, "text") and callable(p.text):
                result = p.text()
                assert "*" in result, f"Expected '*' in prompt, got: {result!r}"
                assert ">" not in result
                break

    def test_prompt_shows_gt_when_idle(self):
        tui = _make_tui()
        tui._thinking = False
        app = tui._make_app()
        root = app.layout.container
        input_window = root.children[3]
        ctrl = input_window.content
        processors = ctrl.input_processors or ctrl.processors
        for p in processors:
            if hasattr(p, "text") and callable(p.text):
                result = p.text()
                assert ">" in result, f"Expected '>' in prompt, got: {result!r}"
                break


# ── Status Bar Tests ─────────────────────────────────────────


class TestStatusBarRendersModelAndCwd:
    """test_status_bar_renders_model_and_cwd — StatusBar.render() returns
    FormattedText with model name in first fragment.
    """

    def test_status_bar_renders_model_in_first_fragment(self):
        bar = StatusBar(model="deepseek-v4-pro", cwd=Path("/tmp/test"))
        result = bar.render()
        assert isinstance(result, FormattedText)
        fragments = list(result._formatted_text if hasattr(result, "_formatted_text") else result.__iter__())
        # First fragment should contain the model name
        assert len(fragments) > 0
        first_style, first_text = fragments[0]
        assert "deepseek-v4-pro" in first_text

    def test_status_bar_renders_model_and_cwd(self):
        bar = StatusBar(model="test-model", cwd=Path("/tmp/test"))
        result = bar.render()
        fragments = list(result.__iter__())
        # Should have at least 1 fragment
        assert len(fragments) >= 1
        # First non-empty fragment should contain model
        texts = [t for _, t in fragments if t.strip()]
        assert any("test-model" in t for t in texts), f"No fragment with model: {texts}"


class TestStatusBarThinking:
    """test_status_bar_thinking — thinking indicator appears in status bar."""

    def test_status_bar_shows_thinking(self):
        bar = StatusBar(model="test-model", cwd=Path.cwd())
        bar.set_thinking(True)
        result = bar.render()
        fragments = list(result.__iter__())
        texts = [t for _, t in fragments if t.strip()]
        assert any("thinking" in t for t in texts)

    def test_status_bar_no_thinking_when_idle(self):
        bar = StatusBar(model="test-model", cwd=Path.cwd())
        bar.set_thinking(False)
        result = bar.render()
        fragments = list(result.__iter__())
        texts = [t for _, t in fragments if t.strip()]
        assert not any("thinking" in t for t in texts)


# ── Activity Content Rendering ───────────────────────────────


class TestActivityLogContent:
    """test_activity_log_content — FormattedText correctly renders log entries."""

    def test_activity_log_entries_formatted(self):
        tui = _make_tui()
        tui._activity_log.append(("●", "class:message-tool", "executing task"))
        tui._activity_log.append(("✓", "class:success", "task done"))

        app = tui._make_app()
        root = app.layout.container
        activity_window = root.children[2]
        ctrl = activity_window.content

        # Get rendered content
        if hasattr(ctrl, "get_formatted_text"):
            result = ctrl.get_formatted_text()
        else:
            result = ctrl.text()

        assert isinstance(result, FormattedText)
        fragments = list(result.__iter__() if hasattr(result, "__iter__") else [])
        texts = [t for _, t in fragments if t.strip()]
        assert any("executing task" in t for t in texts)
        assert any("task done" in t for t in texts)
