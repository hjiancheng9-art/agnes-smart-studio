"""Message pane — scrollable chat buffer with mouse wheel, keyboard, and auto-scroll.

Uses a custom ScrollingWindow subclass to prevent prompt_toolkit 3.x from
resetting vertical_scroll every frame (known issue in _scroll() method).
"""

from __future__ import annotations

import threading
import time

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.mouse_events import MouseEventType

_ROLE_FORMATS = {
    "user": ("class:message-user", "You"),
    "crux": ("class:message-crux", "CRUX"),
    "assistant": ("class:message-crux", "CRUX"),
    "info": ("class:message-info", " i "),
    "error": ("class:message-error", "ERR"),
}


# Sentinel value: setting vertical_scroll to a very large number makes
# ptk clamp it to the actual max, guaranteeing bottom-scroll regardless
# of content height changes.
_SCROLL_BOTTOM = 999999

# Scroll speed
_SCROLL_LINE = 3  # lines per mouse wheel tick
_SCROLL_PAGE_FACTOR = 0.85  # fraction of visible height for PageUp/PageDown


class _ScrollingWindow(Window):
    """Window subclass that overrides _scroll() to prevent ptk 3.x from
    resetting vertical_scroll to 0 on every render frame.

    Also intercepts mouse scroll events to properly update _pinned flag
    so manual scrolling doesn't get overridden by auto-scroll on new content.
    """

    def __init__(self, pane, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mp_pane = pane

    def _mouse_handler(self, mouse_event):
        """Intercept scroll events so they update _pinned via pane methods."""
        from prompt_toolkit.application.current import get_app

        # Restore mouse mode if it was lost (e.g. by subprocess output)
        if hasattr(self._mp_pane, "_mouse_guard") and self._mp_pane._mouse_guard:
            self._mp_pane._mouse_guard.restore()

        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self._mp_pane.scroll_up(lines=_SCROLL_LINE)
            get_app().invalidate()
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self._mp_pane.scroll_down(lines=_SCROLL_LINE)
            get_app().invalidate()
            return None
        return super()._mouse_handler(mouse_event)

    def _scroll(self, ui_content, width, height):
        """No-op for manual scroll positions; only compute bottom when pinned.

        We do NOT call super()._scroll() because _scroll_when_linewrapping
        forces vertical_scroll toward cursor position (0,0 for our cursorless
        FormattedTextControl), fighting every manual scroll operation.
        """
        self.horizontal_scroll = 0

        # ── 如果 pinned，强制回底（修复滚动卡死）──
        if getattr(self._mp_pane, "_pinned", False):
            self.vertical_scroll = _SCROLL_BOTTOM

        if self.vertical_scroll >= _SCROLL_BOTTOM:
            # Pinned to bottom: compute actual scroll position accounting
            # for line wrapping (vertical_scroll_2 skips visual rows).
            total_wrapped = 0
            for i in range(ui_content.line_count if ui_content else 0):
                total_wrapped += ui_content.get_height_for_line(i, width, self.get_line_prefix)

            if total_wrapped <= height:
                # Content fits in window — no scrolling needed
                self.vertical_scroll = 0
                self.vertical_scroll_2 = 0
            else:
                # Content exceeds window height — find the right content
                # line and intra-line offset to show the bottom 'height'
                # visual rows.
                skip = total_wrapped - height
                for lineno in range(ui_content.line_count):
                    line_h = ui_content.get_height_for_line(lineno, width, self.get_line_prefix)
                    if line_h <= skip:
                        skip -= line_h
                    else:
                        self.vertical_scroll = lineno
                        self.vertical_scroll_2 = skip
                        break

        else:
            # ── Manual scroll: preserve position, clamp out-of-bounds only ──
            if ui_content is None:
                # ⚠️ ui_content=None 时 max_line=0，会钳制 vertical_scroll=0。
                # 每次渲染周期都会把用户的滚动位置弹回顶部。不要删这个 guard。
                return  # Cannot clamp without content info; keep current position
            max_line = ui_content.line_count - 1
            if self.vertical_scroll > max(0, max_line):
                self.vertical_scroll = max(0, max_line)
                self.vertical_scroll_2 = 0
            elif self.vertical_scroll < 0:
                self.vertical_scroll = 0
                self.vertical_scroll_2 = 0


class _MessagePaneControl(FormattedTextControl):
    """FormattedTextControl subclass with mouse scroll handler."""

    def __init__(self, pane, *args, **kwargs):
        self._mp_pane = pane
        super().__init__(*args, **kwargs)

    def mouse_handler(self, mouse_event):
        from prompt_toolkit.application.current import get_app

        # Restore mouse mode if it was lost (e.g. by subprocess output).
        # This is a safety net: the heartbeat timer also restores periodically,
        # but this catches the case right when a mouse event arrives.
        if hasattr(self._mp_pane, "_mouse_guard") and self._mp_pane._mouse_guard:
            self._mp_pane._mouse_guard.restore()

        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self._mp_pane.scroll_up(lines=_SCROLL_LINE)
            get_app().invalidate()
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self._mp_pane.scroll_down(lines=_SCROLL_LINE)
            get_app().invalidate()
            return None
        return super().mouse_handler(mouse_event)


class MessagePane:
    # ── P0 事件通道隔离 ──
    VISIBLE_CHAT_ROLES = frozenset(
        {
            "assistant",
            "crux",
            "user",
            "assistant_delta",
            "assistant_final",
            "info",
            "error",
            "tool_status",
            "system_alert",
        }
    )
    TOOL_INLINE_ROLES = frozenset({"tool_started", "tool_finished", "tool_progress", "tool_failed"})
    HIDDEN_ROLES = frozenset(
        {
            "analysis",
            "reasoning",
            "chain_of_thought",
            "debug",
            "tool_raw_output",
            "python_stdout",
            "internal_prompt",
        }
    )
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
        self._empty_render_cache = None
        self._empty_render_cache_key = None

        # Virtual scrolling disabled — _scroll_offset tracked vertical_scroll
        # (wrapped line index), but _render used it to slice _lines (raw entries),
        # causing a scale mismatch that made scrolling appear broken visually.
        # Fix: threshold = max int, let ptk native scroll handle all rendering.
        self._virtual_scroll_threshold = 10**9
        self._visible_range = (0, 0)
        self._scroll_offset = 0
        self._virtual_buffer = 20
        # ── Markdown rendering (per debate R6) ──
        self._enable_markdown = True  # can toggle at runtime

        def _render():
            # Snapshot state atomically, render without lock
            with self._lock:
                if not self._lines and not self._stream_buffer:
                    if self._empty_renderer is not None:
                        _empty_width = self._window.render_info.window_width if self._window.render_info else None
                        _empty_key = _empty_width
                        if self._empty_render_cache_key != _empty_key:
                            self._empty_render_cache = self._empty_renderer()
                            self._empty_render_cache_key = _empty_key
                        return self._empty_render_cache
                    return FormattedText([("class:message-info", "Type a message or /help for commands")])
                lines_snapshot = list(self._lines)
                # ── Virtual Scrolling: only render visible range when over threshold ──
                total_msgs = len(lines_snapshot)
                if total_msgs > self._virtual_scroll_threshold:
                    visible_count = 50  # visible messages on screen
                    # Handle bottom sentinel: show the tail of content
                    if self._scroll_offset >= 999999:
                        start = max(0, total_msgs - visible_count - self._virtual_buffer)
                        end = total_msgs
                    else:
                        mid = self._scroll_offset
                        half = visible_count // 2
                        start = max(0, mid - half)
                        end = min(total_msgs, mid + half + self._virtual_buffer)
                    lines_snapshot = lines_snapshot[start:end]
                    self._visible_range = (start, end)
                stream_snapshot = self._stream_buffer
            pieces = []
            for style_class, text in lines_snapshot:
                pieces.append((style_class, text + "\n"))
            if stream_snapshot:
                pieces.append(("class:message-crux", stream_snapshot))
            return FormattedText(pieces)

        self._control = _MessagePaneControl(self, _render)
        self._window = _ScrollingWindow(
            self,
            content=self._control,
            style="class:message-area",
            wrap_lines=True,
            height=Dimension(weight=1),
            always_hide_cursor=True,
            allow_scroll_beyond_bottom=False,
            right_margins=[],
        )
        # Reference to MouseModeGuard — set by TuiApp after initialization
        self._mouse_guard = None

    def _restore_mouse(self) -> None:
        """Restore terminal mouse mode if subprocess output disabled it.

        Subprocess tools (run_bash) may emit raw ANSI escape sequences that
        disable mouse reporting mode.  Without this, mouse scroll and click
        stop working after any tool invocation.  This is a best-effort fix
        — it sends the enable sequence directly to stdout.
        """
        import sys
        try:
            sys.stdout.write("\033[?1000h\033[?1002h\033[?1006h")  # enable mouse tracking
            sys.stdout.flush()
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)

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
                row += uc.get_height_for_line(i, ri.window_width, self._window.get_line_prefix)
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
            line_h = uc.get_height_for_line(lineno, width, self._window.get_line_prefix)
            if accum + line_h > target_row:
                self._window.vertical_scroll = lineno
                self._window.vertical_scroll_2 = target_row - accum
                return
            accum += line_h

        # Past the end — pin to bottom
        self._window.vertical_scroll = _SCROLL_BOTTOM
        self._window.vertical_scroll_2 = 0

    # ── Scrolling ────────────────────────────────────────────

    def _sync_scroll_offset(self) -> None:
        """Sync _scroll_offset to vertical_scroll for virtual scrolling.

        When virtual scrolling is active (>100 messages), _render uses
        _scroll_offset to decide which messages to render. Without this
        sync, scrolling past message 75 shows blank content.

        Bottom sentinel must be 999999 (not 0) — _render checks
        _scroll_offset >= 999999 to decide whether to show the tail.
        Using 0 here would jump virtual scroll to the top of content.
        """
        vs = self._window.vertical_scroll
        self._scroll_offset = 999999 if vs >= _SCROLL_BOTTOM else vs

    def scroll_up(self, lines: int = _SCROLL_LINE) -> None:
        cur = self._current_visual_row()
        self._set_scroll_to_visual_row(cur - lines)
        new_row = self._current_visual_row()
        if new_row > 0:
            self._pinned = False
        self._sync_scroll_offset()

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
        self._sync_scroll_offset()

    def scroll_page_up(self) -> None:
        page = max(5, int(self._wrapped_window_height() * _SCROLL_PAGE_FACTOR))
        cur = self._current_visual_row()
        self._set_scroll_to_visual_row(cur - page)
        new_row = self._current_visual_row()
        if new_row > 0:
            self._pinned = False
        self._sync_scroll_offset()

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
        self._sync_scroll_offset()

    def scroll_to_top(self) -> None:
        self._window.vertical_scroll = 0
        self._window.vertical_scroll_2 = 0
        self._pinned = False
        self._scroll_offset = 0

    def scroll_to_bottom(self) -> None:
        self._pinned = True
        self._window.vertical_scroll = _SCROLL_BOTTOM
        self._window.vertical_scroll_2 = 0
        self._scroll_offset = 999999  # Bottom sentinel for virtual scrolling

    # ── P0 隐藏事件处理 ──
    def _log_hidden_event(self, role: str, text: str) -> None:
        """内部事件只写日志，不污染聊天区"""
        import logging

        _log = logging.getLogger("crux.ui.hidden")
        _log.debug("[%s] %s", role, text[:200])

    def _update_tool_status(self, role: str, text: str) -> None:
        """工具状态追踪（保留计数用于未来状态栏集成）"""
        if role == "tool_started":
            self._tool_count = getattr(self, "_tool_count", 0) + 1
            self._tool_start_time = time.time()
        elif role in ("tool_finished", "tool_failed"):
            self._tool_start_time = getattr(self, "_tool_start_time", time.time())

    def _auto_scroll(self) -> None:
        if self._pinned:
            # 守卫: 确保窗口是消息面板而非输入区域
            if not hasattr(self._window, "vertical_scroll"):
                return
            self._window.vertical_scroll = _SCROLL_BOTTOM
            self._window.vertical_scroll_2 = 0
            self._scroll_offset = 999999  # sync virtual scroll to bottom

    # ── Message management ───────────────────────────────────

    def pop_last_message(self) -> bool:
        """Remove the last message block from _lines.

        A message block is delimited by trailing empty spacing lines.
        Returns True if something was removed.
        """
        with self._lock:
            if not self._lines:
                return False
            # Remove trailing empty entries
            while self._lines and not self._lines[-1][1].strip():
                self._lines.pop()
            # Remove the message entries (non-empty) until we hit another empty
            while self._lines and self._lines[-1][1].strip():
                self._lines.pop()
            # Remove any remaining trailing empty entries
            while self._lines and not self._lines[-1][1].strip():
                self._lines.pop()
            self._auto_scroll()
            return True

    def append_message(self, role: str, text: str) -> None:
        self._restore_mouse()
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        # ── P0 事件通道隔离 ──
        if role not in self.VISIBLE_CHAT_ROLES:
            if role in self.HIDDEN_ROLES:
                self._log_hidden_event(role, text)
            elif role in self.TOOL_INLINE_ROLES:
                self._update_tool_status(role, text)
            return
        with self._lock:
            self._end_stream()
            fmt = _ROLE_FORMATS.get(role)
            sc, label = fmt if fmt else ("", role)

            # ── Markdown rendering (per R6 debate) ──
            if (
                self._enable_markdown
                and role in ("assistant", "user")
                and ("```" in text or "**" in text or "* " in text)
            ):
                try:
                    from ui.markdown_renderer import render_markdown

                    prefix = f"[{label}] "
                    fragments = render_markdown(text)
                    # Add prefix to first fragment
                    if fragments:
                        first_style, first_text = fragments[0]
                        fragments[0] = (first_style, prefix + first_text)
                    # Store as separate line entries
                    self._lines.append(("", ""))  # spacing
                    for style, frag in fragments:
                        if frag.strip() or style:
                            self._lines.append((sc if style == "" else style, frag))
                    self._lines.append(("", ""))
                    self._auto_scroll()
                    return
                except ImportError:
                    pass  # Fall through to plain text

            # Plain text fallback
            self._lines.append((sc, f"[{label}] {text}"))
            self._lines.append(("", ""))
            self._auto_scroll()

    def stream_start(self, role: str, *, force_pin: bool = True) -> None:
        with self._lock:
            if force_pin:
                self._pinned = True
            # Flush any residual buffer first — _end_stream() checks
            # self._stream_buffer, so it must be called BEFORE clearing.
            # Previously the buffer was cleared first, causing _end_stream
            # to be a no-op and losing unflushed stream data on interrupt.
            self._end_stream()
            fmt = _ROLE_FORMATS.get(role)
            sc, label = fmt if fmt else ("", role)
            self._stream_role = sc
            self._stream_label = label
            self._stream_buffer = f"[{label}] "

    def stream_append(self, text: str) -> None:
        from utils.unicode_safety import sanitize_text

        text = sanitize_text(text)
        # Restore mouse mode: subprocess output may have disabled it
        # via raw ANSI escape sequences (known issue with run_bash tools).
        self._restore_mouse()
        # 缓冲区上限保护: 单条消息超过 100KB 截断，防止异常数据撑爆
        MAX_STREAM_LEN = 102400
        if len(self._stream_buffer) > MAX_STREAM_LEN:
            if not getattr(self, "_truncation_warned", False):
                self._truncation_warned = True
                self._stream_buffer += "\n\n[... 输出超过 100KB 已截断]"
            return  # 停止追加，避免撑爆输入区
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
        # 安全兜底: 仅在流结束时恢复 pin，不在每消息时强制 pin
        # 保留 _pinned 状态让用户的手动滚动不受干扰

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
        self._empty_render_cache = None
        self._empty_render_cache_key = None
        self._empty_render_cache_key = None

    def invalidate_empty_cache(self) -> None:
        self._empty_render_cache = None
        self._empty_render_cache_key = None

    def clear(self) -> None:
        with self._lock:
            self._end_stream()
            self._lines.clear()
            self._window.vertical_scroll = 0
            self._pinned = True
        self._empty_render_cache = None
        self._empty_render_cache_key = None
        self._empty_render_cache_key = None
