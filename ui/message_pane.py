"""Message pane — scrollable chat buffer with mouse wheel, keyboard, and auto-scroll.

Uses a custom ScrollingWindow subclass to prevent prompt_toolkit 3.x from
resetting vertical_scroll every frame (known issue in _scroll() method).
"""

from __future__ import annotations

import threading

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension

_ROLE_FORMATS = {
    "user": ("class:message-user", "You"),
    "crux": ("class:message-crux", "CRUX"),
    "assistant": ("class:message-crux", "CRUX"),
    "info": ("class:message-info", "--"),
    "error": ("class:message-error", "!!"),
}

# Sentinel value: setting vertical_scroll to a very large number makes
# ptk clamp it to the actual max, guaranteeing bottom-scroll regardless
# of content height changes.
_SCROLL_BOTTOM = 999999

# Scroll speed
_SCROLL_LINE = 3   # lines per mouse wheel tick
_SCROLL_PAGE_FACTOR = 0.85  # fraction of visible height for PageUp/PageDown


class _ScrollingWindow(Window):
    """Window subclass that overrides _scroll() to prevent ptk 3.x from
    resetting vertical_scroll to 0 on every render frame.

    ptk 3.0.x recalculates vertical_scroll in _scroll() based on cursor
    position, which is always (0,0) for FormattedTextControl. This means
    any manual scroll position is lost on the next frame unless we no-op
    the internal scroll calculation.

    Also correctly handles auto-scroll-to-bottom when wrap_lines=True:
    computes both vertical_scroll (content line index) and vertical_scroll_2
    (visual row offset within that line) so the bottom of wrapped content
    is visible even when total wrapped height exceeds window height.
    """

    def _scroll(self, ui_content, width, height):
        # Let the parent calculate, but then restore our saved position
        saved = self.vertical_scroll
        super()._scroll(ui_content, width, height)
        if saved >= _SCROLL_BOTTOM:
            # Pinned to bottom: compute actual scroll position accounting
            # for line wrapping (vertical_scroll_2 skips visual rows).
            total_wrapped = 0
            for i in range(ui_content.line_count if ui_content else 0):
                total_wrapped += ui_content.get_height_for_line(
                    i, width, self.get_line_prefix
                )

            if total_wrapped <= height:
                # Content fits in window — no scrolling needed
                self.vertical_scroll = 0
                self.vertical_scroll_2 = 0
            else:
                # Content exceeds window height — find the right content
                # line and intra-line offset to show the bottom 'height'
                # visual rows. Iterate forward from top: skip accumulates
                # until we find the first visible line.
                skip = total_wrapped - height
                for lineno in range(ui_content.line_count):
                    line_h = ui_content.get_height_for_line(
                        lineno, width, self.get_line_prefix
                    )
                    if line_h <= skip:
                        skip -= line_h
                    else:
                        self.vertical_scroll = lineno
                        self.vertical_scroll_2 = skip
                        break
        elif saved > 0:
            self.vertical_scroll = saved


