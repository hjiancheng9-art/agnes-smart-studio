"""TDD RED phase — stream processing tests for TuiApp._stream_response."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from prompt_toolkit.output import DummyOutput

from ui.tui_app import TuiApp

# ── Fixtures ──────────────────────────────────────────────────


def _make_mock_session(yields=None):
    """Create a mock ChatSession whose send_stream is a real function."""
    session = MagicMock()
    session.model = "deepseek-v4-pro"
    session.messages = []

    if yields is None:
        yields = []

    def _send_stream(user_text, image_url=None):
        yield from yields

    session.send_stream = _send_stream
    return session


def _make_mock_cli():
    """Create a mock CruxCLI."""
    cli = MagicMock()
    cli.dispatch = MagicMock(return_value=True)
    return cli


def _make_tui(session=None, cli=None):
    """Create a TuiApp with mocked dependencies."""
    if session is None:
        session = _make_mock_session()
    if cli is None:
        cli = _make_mock_cli()
    with patch("prompt_toolkit.output.defaults.create_output", return_value=DummyOutput()):
        return TuiApp(session=session, cli=cli)


# ── Stream Text Tests ────────────────────────────────────────


class TestStreamTextGoesToMessagePane:
    """test_stream_text_goes_to_message_pane — "text" yield calls stream_append."""

    def test_stream_text_goes_to_message_pane(self):
        session = _make_mock_session(
            yields=[
                ("text", "hello"),
                ("text", " world"),
            ]
        )
        tui = _make_tui(session=session)
        with patch.object(tui.message_pane, "stream_append") as mock_append:
            tui._stream_response("test message")
            mock_append.assert_any_call("hello")
            mock_append.assert_any_call(" world")
            assert mock_append.call_count >= 2


# ── Stream Error Tests ───────────────────────────────────────


class TestStreamErrorGoesToMessagePane:
    """test_stream_error_goes_to_message_pane — "error" yield calls append_error."""

    def test_stream_error_goes_to_message_pane(self):
        session = _make_mock_session(
            yields=[
                ("error", "something failed"),
            ]
        )
        tui = _make_tui(session=session)
        with patch.object(tui.message_pane, "append_error") as mock_error:
            tui._stream_response("test message")
            mock_error.assert_called_with("something failed")


# ── Stream Info / Tool Tracking Tests ────────────────────────


class TestStreamInfoToolStart:
    """test_stream_info_tool_start — "info" yield adds activity entry."""

    def test_stream_info_adds_activity_entry(self):
        """Generic info messages add a dot-bullet entry to activity log."""
        session = _make_mock_session(
            yields=[
                ("info", "hello info message"),
            ]
        )
        tui = _make_tui(session=session)
        tui._stream_response("test message")
        assert len(tui._activity_log) >= 1
        msgs = [msg for _, _, msg in tui._activity_log]
        assert any("hello info message" in msg for msg in msgs)

    def test_stream_info_empty_skipped(self):
        """Empty info messages are skipped."""
        session = _make_mock_session(
            yields=[
                ("info", "   "),
            ]
        )
        tui = _make_tui(session=session)
        before = len(tui._activity_log)
        tui._stream_response("test message")
        assert len(tui._activity_log) == before


class TestStreamInfoToolDone:
    """test_stream_info_tool_done — "tool_result" yield is handled."""

    def test_tool_result_handled(self):
        session = _make_mock_session(
            yields=[
                ("info", "hello info message"),
                ("tool_result", {"status": "ok"}),
            ]
        )
        tui = _make_tui(session=session)
        tui._stream_response("test message")
        # tool_result should be handled without error
        assert len(tui._activity_log) >= 1
        msgs = [msg for _, _, msg in tui._activity_log]
        assert any("hello info message" in msg for msg in msgs)


# ── Stream Thinking Tests ────────────────────────────────────


class TestStreamThinkingGoesToActivity:
    """test_stream_thinking_goes_to_activity — "thinking" yield adds activity entry."""

    def test_stream_thinking_goes_to_activity(self):
        session = _make_mock_session(
            yields=[
                ("thinking", "Let me analyze this code..."),
            ]
        )
        tui = _make_tui(session=session)
        tui._stream_response("test message")
        assert len(tui._activity_log) >= 1
        msgs = [msg for _, _, msg in tui._activity_log]
        assert any("Let me analyze" in msg for msg in msgs)

    def test_stream_thinking_truncated(self):
        long_reasoning = "x" * 200
        session = _make_mock_session(
            yields=[
                ("thinking", long_reasoning),
            ]
        )
        tui = _make_tui(session=session)
        tui._stream_response("test message")
        msgs = [msg for _, _, msg in tui._activity_log]
        assert any(len(msg) <= 120 for msg in msgs)


# ── Stream Image/Video Tests ─────────────────────────────────


class TestStreamImageVideoSaved:
    """test_stream_image_video_saved — "image"/"video" yield shows saved path."""

    def test_stream_image_saved(self):
        session = _make_mock_session(
            yields=[
                ("image", {"local_path": "/tmp/test.png"}),
            ]
        )
        tui = _make_tui(session=session)
        with patch.object(tui.message_pane, "append_info") as mock_info:
            tui._stream_response("test message")
            mock_info.assert_called_with("Saved: /tmp/test.png")

    def test_stream_video_saved(self):
        session = _make_mock_session(
            yields=[
                ("video", {"local_path": "/tmp/test.mp4"}),
            ]
        )
        tui = _make_tui(session=session)
        with patch.object(tui.message_pane, "append_info") as mock_info:
            tui._stream_response("test message")
            mock_info.assert_called_with("Saved: /tmp/test.mp4")

    def test_stream_image_activity_log_entry(self):
        session = _make_mock_session(
            yields=[
                ("image", {"local_path": "/tmp/test.png"}),
            ]
        )
        tui = _make_tui(session=session)
        tui._stream_response("test message")
        msgs = [msg for _, _, msg in tui._activity_log]
        assert any("/tmp/test.png" in msg for msg in msgs)


# ── Stream Exception Tests ───────────────────────────────────


class TestStreamExceptionHandled:
    """test_stream_exception_handled — exceptions are caught gracefully."""

    def test_stream_exception_handled(self):
        def bad_generator():
            yield ("text", "partial output")
            raise RuntimeError("connection lost")

        session = _make_mock_session()
        session.send_stream = bad_generator
        tui = _make_tui(session=session)
        tui._thinking = True

        with patch.object(tui.message_pane, "append_error") as mock_error:
            tui._stream_response("test message")
            mock_error.assert_called()
            assert tui._thinking is False

    def test_stream_exception_sets_thinking_false(self):
        session = _make_mock_session()
        session.send_stream = MagicMock(side_effect=RuntimeError("fail"))
        tui = _make_tui(session=session)
        tui._thinking = True

        tui._stream_response("test message")
        assert tui._thinking is False


# ── Stream Lifecycle Tests ───────────────────────────────────


class TestStreamLifecycle:
    """test_stream_lifecycle — stream_start/stream_end are called."""

    def test_stream_start_called(self):
        session = _make_mock_session(yields=[("text", "hello")])
        tui = _make_tui(session=session)
        with patch.object(tui.message_pane, "stream_start") as mock_start:
            tui._stream_response("test message")
            mock_start.assert_called_once()

    def test_stream_end_called(self):
        session = _make_mock_session(yields=[("text", "hello")])
        tui = _make_tui(session=session)
        with patch.object(tui.message_pane, "stream_end") as mock_end:
            tui._stream_response("test message")
            mock_end.assert_called_once()

    def test_stream_end_called_even_on_error(self):
        def bad_gen():
            yield ("text", "partial")
            raise RuntimeError("boom")

        session = _make_mock_session()
        session.send_stream = bad_gen
        tui = _make_tui(session=session)
        with patch.object(tui.message_pane, "stream_end") as mock_end:
            tui._stream_response("test message")
            mock_end.assert_called()


# ── Info fallback / budget tests ─────────────────────────────


class TestStreamInfoSpecialCases:
    """test_stream_info_special_cases — fallback message handling."""

    def test_stream_info_fallback(self):
        session = _make_mock_session(
            yields=[
                ("info", "fallback to light model"),
            ]
        )
        tui = _make_tui(session=session)
        tui._stream_response("test message")
        msgs = [msg for _, _, msg in tui._activity_log]
        assert any("fallback" in msg.lower() for msg in msgs)

    def test_stream_info_generic_message(self):
        session = _make_mock_session(
            yields=[
                ("info", "processing step 1"),
            ]
        )
        tui = _make_tui(session=session)
        tui._stream_response("test message")
        msgs = [msg for _, _, msg in tui._activity_log]
        assert any("processing step 1" in msg for msg in msgs)
