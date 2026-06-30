"""CRUX Terminal Application — Claude Code-style fixed input box.

Layout:
  ┌──────────────────────────────────┐
  │  Header bar (fixed)              │
  ├──────────────────────────────────┤
  │  Message area (ScrollablePane)   │
  ├──────────────────────────────────┤
  │  Status bar (fixed)              │
  ├──────────────────────────────────┤
  │  Input area (fixed, TextArea)    │
  └──────────────────────────────────┘

All existing console.print() output is captured via _LayoutSink and routed
to add_message(), which updates the message area and triggers a UI refresh.

Streaming text arrives via add_stream_chunk() from the background AI thread.
"""

from __future__ import annotations

import logging
import queue
import time
from typing import Callable

from prompt_toolkit import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.filters import has_focus
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.bindings.scroll import (
    scroll_forward, scroll_backward,
    scroll_half_page_down, scroll_half_page_up,
    scroll_one_line_down, scroll_one_line_up,
)
from prompt_toolkit.layout import (
    Dimension, HSplit, Layout, ScrollablePane, Window, WindowAlign,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.processors import (
    BeforeInput, ConditionalProcessor, TabsProcessor,
)
from prompt_toolkit.lexers import SimpleLexer
from prompt_toolkit.styles import Style, merge_styles

from ui.flourish import (
    BEAST_THEMES, DEFAULT_BEAST, BeastTheme, DayNightPalette,
    ParticleBurst, PromptGlow, Spinner, SPLASH_FRAMES,
)
from ui.theme import COLORS
from ui.message_buffer import MessageBuffer

logger = logging.getLogger("crux.ui")

__all__ = ["CruxTerminalApp"]


# ═══════════════════════════════════════════════════════════════
# Slash-command completer
# ═══════════════════════════════════════════════════════════════

SLASH_COMMANDS = [
    "beast", "help", "clear", "thinking", "code", "agent", "tools",
    "img", "video", "showrun", "vision", "skill",
    "plan", "sub", "project", "team", "deploy", "todo", "refactor",
    "commit", "changelog",
    "self", "audit", "rules", "provider", "evolve", "know", "model",
    "exit", "quit", "q",
]


class SlashCompleter(Completer):
    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            prefix = text[1:]
            for cmd in SLASH_COMMANDS:
                if cmd.startswith(prefix):
                    yield Completion(cmd, start_position=-len(prefix))


# ═══════════════════════════════════════════════════════════════
# App styles — derived from existing Dark Atelier theme
# ═══════════════════════════════════════════════════════════════

def build_ptk_style(theme: BeastTheme | None = None) -> Style:
    """Build a prompt_toolkit Style from the CRUX COLORS palette.

    When *theme* is provided the primary/accent colours come from the
    beast theme; otherwise the default Dark Atelier palette is used.
    """
    C = dict(COLORS)
    # Apply day/night adjustments
    C = DayNightPalette.adjust(C)

    if theme is not None:
        C["primary"] = theme.primary
        C["accent"] = theme.accent
        C["input_prompt"] = theme.primary
        C["input_cursor"] = theme.glow
        C["input_border"] = theme.border
        C["border_focus"] = theme.glow
        C["info"] = theme.primary
        C["success"] = COLORS["qilin"]

    return Style.from_dict({
        # Header
        "header": f"bold {C['primary']}",
        "header.bar": C["border"],
        # Message area
        "window": f"bg:{C['base']}",
        "window.border": C["border"],
        # Status bar
        "status": C["text_tertiary"],
        "status.key": C["text_secondary"],
        "status.value": C["text"],
        "status.spinner": f"bold {C['accent']}",
        # Input
        "input.prompt": f"bold {C['primary']}",
        "input.text": C["text"],
        "input.placeholder": C["text_tertiary"],
        "input.border": C["border"],
        "input.border.focused": C["border_focus"],
        # General
        "dim": C["text_tertiary"],
        "accent": C["accent"],
        "success": C["success"],
        "warning": C["warning"],
        "error": C["error"],
        "info": C["info"],
        # Existing styles for Rich ANSI
        "primary": f"bold {C['primary']}",
        "muted": C["text_secondary"],
        "highlight": C["zhuque"],
        "surface": f"bg:{C['surface']}",
    })


# ═══════════════════════════════════════════════════════════════
# Main terminal application
# ═══════════════════════════════════════════════════════════════

class CruxTerminalApp:
    """Full-screen terminal chat app with fixed input box.

    Usage::

        app = CruxTerminalApp(on_submit=my_handler)
        app.set_header("CRUX Studio v6 · deepseek-v4-pro")
        app.run()
    """

    def __init__(
        self,
        on_submit: Callable[[str], None] | None = None,
        on_interrupt: Callable[[], None] | None = None,
        history: list[str] | None = None,
        show_splash: bool = True,
    ):
        self._on_submit = on_submit
        self._on_interrupt = on_interrupt

        # Thread-safe message queue (streaming chunk → UI)
        self._msg_queue: queue.Queue = queue.Queue()
        self._streaming_buf = ""
        self._messages: list[tuple[str, str]] = []  # [(role, text)]
        self._header_text = ""
        self._status_text = ""

        # ── Creative state ──
        self._beast_theme: BeastTheme = BEAST_THEMES[DEFAULT_BEAST]
        self._spinner = Spinner()
        self._prompt_glow = PromptGlow()
        self._splash_frame = -1 if not show_splash else 0
        self._splash_t0 = time.time() if show_splash else 0.0
        self._generating = False
        self._first_launch = True

        # Input history
        self._history = InMemoryHistory()
        if history:
            for h in history:
                self._history.append_string(h)

        # Flag: application is running
        self._running = False
        # Deferred scroll-to-bottom flag (set by _drain_queue, handled after render)
        self._pending_scroll = False

        # Build UI components
        self._build()

    # ── Public API (thread-safe) ─────────────────────────────

    def add_message(self, role: str, text: str) -> None:
        """Add a complete message. Thread-safe — callable from any thread."""
        self._msg_queue.put(("message", (role, text)))
        self._refresh()

    def add_stream_chunk(self, text: str) -> None:
        """Append a streaming text chunk. Thread-safe."""
        self._msg_queue.put(("chunk", text))
        self._refresh()

    def commit_stream(self) -> None:
        """Finalize the current streaming message."""
        self._msg_queue.put(("commit", None))
        self._refresh()

    def set_header(self, text: str) -> None:
        self._header_text = text
        self._refresh()

    def set_status(self, text: str) -> None:
        self._status_text = text
        self._refresh()

    def set_input_text(self, text: str) -> None:
        """Pre-fill the input buffer (e.g., restore pending input)."""
        def _set():
            buf = self._app.layout.get_buffer_by_name(DEFAULT_BUFFER)
            if buf:
                buf.text = text
        self._schedule(_set)

    def exit(self) -> None:
        """Request app shutdown."""
        self._running = False
        self._schedule(lambda: get_app().exit())

    # ── Creative API ──────────────────────────────────────────

    def set_beast(self, name: str) -> str | None:
        """Switch to a beast theme. Returns theme label or None if unknown."""
        theme = BEAST_THEMES.get(name)
        if theme is None:
            return None
        self._beast_theme = theme
        # Rebuild app style
        self._app.style = merge_styles([build_ptk_style(theme)])
        self._app.invalidate()
        return theme.label

    @property
    def beast_theme(self) -> BeastTheme:
        return self._beast_theme

    def start_generating(self) -> None:
        """Signal that AI generation has started (activates spinner)."""
        self._generating = True
        self._spinner.start()
        self._refresh()

    def stop_generating(self) -> None:
        """Signal that AI generation has stopped."""
        self._generating = False
        self._spinner.stop()
        self._refresh()

    def sparkle(self) -> None:
        """Emit a success sparkle particle burst in the message area."""
        burst = ParticleBurst.success().render()
        self.add_message("system", f"  {burst}")

    def flash_error(self) -> None:
        """Emit an error flash in the message area."""
        burst = ParticleBurst.error().render()
        self.add_message("system", f"  {burst}")

    # ── Build layout ─────────────────────────────────────────

    def _build(self) -> None:
        # ── Header ──
        self._header_control = FormattedTextControl(
            text=self._get_header_text,
        )
        header_window = Window(
            self._header_control,
            height=1,
            style="class:header.bar",
            align=WindowAlign.LEFT,
        )

        # ── Message area (ScrollablePane) ──
        self._message_control = FormattedTextControl(
            text=self._get_message_text,
            focusable=True,
        )
        message_window = Window(
            self._message_control,
            wrap_lines=True,
            always_hide_cursor=True,
        )
        self._scrollable_pane = ScrollablePane(message_window, show_scrollbar=False, display_arrows=False)
        scrollable = self._scrollable_pane

        # ── Status bar ──
        self._status_control = FormattedTextControl(
            text=self._get_status_text,
        )
        status_window = Window(
            self._status_control,
            height=1,
            style="class:dim",
            align=WindowAlign.LEFT,
        )

        # ── Input area ──
        self._input_buffer = Buffer(
            history=self._history,
            completer=SlashCompleter(),
            complete_while_typing=True,
            name=DEFAULT_BUFFER,
        )
        self._input_control = BufferControl(
            buffer=self._input_buffer,
            lexer=SimpleLexer("class:input.text"),
            input_processors=[
                ConditionalProcessor(
                    BeforeInput("  › "),
                    has_focus(self._input_buffer),
                ),
                TabsProcessor(),
            ],
            include_default_input_processors=True,
        )
        input_window = Window(
            self._input_control,
            height=Dimension(min=1, max=5, preferred=3),
            style=lambda: (
                "class:input.border.focused"
                if self._app and self._app.layout.has_focus(self._input_buffer)
                else "class:input.border"
            ),
        )

        # ── Root layout ──
        root = HSplit([
            header_window,
            Window(height=1, char="─", style="class:window.border"),  # separator
            scrollable,
            Window(height=1, char="─", style="class:window.border"),  # separator
            status_window,
            input_window,
        ])

        # ── Key bindings ──
        kb = self._build_keybindings()

        # ── Scroll bindings for message area ──
        scroll_kb = KeyBindings()

        def _do_scroll(event, scroll_fn):
            """Focus message window, scroll, then refocus input."""
            try:
                event.app.layout.focus(message_window)
                scroll_fn(event)
            finally:
                try:
                    event.app.layout.focus(input_window)
                except Exception:
                    pass

        @scroll_kb.add("pageup")
        def _page_up(event):
            _do_scroll(event, scroll_half_page_up)

        @scroll_kb.add("pagedown")
        def _page_down(event):
            _do_scroll(event, scroll_half_page_down)

        @scroll_kb.add("c-up")
        def _scroll_up_kb(event):
            _do_scroll(event, scroll_one_line_up)

        @scroll_kb.add("c-down")
        def _scroll_down_kb(event):
            _do_scroll(event, scroll_one_line_down)

        @scroll_kb.add("c-home")
        def _scroll_top(event):
            _do_scroll(event, scroll_backward)

        @scroll_kb.add("c-end")
        def _scroll_bottom(event):
            _do_scroll(event, scroll_forward)

        # Mouse wheel
        @scroll_kb.add("<scroll-up>")
        def _mouse_scroll_up(event):
            _do_scroll(event, scroll_one_line_up)

        @scroll_kb.add("<scroll-down>")
        def _mouse_scroll_down(event):
            _do_scroll(event, scroll_one_line_down)

        # ── Application ──
        app_kwargs = dict(
            layout=Layout(root, focused_element=input_window),
            key_bindings=merge_key_bindings([kb, scroll_kb]),
            style=merge_styles([build_ptk_style()]),
            full_screen=True,
            mouse_support=True,
            refresh_interval=0.066,
        )
        try:
            self._app = Application(**app_kwargs)
        except Exception:
            # Fallback for PTY terminals (Git Bash, ConEmu, etc.)
            # where Win32 console API is unavailable.
            from prompt_toolkit.output.vt100 import Vt100_Output
            import sys as _sys
            app_kwargs["output"] = Vt100_Output.from_pty(_sys.stdout)
            self._app = Application(**app_kwargs)

        # Hook: process message queue before each render
        self._app.before_render += self._drain_queue

        # Focus input once on first render, then remove handler.
        def _focus_once(_app):
            try:
                _app.layout.focus(input_window)
            except Exception:
                pass
            try:
                _app.after_render.remove_handler(_focus_once)
            except Exception:
                pass
        self._app.after_render += _focus_once

        # Auto-scroll to bottom after streaming content renders.
        def _auto_scroll(_app):
            if self._pending_scroll:
                self._pending_scroll = False
                try:
                    self._scrollable_pane.vertical_scroll = 999999
                except Exception:
                    pass
        self._app.after_render += _auto_scroll

    # ── Key bindings ─────────────────────────────────────────

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("enter")
        def _submit(event):
            """Enter → submit input."""
            text = self._input_buffer.text.strip()
            if not text:
                return
            self._input_buffer.text = ""
            self._on_submit and self._on_submit(text)

        @kb.add("escape", "enter")
        @kb.add("c-j")
        def _newline(event):
            """Alt+Enter / Ctrl+J → insert newline."""
            self._input_buffer.insert_text("\n")

        @kb.add("c-c")
        def _interrupt(event):
            """Ctrl+C → interrupt streaming or exit."""
            if self._streaming_buf:
                # Interrupt streaming
                self._streaming_buf = ""
                self._on_interrupt and self._on_interrupt()
            else:
                # No active stream → exit
                self.exit()

        @kb.add("c-d")
        def _eof(event):
            """Ctrl+D → exit if input is empty."""
            if not self._input_buffer.text.strip():
                self.exit()

        @kb.add("escape", "c")
        def _toggle_focus(event):
            """Alt+C → toggle focus between input and messages."""
            cur = event.app.layout.current_control
            if cur == self._input_control:
                event.app.layout.focus_last()
            else:
                event.app.layout.focus(self._input_buffer)

        return kb

    # ── Message text callback ────────────────────────────────

    def _get_header_text(self) -> list[tuple[str, str]]:
        text = self._header_text or "CRUX Studio"
        return [("class:header", f"  {text}")]

    def _get_message_text(self) -> list[tuple[str, str]]:
        """Render all messages + streaming preview as formatted text.

        During splash screen: show the CRUX ASCII art animation.
        """
        # ── Splash screen ──
        if self._splash_frame >= 0:
            elapsed = time.time() - self._splash_t0
            # Cycle frames every 0.6s, exit after all frames + linger
            frame_idx = int(elapsed / 0.6)
            if frame_idx < len(SPLASH_FRAMES):
                self._splash_frame = frame_idx
                splash = SPLASH_FRAMES[frame_idx]
                # Add beast mini-glyph
                beast_art = self._beast_theme.name
                beast_glyph = ""
                from ui.flourish import BEAST_ASCII
                beast_glyph = BEAST_ASCII.get(beast_art, "")
                art_text = splash + "\n" + beast_glyph
                return [("class:header", art_text)]
            elif elapsed < 3.0:
                # Linger on last frame
                splash = SPLASH_FRAMES[-1]
                return [("class:header", splash)]
            else:
                # Done — exit splash mode
                self._splash_frame = -1

        try:
            buf = MessageBuffer()
            for role, text in self._messages:
                buf.add(role, text)

            # Append streaming preview
            if self._streaming_buf:
                buf.add("assistant", self._streaming_buf)

            return buf.render_all(width=100)
        except Exception:
            import traceback
            err = traceback.format_exc()
            logger.error("Message render failed:\n%s", err)
            return [("class:error", f"Render error: {err[:200]}")]

    def _get_status_text(self) -> list[tuple[str, str]]:
        # ── Splash mode: show themed hint ──
        if self._splash_frame >= 0:
            theme = self._beast_theme
            return [
                ("class:status", f"  {theme.icon} "),
                ("class:status.key", theme.label),
                ("class:status", f"  ·  /beast {theme.name}"),
            ]

        # ── Generating: spinner + status ──
        if self._generating and self._spinner.active:
            spinner_char = self._spinner.frame()
            base = self._status_text or "Ready."
            return [
                ("class:status.spinner", f"  {spinner_char} "),
                ("class:status", base),
            ]

        if self._status_text:
            theme = self._beast_theme
            return [
                ("class:status", f"  {theme.icon} "),
                ("class:status", self._status_text),
            ]
        hints = "Enter send · Alt+Enter newline · Ctrl+C interrupt · Shift+click select"
        if self._first_launch:
            return [("class:status", f"  {self._beast_theme.icon} Welcome!  {hints}")]
        return [("class:status", f"  {self._beast_theme.icon} {hints}")]

    # ── Queue drain (called before each render frame) ─────────

    def _drain_queue(self, _app) -> None:
        """Process all pending messages from the queue."""
        dirty = False
        stream_dirty = False
        while True:
            try:
                kind, payload = self._msg_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "message":
                role, text = payload
                self._messages.append((role, text))
                dirty = True
            elif kind == "chunk":
                self._streaming_buf += payload
                dirty = True
                stream_dirty = True
            elif kind == "commit":
                if self._streaming_buf:
                    self._messages.append(("assistant", self._streaming_buf))
                    self._streaming_buf = ""
                    dirty = True

        if dirty:
            self._app.invalidate()
        # Defer scroll-to-bottom until after the next render,
        # when content height is known and vertical_scroll clamping works.
        if stream_dirty:
            self._pending_scroll = True

    # ── Scheduling ────────────────────────────────────────────

    def _schedule(self, callback: Callable[[], None]) -> None:
        """Schedule a callback to run in the app's event loop. Thread-safe."""
        if self._app and self._app.is_running:
            try:
                async def _run():
                    callback()
                self._app.create_background_task(_run())
            except Exception:
                pass

    def _refresh(self) -> None:
        """Invalidate the UI to trigger a redraw."""
        try:
            if self._app:
                self._app.invalidate()
        except Exception:
            pass

    # ── Run loop ──────────────────────────────────────────────

    def run(self) -> None:
        """Start the terminal application. Blocking call."""
        self._running = True
        try:
            self._app.run()
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False

    async def run_async(self) -> None:
        """Start the terminal application asynchronously."""
        self._running = True
        try:
            await self._app.run_async()
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False

    @property
    def app(self) -> Application:
        return self._app