class MessagePane:
    """Scrollable chat message display with auto-scroll and manual override.

    Behavior:
    - New messages auto-scroll to bottom when _pinned=True
    - User scrolls up (PageUp / mouse wheel up) → unpin, stop auto-scrolling
    - User scrolls to bottom (PageDown / mouse wheel down to end) → re-pin
    - stream_start() always re-pins to show live streaming output
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lines: list[tuple[str, str]] = []
        self._stream_role = ""
        self._stream_label = ""
        self._stream_buffer = ""
        self._pinned = True
        self._empty_renderer = None  # type: ignore[assignment]

        def _render():
            # Snapshot state atomically, render without lock
            with self._lock:
                if not self._lines and not self._stream_buffer:
                    if self._empty_renderer is not None:
                        return self._empty_renderer()
                    return FormattedText([("class:message-info", "Type a message or /help for commands")])
                lines_snapshot = list(self._lines)
                stream_snapshot = self._stream_buffer
            pieces = []
            for style_class, text in lines_snapshot:
                pieces.append((style_class, text + "\n"))
            if stream_snapshot:
                pieces.append(("class:message-crux", stream_snapshot))
            return FormattedText(pieces)

        self._control = FormattedTextControl(_render)
        self._window = _ScrollingWindow(
            content=self._control,
            style="class:message-area",
            wrap_lines=True,
            height=Dimension(weight=3),
            always_hide_cursor=True,
            allow_scroll_beyond_bottom=False,
            right_margins=[],
        )

    # ── Public properties ────────────────────────────────────

    @property
    def pane(self) -> Window:
        return self._window

    @property
    def line_count(self) -> int:
        return len(self._lines) + (1 if self._stream_buffer else 0)

    def _window_height(self) -> int:
        h = self._window.render_info.window_height if self._window.render_info else 0
        return max(5, h - 1) if h > 0 else 20

    # ── Wrapped content helpers ──────────────────────────────

    def _wrapped_content_height(self) -> int:
        """Total visual row count of all messages after line wrapping.
        Falls back to unwrapped line_count when render_info is unavailable."""
        ri = self._window.render_info
        if ri is not None:
            return ri.content_height
        return self.line_count

    def _wrapped_window_height(self) -> int:
        """Current window height in visual rows."""
        ri = self._window.render_info
        if ri is not None:
            return ri.window_height
        return self._window_height()

    def _current_visual_row(self) -> int:
        """Estimate the topmost visible visual row from scroll state."""
        vs = self._window.vertical_scroll
        if vs >= _SCROLL_BOTTOM:
            return max(0, self._wrapped_content_height() - self._wrapped_window_height())
        ri = self._window.render_info
        if ri is not None and ri.ui_content is not None:
            uc = ri.ui_content
            row = 0
            for i in range(min(vs, uc.line_count)):
                row += uc.get_height_for_line(
                    i, ri.window_width, self._window.get_line_prefix
                )
            return row + self._window.vertical_scroll_2
        # Fallback: clamp vs to valid range
        return min(vs, max(0, self.line_count - self._window_height()))

    def _set_scroll_to_visual_row(self, target_row: int, *, clamp: bool = True) -> None:
        """Set vertical_scroll and vertical_scroll_2 to show a given visual row
        as the topmost visible row. When clamp=True, constrain to valid range."""
        ri = self._window.render_info
        if ri is None or ri.ui_content is None:
            # Fallback: clamp to valid content range
            max_line = max(0, self.line_count - self._window_height())
            self._window.vertical_scroll = max(0, min(target_row, max_line))
            self._window.vertical_scroll_2 = 0
            return

        uc = ri.ui_content
        width = ri.window_width

        if clamp:
            max_row = max(0, self._wrapped_content_height() - self._wrapped_window_height())
            target_row = max(0, min(target_row, max_row))

        if target_row <= 0:
            self._window.vertical_scroll = 0
            self._window.vertical_scroll_2 = 0
            return

        # Walk through content lines to find which one contains target_row
        accum = 0
        for lineno in range(uc.line_count):
            line_h = uc.get_height_for_line(
                lineno, width, self._window.get_line_prefix
            )
            if accum + line_h > target_row:
                self._window.vertical_scroll = lineno
                self._window.vertical_scroll_2 = target_row - accum
                return
            accum += line_h

        # Past the end — pin to bottom
        self._window.vertical_scroll = _SCROLL_BOTTOM
        self._window.vertical_scroll_2 = 0

    # ── Scrolling ────────────────────────────────────────────

    def scroll_up(self, lines: int = _SCROLL_LINE) -> None:
        cur = self._current_visual_row()
        self._set_scroll_to_visual_row(cur - lines)
        new_row = self._current_visual_row()
        if new_row > 0:
            self._pinned = False

    def scroll_down(self, lines: int = _SCROLL_LINE) -> None:
        cur = self._current_visual_row()
        max_row = max(0, self._wrapped_content_height() - self._wrapped_window_height())
        target = cur + lines
        if target >= max_row:
            self._pinned = True
            self._window.vertical_scroll = _SCROLL_BOTTOM
        else:
            self._set_scroll_to_visual_row(target, clamp=False)
            self._pinned = False

    def scroll_page_up(self) -> None:
        page = max(5, int(self._wrapped_window_height() * _SCROLL_PAGE_FACTOR))
        cur = self._current_visual_row()
        self._set_scroll_to_visual_row(cur - page)
        new_row = self._current_visual_row()
        if new_row > 0:
            self._pinned = False

    def scroll_page_down(self) -> None:
        page = max(5, int(self._wrapped_window_height() * _SCROLL_PAGE_FACTOR))
        cur = self._current_visual_row()
        max_row = max(0, self._wrapped_content_height() - self._wrapped_window_height())
        target = cur + page
        if target >= max_row:
            self._pinned = True
            self._window.vertical_scroll = _SCROLL_BOTTOM
        else:
            self._set_scroll_to_visual_row(target, clamp=False)
            self._pinned = False

    def scroll_to_top(self) -> None:
        self._window.vertical_scroll = 0
        self._window.vertical_scroll_2 = 0
        self._pinned = False

    def scroll_to_bottom(self) -> None:
        self._pinned = True
        self._window.vertical_scroll = _SCROLL_BOTTOM
        self._window.vertical_scroll_2 = 0

    def _auto_scroll(self) -> None:
        if self._pinned:
            self._window.vertical_scroll = _SCROLL_BOTTOM
            self._window.vertical_scroll_2 = 0

    # ── Message management ───────────────────────────────────

    def append_message(self, role: str, text: str) -> None:
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        with self._lock:
            self._end_stream()
            fmt = _ROLE_FORMATS.get(role)
            sc, label = fmt if fmt else ("", role)
            self._lines.append((sc, f"[{label}] {text}"))
            self._lines.append(("", ""))
            self._auto_scroll()

    def stream_start(self, role: str) -> None:
        with self._lock:
            self._pinned = True
            self._end_stream()
            fmt = _ROLE_FORMATS.get(role)
            sc, label = fmt if fmt else ("", role)
            self._stream_role = sc
            self._stream_label = label
            self._stream_buffer = f"[{label}] "

    def stream_append(self, text: str) -> None:
        with self._lock:
            if self._stream_label:
                self._stream_buffer += text
                self._auto_scroll()

    def stream_end(self) -> None:
        with self._lock:
            self._end_stream()

    def _end_stream(self) -> None:
        if self._stream_buffer:
            self._lines.append((self._stream_role, self._stream_buffer))
            self._lines.append(("", ""))
            self._stream_buffer = ""
            self._stream_role = ""
            self._stream_label = ""
            self._auto_scroll()

    def append_info(self, text: str) -> None:
        self.append_message("info", text)

    def append_error(self, text: str) -> None:
        self.append_message("error", text)

    def set_empty_renderer(self, renderer) -> None:
        """Set a custom renderer for the empty state (no messages, no stream).

        When set, this callable (returning FormattedText) is used instead of
        the default placeholder text. Pass None to restore default.
        """
        self._empty_renderer = renderer

    def clear(self) -> None:
        with self._lock:
            self._end_stream()
            self._lines.clear()
            self._window.vertical_scroll = 0
            self._pinned = True
