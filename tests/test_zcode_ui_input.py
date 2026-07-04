"""TDD RED phase — tests for ui/tui_app.py input handling and key bindings.

Tests must FAIL before GREEN implementation.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────


def _make_mock_session():
    """Create a mock ChatSession with minimal attributes."""
    s = MagicMock()
    s.model = "test-model"
    s.messages = []
    s.send_stream.return_value = iter([])
    return s


def _make_mock_cli():
    """Create a mock CruxCLI."""
    c = MagicMock()
    c.dispatch.return_value = True
    return c


def _make_app(**kwargs):
    """Create a TuiApp with all prompt_toolkit Application and key-parsing mocked out."""
    from ui.tui_app import TuiApp

    session = kwargs.get("session", _make_mock_session())
    cli = kwargs.get("cli", _make_mock_cli())

    # ptk 3.0.52 _parse_key rejects "wheel-up"/"wheel-down" — patch it
    import prompt_toolkit.key_binding.key_bindings as kb_mod
    _real_parse = kb_mod._parse_key

    def _patched_parse_key(key: str):
        if key in ("<scroll-up>", "<scroll-down>"):
            return key  # return the string itself as the key token
        return _real_parse(key)

    # Must patch ui.tui_app.Application (the imported reference) AND
    # prompt_toolkit.key_binding.key_bindings._parse_key
    with patch("ui.tui_app.Application"), patch.object(kb_mod, "_parse_key", side_effect=_patched_parse_key):
        app = TuiApp(session, cli)
    # After construction, replace _app with a MagicMock
    app._app = MagicMock()
    return app


# ── Test 1: Key Bindings ───────────────────────────────────────────


class TestKeyBindings:
    """test_tui_app_has_correct_keybindings — verify all required keys are bound."""

    REQUIRED_KEYS = [
        "c-c", "c-v", "escape", "c-l",
        "pageup", "pagedown", "home", "end",
        "<scroll-up>", "<scroll-down>",  # Keys.ScrollUp / Keys.ScrollDown string form
    ]

    def test_has_required_keybindings(self):
        """Instantiate TuiApp with mocks, verify self.kb.bindings has all required keys."""
        app = _make_app()
        bound_keys = set()
        for binding in app.kb.bindings:
            bound_keys.update(binding.keys)
        for key in self.REQUIRED_KEYS:
            assert key in bound_keys, f"Missing key binding: {key}"


# ── Test 2: Quit Commands ──────────────────────────────────────────


class TestQuitCommands:
    """test_on_accept_quit_commands — /q, /quit, /exit should call _app.exit()."""

    @pytest.mark.parametrize("cmd", ["/q", "/quit", "/exit"])
    def test_quit_command_exits_app(self, cmd):
        app = _make_app()
        app._app.exit = MagicMock()
        app.input_buffer.text = cmd
        result = app._on_accept(app.input_buffer)
        app._app.exit.assert_called_once()
        assert result is True


# ── Test 3: Empty Input ────────────────────────────────────────────


class TestEmptyInput:
    """test_on_accept_empty_input — empty string returns True without effects."""

    def test_empty_input_returns_true(self):
        app = _make_app()
        app.input_buffer.text = ""
        result = app._on_accept(app.input_buffer)
        assert result is True

    def test_empty_input_no_side_effects(self):
        app = _make_app()
        app._app.exit = MagicMock()
        app.cli.dispatch = MagicMock()
        app.input_buffer.text = ""
        app._on_accept(app.input_buffer)
        app._app.exit.assert_not_called()
        app.cli.dispatch.assert_not_called()


# ── Test 4: Slash Command Dispatch ─────────────────────────────────


class TestSlashCommand:
    """test_on_accept_slash_command — /help calls cli.dispatch and captures stdout."""

    def test_slash_command_dispatches(self):
        app = _make_app()
        app.cli.dispatch.return_value = True
        app.input_buffer.text = "/help"
        result = app._on_accept(app.input_buffer)
        app.cli.dispatch.assert_called_once_with("/help")
        assert result is True

    def test_slash_command_captures_stdout(self):
        app = _make_app()
        app.cli.dispatch.side_effect = lambda _: sys.stdout.write("help info printed")
        app.input_buffer.text = "/status"
        # Mock append_info to verify stdout capture
        app.message_pane.append_info = MagicMock()
        result = app._on_accept(app.input_buffer)
        assert result is True
        # The stdout output should have been appended to message_pane
        app.message_pane.append_info.assert_called_with("help info printed")


# ── Test 5: Normal Text Submission ──────────────────────────────────


class TestNormalText:
    """test_on_accept_normal_text — normal text submits to executor, sets _thinking=True."""

    def test_normal_text_submits(self):
        app = _make_app()
        app._executor = MagicMock()
        app.input_buffer.text = "hello world"
        result = app._on_accept(app.input_buffer)
        assert result is True
        assert app._thinking is True
        app._executor.submit.assert_called_once()

    def test_normal_text_appends_user_message(self):
        app = _make_app()
        app._executor = MagicMock()
        mp_mock = MagicMock()
        app.message_pane = mp_mock
        app.input_buffer.text = "hello world"
        app._on_accept(app.input_buffer)
        mp_mock.append_message.assert_called_with("user", "hello world")


# ── Test 6: Double Submit Guard ─────────────────────────────────────


class TestDoubleSubmitGuard:
    """test_double_submit_guard — when _thinking=True, blocks submission."""

    def test_double_submit_blocked(self):
        app = _make_app()
        app._executor = MagicMock()
        app._thinking = True
        app.input_buffer.text = "test"
        result = app._on_accept(app.input_buffer)
        assert result is True
        # Must NOT submit to executor
        app._executor.submit.assert_not_called()


# ── Test 7: Drag-Drop Image Detection ───────────────────────────────


class TestDragDropImage:
    """test_drag_drop_single_image_detected — quoted image path triggers _send_image."""

    def test_single_drag_image_detected(self):
        app = _make_app()
        app._send_image = MagicMock()
        app.input_buffer.text = '"/tmp/screenshot.png"'
        with patch("ui.tui_app.detect_drag_images") as mock_detect:
            mock_detect.return_value = ["/tmp/screenshot.png"]
            result = app._on_accept(app.input_buffer)
            app._send_image.assert_called_once_with("/tmp/screenshot.png")
            assert result is True

    def test_multi_drag_images_sends_all(self):
        app = _make_app()
        app._send_image = MagicMock()
        app.input_buffer.text = '"/tmp/a.png" "/tmp/b.png"'
        with patch("ui.tui_app.detect_drag_images") as mock_detect:
            mock_detect.return_value = ["/tmp/a.png", "/tmp/b.png"]
            result = app._on_accept(app.input_buffer)
            assert app._send_image.call_count == 2
            app._send_image.assert_any_call("/tmp/a.png")
            app._send_image.assert_any_call("/tmp/b.png")
            assert result is True


# ── Test 8: Ctrl+V Text Paste ─────────────────────────────────────


class TestCtrlVPaste:
    """test_ctrl_v_text_paste — when clipboard has text, calls paste_from_clipboard."""

    def test_ctrl_v_pastes_text(self):
        app = _make_app()
        # Set up the c-v handler by simulating it
        # We need to find and invoke the handler for 'c-v'
        handler = None
        for binding in app.kb.bindings:
            if "c-v" in binding.keys:
                handler = binding.handler
                break
        assert handler is not None, "c-v binding not found"

        # Mock event
        mock_event = MagicMock()
        mock_event.app.clipboard.get_data.return_value = "pasted text"
        mock_clipboard_image = MagicMock(return_value=None)

        with patch("ui.tui_app.get_clipboard_image", mock_clipboard_image):
            # patch paste_from_clipboard on the buffer directly
            app.input_buffer.paste_from_clipboard = MagicMock()
            handler(mock_event)
            app.input_buffer.paste_from_clipboard.assert_called_once()

    def test_ctrl_v_image_paste(self):
        """When clipboard has an image, _send_image is called instead of paste."""
        app = _make_app()
        # Find c-v handler
        handler = None
        for binding in app.kb.bindings:
            if "c-v" in binding.keys:
                handler = binding.handler
                break
        assert handler is not None, "c-v binding not found"

        mock_event = MagicMock()
        app._send_image = MagicMock()

        with patch("ui.tui_app.get_clipboard_image", return_value="/tmp/clip_img.png"):
            handler(mock_event)
            app._send_image.assert_called_once_with("/tmp/clip_img.png")


# ── Test 9: Escape Resets Buffer ───────────────────────────────────


class TestEscapeReset:
    """test_escape_resets_buffer — escape key resets input_buffer."""

    def test_escape_resets_buffer(self):
        app = _make_app()
        # Find standalone escape handler (keys == ("escape",), not a key sequence)
        handler = None
        for binding in app.kb.bindings:
            if binding.keys == ("escape",):
                handler = binding.handler
                break
        assert handler is not None, "standalone escape binding not found"

        app.input_buffer.text = "some text"
        app.input_buffer.reset = MagicMock()
        mock_event = MagicMock()
        handler(mock_event)
        app.input_buffer.reset.assert_called_once()
