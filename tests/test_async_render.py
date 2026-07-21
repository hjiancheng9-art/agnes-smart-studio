"""Tests for core/async_render.py — stream dispatch and rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from core.async_render import (
    StreamingRenderer,
    _dispatch_to_renderer,
    render_session_stream,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# ── Helpers ──


def _make_renderer() -> StreamingRenderer:
    """Create a minimal StreamingRenderer for test use."""
    return StreamingRenderer()


# ── _dispatch_to_renderer ──


class TestDispatchToRenderer:
    def test_text_appended(self):
        r = _make_renderer()
        _dispatch_to_renderer(r, "text", "hello")
        assert r.buffer == "hello"

    def test_text_multiple_pieces(self):
        r = _make_renderer()
        _dispatch_to_renderer(r, "text", "a")
        _dispatch_to_renderer(r, "text", "b")
        assert r.buffer == "ab"

    def test_text_type_check(self):
        r = _make_renderer()
        with pytest.raises(AssertionError):
            _dispatch_to_renderer(r, "text", 123)  # type: ignore[arg-type]

    def test_side_effect_dispatched(self):
        handled: list[tuple[str, Any]] = []

        def handler(kind: str, payload: Any) -> None:
            handled.append((kind, payload))

        r = StreamingRenderer(side_effect_handlers={"info": handler})
        _dispatch_to_renderer(r, "info", {"msg": "hello"})
        assert handled == [("info", {"msg": "hello"})]

    def test_unknown_side_effect_noop(self):
        r = _make_renderer()
        # Should not crash
        _dispatch_to_renderer(r, "unknown", {"data": 1})

    def test_mixed_text_and_side_effects(self):
        handled: list[str] = []

        def handler(kind: str, payload: Any) -> None:
            handled.append(f"{kind}:{payload}")

        r = StreamingRenderer(side_effect_handlers={"info": handler})
        _dispatch_to_renderer(r, "text", "start ")
        _dispatch_to_renderer(r, "info", "note")
        _dispatch_to_renderer(r, "text", " end")
        assert r.buffer == "start  end"
        assert handled == ["info:note"]


# ── render_session_stream ──


def _stream(items: list[tuple[str, Any]]) -> Iterator[tuple[str, Any]]:
    yield from items


class TestRenderSessionStream:
    def test_returns_empty_buffer_for_empty_stream(self):
        r = _make_renderer()
        result = render_session_stream(r, _stream([]))
        assert result == ""

    def test_renders_text(self):
        r = _make_renderer()
        result = render_session_stream(r, _stream([("text", "hello")]))
        assert result == "hello"
        assert r.buffer == "hello"

    def test_renders_multiple_pieces(self):
        r = _make_renderer()
        result = render_session_stream(r, _stream([("text", "a"), ("text", "bb"), ("text", "ccc")]))
        assert result == "abbccc"

    def test_renders_mixed_with_side_effects(self):
        handled: list[str] = []

        def handler(kind: str, payload: Any) -> None:
            handled.append(payload)

        r = StreamingRenderer(side_effect_handlers={"info": handler})
        result = render_session_stream(
            r,
            _stream(
                [
                    ("text", "A"),
                    ("info", {"msg": "note"}),
                    ("text", "B"),
                ]
            ),
        )
        assert result == "AB"
        assert handled == [{"msg": "note"}]

    def test_permission_error_calls_callback(self):
        permission_errors: list[PermissionError] = []

        def on_denied(e: PermissionError) -> None:
            permission_errors.append(e)

        # Register a confirm handler that raises PermissionError
        def confirm_handler(kind: str, payload: Any) -> None:
            raise PermissionError(f"user denied {payload.get('tool', 'unknown')}")

        r = StreamingRenderer(side_effect_handlers={"confirm": confirm_handler})
        result = render_session_stream(
            r,
            _stream(
                [
                    ("text", "before "),
                    ("confirm", {"tool": "rm -rf /"}),
                    ("text", " after"),
                ]
            ),
            on_permission_denied=on_denied,
        )
        # Text before the permission error should be rendered
        assert result == "before "
        assert len(permission_errors) == 1
        assert "rm" in str(permission_errors[0]) or "user denied" in str(permission_errors[0])

    def test_keyboard_interrupt_re_raises(self):
        r = _make_renderer()
        interrupted = False

        def on_interrupt(e: KeyboardInterrupt) -> None:
            nonlocal interrupted
            interrupted = True

        # First item is text, second raises KeyboardInterrupt
        def gen():
            yield ("text", "before ")
            raise KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            render_session_stream(
                r,
                gen(),
                on_interrupt=on_interrupt,
            )
        assert interrupted
        # Text before interrupt should be in buffer
        assert r.buffer == "before "

    def test_on_interrupt_not_called_when_no_interrupt(self):
        r = _make_renderer()
        called = False

        def cb(_e: KeyboardInterrupt) -> None:
            nonlocal called
            called = True

        render_session_stream(
            r,
            _stream([("text", "hi")]),
            on_interrupt=cb,
        )
        assert not called
