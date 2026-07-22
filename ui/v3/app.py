"""CRUX TUI v3 — game-console style terminal UI.

Architecture:
  key → handler → reduce_ui / direct action → invalidate → render
  Worker threads → _threadsafe_call → UI updates

Built on prompt_toolkit. No event queue, no scheduler — ptk is the engine.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window, WindowAlign
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.output import create_output

from core.version import __version__ as _CRUX_VERSION
from ui.message_pane import MessagePane
from ui.message_store import MessageStore
from ui.widgets_v2 import ThinkingPanel

from .events import (
    ActivityLogged,
    CancelRequested,
    ClearScreen,
    CopyFocusedMessage,
    CopySelectedMessage,
    EnterCopyMode,
    ExitCopyMode,
    MoveCopySelection,
    NavigateBack,
    PaletteSelect,
    ResizeEvent,
    SubmitInput,
    ToggleActivity,
    ToggleDashboard,
    ToggleFocusMode,
    ToggleInteractionMode,
    UiEvent,
)
from .reducer import reduce_ui
from .state import (
    InteractionMode,
    Screen,
    ScrollMode,
    ScrollState,
    SessionView,
    StreamState,
    StreamStatus,
    initial_state,
)
from .views.activity import render_activity
from .views.input import render_input_hint, render_input_prompt
from .views.overlays import render_overlay
from .views.status import render_status

if TYPE_CHECKING:
    from .effects import Effect

logger = logging.getLogger("crux.v3")


# ── Theme / icons (time-based, no thread needed) ──────────────────

_BEASTS = [
    ("class:status-bar-beast-baihu", "🐅"),
    ("class:status-bar-beast-qinglong", "🐉"),
    ("class:status-bar-beast-zhuque", "🦅"),
    ("class:status-bar-beast-xuanwu", "🐢"),
    ("class:status-bar-beast-qilin", "🦄"),
    ("class:status-bar-beast-tengshe", "🐍"),
    ("class:status-bar-beast-yinglong", "🐲"),
]


def _tw() -> int:
    try:
        return max(shutil.get_terminal_size().columns, 40)
    except Exception:
        return 80


# ── V3App ─────────────────────────────────────────────────────────


class V3App:
    """Minimal event-driven TUI application."""

    def __init__(
        self,
        session: Any = None,  # ChatSession
        cli: Any = None,  # CruxCLI
        *,
        session_wire: Any = None,
        cwd: Path | None = None,
    ) -> None:
        self.session = session
        self.cli = cli
        self.wire = session_wire
        self.cwd = cwd or Path.cwd()

        # ── State (single source of truth, lock-protected) ──
        tw = _tw()
        th = shutil.get_terminal_size().lines
        model = getattr(session, "model", "") if session else ""
        self._state = initial_state(cols=tw, rows=th)
        self._state = self._state.__class__(
            **{
                **self._state.__dict__,
                "session": SessionView(model=model, cwd=str(self.cwd)),
            }
        )
        self._state_lock = threading.Lock()
        self._last_term_size = (self._state.terminal.cols, self._state.terminal.rows)
        self._term_cols = max(1, self._state.terminal.cols)

        # ── Message rendering ──
        self._msg_store = MessageStore()
        self.message_pane = MessagePane()
        self.message_pane._msg_store = self._msg_store
        self.thinking_panel = ThinkingPanel()
        self._setup_welcome()

        # ── Stream guards ──
        self._stream_cancelled = threading.Event()
        self._stream_last_chunk = 0.0
        self._stream_timeout_s = 120.0
        self._stream_timer: threading.Timer | None = None
        self._ui_thread = threading.current_thread()
        # Chunk buffer: worker writes, UI thread drains on render
        self._chunk_queue: list[tuple] = []
        self._chunk_lock = threading.Lock()

        # ── Effects ──
        self._effect_handlers = self._build_effect_handlers()

        # ── Input ──
        self._history = InMemoryHistory()
        self.input_buffer = Buffer(history=self._history)

        # ── Key bindings ──
        self.kb = self._build_keybindings()

        # ── Build ptk Application ──
        self._app = self._build_app()

    # ══════════════════════════════════════════════════════════════
    #  Welcome screen
    # ══════════════════════════════════════════════════════════════

    def _setup_welcome(self) -> None:
        """Configure welcome screen as message pane empty state."""
        from ui.widgets_v2 import build_welcome_formatted

        model = self._state.session.model or "CRUX"
        cwd = str(self.cwd)
        welcome_ft = build_welcome_formatted(model_name=model, cwd=cwd)

        self.message_pane.set_empty_renderer(lambda: welcome_ft)
        self.message_pane._empty_render_cache = welcome_ft
        self.message_pane._empty_render_cache_key = 1

    # ══════════════════════════════════════════════════════════════
    #  State helpers  —  direct, no queue, no scheduler
    # ══════════════════════════════════════════════════════════════

    def _threadsafe_call(self, fn, *a) -> None:
        """Call fn + invalidate. Thread-safe — runs on the CALLER's thread.
        fn must be thread-safe (stream_append has own lock; invalidate is ptk-safe).
        For state changes, use dedicated lifecycle helpers, not _reduce."""
        try:
            fn(*a) if a else fn()
            if self._app:
                self._app.invalidate()
        except Exception:
            logger.debug("_threadsafe_call failed", exc_info=True)

    def _execute_effect(self, fx: Effect) -> None:
        handler = self._effect_handlers.get(fx.kind)
        if handler:
            try:
                handler(fx)
            except Exception:
                logger.exception("Effect handler failed: %s", fx.kind)

    def _start_stream_timeout(self) -> None:
        """Arm the stream timeout timer."""
        self._cancel_stream_timeout()
        self._stream_timer = threading.Timer(self._stream_timeout_s, self._on_stream_timeout)
        self._stream_timer.daemon = True
        self._stream_timer.start()

    def _cancel_stream_timeout(self) -> None:
        if self._stream_timer:
            self._stream_timer.cancel()
            self._stream_timer = None

    def _on_stream_timeout(self) -> None:
        """Called by Timer when stream produces no chunk for _stream_timeout_s."""
        logger.warning("Stream timeout: no chunk for %.0fs — cancelling", self._stream_timeout_s)
        self._stream_cancelled.set()

    # ══════════════════════════════════════════════════════════════
    #  Effect handlers
    # ══════════════════════════════════════════════════════════════

    def _build_effect_handlers(self) -> dict[str, Any]:
        return {
            "run_model_stream": self._fx_run_stream,
            "cancel_model_stream": self._fx_cancel_stream,
            "finalize_stream": self._fx_finalize_stream,
            "copy_to_clipboard": self._fx_copy,
            "execute_command": self._fx_execute_command,
            "exit_app": self._fx_exit,
            "recalculate_layout": self._fx_noop,
            "stream_append_text": self._fx_stream_append_text,
            "stream_append_thinking": self._fx_stream_append_thinking,
            "render_chat": self._fx_noop,
            "render_thinking": self._fx_noop,
            "render_activity": self._fx_noop,
            "render_status": self._fx_noop,
            "scroll_to_bottom": self._fx_scroll_to_bottom,
            "scroll_sync": self._fx_scroll_sync,
            "clear_messages": self._fx_clear_messages,
            "noop": self._fx_noop,
        }

    def _fx_run_stream(self, fx: Effect) -> None:
        """Start model stream. Worker writes chunks to queue; UI thread drains.
        Worker never touches widgets — no stdout, no Window attrs, no focus."""
        text = (fx.payload or {}).get("text", "")
        image_url = (fx.payload or {}).get("image_url")

        self._stream_cancelled.clear()
        self._stream_last_chunk = time.monotonic()
        self._start_stream_timeout()

        # ── UI thread ops: stream_start, clear, user message ──
        if not image_url:
            self.message_pane.append_message("user", text)
            self._msg_store.append("user", text)
        self.message_pane.stream_start("crux")
        self.thinking_panel.clear()
        self._app.invalidate()

        def worker():
            import time as _time

            t0 = _time.monotonic()
            cancelled = False
            try:
                gen = self.session.send_stream(text)
                for kind, payload in gen:
                    if self._stream_cancelled.is_set():
                        cancelled = True
                        break
                    self._stream_last_chunk = _time.monotonic()
                    self._start_stream_timeout()
                    with self._chunk_lock:
                        if kind == "text":
                            self._chunk_queue.append(("text", str(payload)))
                        elif kind == "thinking":
                            self._chunk_queue.append(("thinking", str(payload)))
                        elif kind == "error":
                            self._chunk_queue.append(("error", str(payload)))
                    self._app.invalidate()
                elapsed = _time.monotonic() - t0
                with self._chunk_lock:
                    if cancelled:
                        self._chunk_queue.append(("info", f"[Cancelled] {elapsed:.0f}s timeout"))
                    else:
                        self._chunk_queue.append(("info", f"[Done] {elapsed:.1f}s"))
                    self._chunk_queue.append(("done",))
                self._app.invalidate()
            except Exception as e:
                logger.exception("Stream worker: %s", e)
                with self._chunk_lock:
                    self._chunk_queue.append(("error", f"{type(e).__name__}: {e!s}"))
                    self._chunk_queue.append(("done",))
                self._app.invalidate()
            finally:
                self._cancel_stream_timeout()

        threading.Thread(target=worker, daemon=True, name="v3-stream").start()

    def _fx_cancel_stream(self, _fx: Effect) -> None:
        self._stream_cancelled.set()

    def _fx_finalize_stream(self, _fx: Effect) -> None:
        """Stream done — tell MessagePane, ThinkingPanel, and clean up."""
        self.message_pane.stream_end()
        self.thinking_panel.done()
        self._cancel_stream_timeout()
        if self.wire:
            try:
                self.wire.record_turn("assistant", "[streamed]")
            except Exception:
                logger.debug("silent except", exc_info=True)

    def _fx_copy(self, fx: Effect) -> None:
        """Copy last assistant message to clipboard."""
        msg = self._msg_store.last_assistant() if self._msg_store else None
        if msg is None:
            return
        as_md = (fx.payload or {}).get("as_markdown", False)  # noqa: F841 (TODO: markdown extraction)
        text = msg.text  # TODO: markdown extraction when as_md=True
        try:
            import pyperclip

            pyperclip.copy(text)
            self._log_activity("✓", "class:activity-done", "Copied to clipboard")
        except Exception:
            self._log_activity("✗", "class:activity-fail", "Clipboard unavailable")

    def _fx_execute_command(self, fx: Effect) -> None:
        cmd = (fx.payload or {}).get("command", "").strip()
        if not cmd:
            return
        # ── Built-in commands ──
        if cmd in ("/q", "/quit", "/exit"):
            self._request_exit()
            self._app.exit()
            return
        if cmd in ("/dashboard",):
            self._reduce_only(ToggleDashboard())  # state only, no recursive effects
            return
        if cmd.startswith("/theme "):
            # Forward to cli
            pass
        if cmd in ("/clear", "/cls"):
            self._reduce(ClearScreen())
            return
        # ── Delegate to CruxCLI ──
        if self.cli:
            try:
                self.cli.dispatch(cmd)
            except Exception:
                self._log_activity("✗", "class:activity-fail", f"Command failed: {cmd}")

    def _fx_exit(self, _fx: Effect) -> None:
        self._request_exit()
        self._app.exit()

    def _fx_stream_append_text(self, fx: Effect) -> None:
        """Route text chunks to MessagePane + sync scroll state."""
        text = (fx.payload or {}).get("text", "")
        if text:
            self.message_pane.stream_append(text)
        self._sync_scroll_to_pane()

    def _fx_stream_append_thinking(self, fx: Effect) -> None:
        """Route thinking chunks to ThinkingPanel."""
        text = (fx.payload or {}).get("text", "")
        if text:
            self.thinking_panel.append(text)

    def _fx_scroll_sync(self, _fx: Effect) -> None:
        """Sync UiState.scroll state to MessagePane."""
        self._sync_scroll_to_pane()

    def _fx_scroll_to_bottom(self, _fx: Effect) -> None:
        """Force scroll to bottom."""
        self.message_pane.scroll_to_bottom()
        self.message_pane._pinned = True

    def _log_activity(self, icon: str, style: str, msg: str) -> None:
        """Append to activity log via event (thread-safe, no direct state mutation)."""
        self._reduce_only(ActivityLogged(icon=icon, style=style, msg=msg))

    def _sync_scroll_to_pane(self) -> None:
        """Push UiState.scroll → MessagePane (FOLLOW/MANUAL + offset)."""
        sc = self._state.scroll
        if sc.mode == ScrollMode.FOLLOW:
            self.message_pane.scroll_to_bottom()
            self.message_pane._pinned = True
        else:
            self.message_pane._pinned = False

    def _check_resize(self) -> None:
        """Check if terminal size changed, post ResizeEvent if so."""
        try:
            import shutil

            s = shutil.get_terminal_size((80, 24))
            cur = (s.columns, s.lines)
        except Exception:
            return
        if cur != self._last_term_size:
            self._last_term_size = cur
            self._term_cols = max(1, cur[0])
            self._reduce_only(ResizeEvent(cols=cur[0], rows=cur[1]))

    def _fx_clear_messages(self, _fx: Effect) -> None:
        self.message_pane.clear()

    def _fx_noop(self, _fx: Effect) -> None:
        pass

    # ══════════════════════════════════════════════════════════════
    #  Key bindings (produce events, never mutate state directly)
    # ══════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════
    #  Key controllers  —  game-console style: one key = one handler.
    #  No shared queue. No reducer dependency. One key crash can't
    #  take down another key. Direct state write + invalidate.
    # ══════════════════════════════════════════════════════════════

    def _emit_key(self, name: str, fn) -> None:
        try:
            self._drain_chunks()
            fn()
        except Exception:
            logger.exception("Key [%s] handler crashed", name)

    def _reduce(self, event: UiEvent) -> None:
        """Reduce state + execute effects + invalidate. Direct, no queue.
        MUST run on the UI thread — workers use _threadsafe_call instead."""
        assert threading.current_thread() is self._ui_thread, (
            "_reduce called from worker thread. Use _threadsafe_call for cross-thread."
        )
        with self._state_lock:
            new_state, effects = reduce_ui(self._state, event)
            self._state = new_state
            for fx in effects:
                self._execute_effect(fx)
        self._app.invalidate()
        # ptk's invalidate() no-ops when _invalidated is already True (e.g. a
        # worker-thread invalidate is still pending redraw). After a stream
        # finishes this is the common case, so key-driven state changes (F12,
        # F7, etc.) never repaint. Force a redraw on the next loop iteration
        # to guarantee the new state is reflected.
        try:
            _loop = self._app.loop
            if _loop is not None and not _loop.is_closed():
                _loop.call_soon(self._app._redraw)
        except Exception:
            logger.debug("force redraw schedule failed", exc_info=True)

    def _reduce_only(self, event: UiEvent) -> None:
        """Reduce state only — no effects, no invalidate. For chained operations."""
        with self._state_lock:
            self._state, _ = reduce_ui(self._state, event)

    def _drain_chunks(self) -> None:
        """Consume chunk queue on UI thread. Called before any key handler.
        All widget mutations happen here — on the UI thread only."""
        # Detect terminal resize here (UI thread) — must NOT happen inside
        # render functions, which ptk requires to be pure. _check_resize
        # mutates state via _reduce_only; running it during render corrupts
        # the layout tree and causes focus loss / broken keybindings.
        self._check_resize()
        with self._chunk_lock:
            if not self._chunk_queue:
                return
            chunks = self._chunk_queue
            self._chunk_queue = []
        for chunk in chunks:
            kind = chunk[0]
            if kind == "text":
                # Transition THINKING → STREAMING on first chunk
                if self._state.stream.status == StreamStatus.THINKING:
                    with self._state_lock:
                        self._state = replace(
                            self._state,
                            stream=StreamState(status=StreamStatus.STREAMING, tool_seq=self._state.stream.tool_seq),
                        )
                self.message_pane.stream_append(str(chunk[1]))
            elif kind == "thinking":
                self.thinking_panel.append(str(chunk[1]))
            elif kind == "error":
                self.message_pane.append_error(str(chunk[1]))
            elif kind == "info":
                self.message_pane.append_info(str(chunk[1]))
            elif kind == "done":
                self.message_pane.stream_end()
                self.thinking_panel.done()
                self._cancel_stream_timeout()
                # Reset state to IDLE so Ctrl+C exits, not cancels
                with self._state_lock:
                    self._state = replace(
                        self._state,
                        stream=StreamState(status=StreamStatus.IDLE, tool_seq=self._state.stream.tool_seq),
                        scroll=ScrollState(mode=ScrollMode.FOLLOW),
                    )
                # Restore focus to input window — without this, layout recomputes
                # (thinking/activity panels collapsing to height 0) leave focus null
                # and most non-eager keybindings die after the first reply.
                try:
                    self._app.layout.focus(self.input_win)
                except Exception:
                    logger.debug("focus restore after stream done failed", exc_info=True)

    # ── Core ────────────────────────────────────────────────────

    def _key_interrupt(self) -> None:
        with self._state_lock:
            streaming = self._state.stream.status in (StreamStatus.THINKING, StreamStatus.STREAMING)
        if streaming:
            self._reduce(CancelRequested())
        else:
            self._app.exit()

    def _key_quit(self) -> None:
        self._app.exit()

    def _key_clear_screen(self) -> None:
        self.message_pane.clear()
        self.thinking_panel.clear()
        self._app.invalidate()

    def _key_paste(self, event: Any) -> None:
        self.input_buffer.paste_from_clipboard(event.app.clipboard.get_data())

    def _key_reset_input(self) -> None:
        self.input_buffer.reset()

    def _key_escape(self) -> None:
        s = self._state.screen
        if s != Screen.MAIN:
            self._reduce(NavigateBack())
            return
        if self._state.interaction.mode == InteractionMode.COPY:
            self._reduce(ToggleInteractionMode(target=InteractionMode.NORMAL))
            return
        self._reduce(CancelRequested())

    # ── Input ───────────────────────────────────────────────────

    def _key_newline(self) -> None:
        self.input_buffer.insert_text("\n")

    def _key_submit(self, event: Any) -> None:
        p = getattr(self._state, "palette", None)
        if p and p.open:
            self._reduce(PaletteSelect())
            return
        if self._state.interaction.mode == InteractionMode.COPY:
            return
        buf = event.current_buffer
        if buf is None:
            return
        text = buf.text.strip()
        buf.reset()
        if not text:
            return
        if text in ("/q", "/quit", "/exit"):
            self._app.exit()
            return
        self._reduce(SubmitInput(text))

    # ── Scroll ──────────────────────────────────────────────────

    def _key_pageup(self) -> None:
        self.message_pane.scroll_page_up()
        self._app.invalidate()

    def _key_pagedown(self) -> None:
        self.message_pane.scroll_page_down()
        self._app.invalidate()

    def _key_scroll_top(self) -> None:
        self.message_pane.scroll_to_top()
        self._app.invalidate()

    def _key_scroll_bottom(self) -> None:
        self.message_pane.scroll_to_bottom()
        self._app.invalidate()

    # ── Palette ─────────────────────────────────────────────────

    def _key_palette_toggle(self) -> None:
        from .events import TogglePalette

        self._reduce(TogglePalette())

    def _key_palette_up(self) -> None:
        if bool(getattr(self._state, "palette", None) and getattr(self._state.palette, "open", False)):
            from .events import PaletteMoveUp

            self._reduce(PaletteMoveUp())

    def _key_palette_down(self) -> None:
        if bool(getattr(self._state, "palette", None) and getattr(self._state.palette, "open", False)):
            from .events import PaletteMoveDown

            self._reduce(PaletteMoveDown())

    # ── Mode toggles ────────────────────────────────────────────

    def _key_focus_mode(self) -> None:
        self._reduce(ToggleFocusMode())

    def _key_interaction_mode(self) -> None:
        self._reduce(ToggleInteractionMode())

    def _key_toggle_activity(self) -> None:
        self._reduce(ToggleActivity())

    def _key_toggle_thinking_pin(self) -> None:
        self.thinking_panel.toggle_pin()
        self._app.invalidate()

    # ── Copy ────────────────────────────────────────────────────

    def _key_quick_copy(self, event: Any, as_markdown: bool = False) -> None:
        if event.app.current_buffer is self.input_buffer:
            # Focused on input — must insert the character, not swallow it,
            # otherwise users can't type 'c' or 'C' into the input box.
            event.current_buffer.insert_text("C" if as_markdown else "c")
            return
        self._reduce(CopyFocusedMessage(as_markdown=as_markdown))

    def _key_enter_copy_mode(self) -> None:
        if self._state.interaction.mode == InteractionMode.COPY:
            self._reduce(ExitCopyMode())
            return
        total = len(self._msg_store)
        if total > 0:
            self._reduce(EnterCopyMode(total_messages=total))

    def _key_copy_move_up(self) -> None:
        total = len(self._msg_store)
        self._reduce(MoveCopySelection(delta=-1, total=total))

    def _key_copy_move_down(self) -> None:
        total = len(self._msg_store)
        self._reduce(MoveCopySelection(delta=1, total=total))

    def _key_copy_selected(self) -> None:
        idx = self._state.interaction.focus_idx
        msg = self._msg_store.get(idx)
        if msg:
            self._reduce(CopySelectedMessage())
            try:
                import pyperclip

                pyperclip.copy(msg.text)
            except Exception:
                logger.debug("Clipboard copy failed", exc_info=True)
        self._reduce(ExitCopyMode())

    # ── Vim ─────────────────────────────────────────────────────

    def _key_vim_up(self) -> None:
        self.message_pane.scroll_up(3)
        self._app.invalidate()

    def _key_vim_down(self) -> None:
        self.message_pane.scroll_down(3)
        self._app.invalidate()

    def _key_vim_top(self) -> None:
        self.message_pane.scroll_to_top()
        self._app.invalidate()

    def _key_vim_bottom(self) -> None:
        self.message_pane.scroll_to_bottom()
        self._app.invalidate()

    # ── Registration ────────────────────────────────────────────

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()
        _copy = Condition(lambda: self._state.interaction.mode == InteractionMode.COPY)
        _vim = Condition(lambda: self._state.interaction.mode == InteractionMode.VIM)

        # Shortcut: key → isolated handler (no event arg)
        def _on(key, *opts, handler, eager=False, filter=None):
            kwargs = {"eager": eager, "save_before": lambda e: False}
            if filter is not None:
                kwargs["filter"] = filter
            kb.add(key, *opts, **kwargs)(lambda e: self._emit_key(key, handler))

        # Shortcut: key → isolated handler (needs event arg)
        def _one(key, *opts, handler, eager=False, filter=None):
            kwargs = {"eager": eager, "save_before": lambda e: False}
            if filter is not None:
                kwargs["filter"] = filter
            kb.add(key, *opts, **kwargs)(lambda e: self._emit_key(key, lambda: handler(e)))

        # Core
        _on("c-c", handler=self._key_interrupt)
        _on("c-q", handler=self._key_quit)
        _on("c-l", handler=self._key_clear_screen, eager=True)
        _one("c-v", handler=self._key_paste)
        _on("c-k", handler=self._key_reset_input)
        _on("escape", "escape", handler=self._key_reset_input)
        _on("escape", handler=self._key_escape)
        # Input
        _on("escape", "enter", handler=self._key_newline)
        _on("c-j", handler=self._key_newline)
        _one("enter", handler=self._key_submit)
        # Scroll
        _on("pageup", handler=self._key_pageup, eager=True)
        _on("pagedown", handler=self._key_pagedown, eager=True)
        _on("c-home", handler=self._key_scroll_top, eager=True)
        _on("c-end", handler=self._key_scroll_bottom, eager=True)
        # Palette
        _on("c-p", handler=self._key_palette_toggle)
        _on("up", handler=self._key_palette_up)
        _on("down", handler=self._key_palette_down)
        # Modes
        _on("f12", handler=self._key_focus_mode, eager=True)
        _on("f7", handler=self._key_interaction_mode, eager=True)
        _on("f8", handler=self._key_toggle_activity, eager=True)
        _on("f6", handler=self._key_toggle_thinking_pin, eager=True)
        # Copy
        _one("c", handler=lambda e: self._key_quick_copy(e))
        _one("C", handler=lambda e: self._key_quick_copy(e, as_markdown=True))
        _on("f3", handler=self._key_enter_copy_mode, eager=True)
        _on("up", filter=_copy, handler=self._key_copy_move_up)
        _on("down", filter=_copy, handler=self._key_copy_move_down)
        _on("c", filter=_copy, handler=self._key_copy_selected)
        # Vim
        _on("j", filter=_vim, handler=self._key_vim_down)
        _on("k", filter=_vim, handler=self._key_vim_up)
        _on("g", "g", filter=_vim, handler=self._key_vim_top)
        _on("G", filter=_vim, handler=self._key_vim_bottom)

        return kb

    # ══════════════════════════════════════════════════════════════
    #  Layout (prompt_toolkit as rendering backend only)
    # ══════════════════════════════════════════════════════════════

    def _build_app(self) -> Application:
        # ── Header: left (beast + logo) | right (model + ◎ clock) ──
        def _header_left():
            bstyle, bicon = _BEASTS[int(time.time() / 2.0) % len(_BEASTS)]
            return FormattedText(
                [
                    (bstyle, f" {bicon} "),
                    ("class:header-logo", f"CRUX Studio v{_CRUX_VERSION}"),
                    ("class:header-sep", " "),
                ]
            )

        def _header_right():
            s = self._state
            model = s.session.model or "CRUX"
            now = datetime.now().strftime("%H:%M")
            return FormattedText(
                [
                    ("class:header-model", f" {model} "),
                    ("class:header-latency", ["◎", "◉", "○", "◉"][int(time.time() * 2.5) % 4] + " "),
                    ("class:status-bar-context", now),
                    ("", " "),
                ]
            )

        def _header_fill():
            left_vis = 2 + 2 + len(f"CRUX Studio v{_CRUX_VERSION}")
            model = self._state.session.model or "CRUX"
            right_vis = 1 + len(model) + 1 + 2 + 1 + 5
            pad = max(1, self._term_cols - left_vis - right_vis)
            return FormattedText([("class:header-sep", "─" * pad)])

        header = VSplit(
            [
                Window(
                    content=FormattedTextControl(_header_left),
                    style="class:header-bar",
                    always_hide_cursor=True,
                    dont_extend_width=True,
                ),
                Window(content=FormattedTextControl(_header_fill), style="class:header-bar"),
                Window(
                    content=FormattedTextControl(_header_right),
                    style="class:header-bar",
                    always_hide_cursor=True,
                    align=WindowAlign.RIGHT,
                    dont_extend_width=True,
                ),
            ],
            height=1,
            style="class:header-bar",
        )

        # ── Separator ──
        def _sep():
            return FormattedText([("class:header-sep", "╠" + "═" * (self._term_cols - 2) + "╣")])

        sep = Window(content=FormattedTextControl(_sep), height=1, style="class:header-bar", always_hide_cursor=True)

        # ── Thinking Panel ──
        def _thinking():
            return self.thinking_panel.render(_tw())

        thinking_win = Window(
            content=FormattedTextControl(_thinking),
            height=lambda: self.thinking_panel.height(_tw()),
            style="class:message-area",
            always_hide_cursor=True,
            dont_extend_height=True,
        )

        # ── Status ──
        def _status():
            return render_status(self._state)

        status = Window(
            content=FormattedTextControl(_status), height=1, style="class:status-bar", always_hide_cursor=True
        )

        # ── Activity ──
        def _activity():
            return render_activity(self._state)

        activity = Window(
            content=FormattedTextControl(_activity),
            height=lambda: 3 if self._state.activity.expanded or self._state.stream.tool_name else 0,
            style="class:message-area",
            always_hide_cursor=True,
            dont_extend_height=True,
        )

        # ── Input ──
        input_ctrl = BufferControl(
            buffer=self.input_buffer,
            input_processors=[BeforeInput(lambda: "║ " + render_input_prompt(self._state))],
            focusable=True,
        )
        self.input_win = Window(
            content=input_ctrl,
            height=Dimension(min=1, max=10),
            style="class:input-field",
            dont_extend_height=True,
            wrap_lines=False,
        )

        # ── Input bottom border ──
        def _input_bottom():
            _tw()
            hint_ft = render_input_hint(self._state)
            hint_text = "".join(t for _, t in hint_ft) if hint_ft else ""
            hint_len = len(hint_text) if hint_text else 0
            bars = max(1, self._term_cols - hint_len - 2)
            pieces = [("class:input-border", f"╚{'─' * bars}")]
            if hint_text:
                pieces.append(("class:welcome-desc", hint_text))
            pieces.append(("class:input-border", "╝"))
            return FormattedText(pieces)

        input_bottom = Window(
            content=FormattedTextControl(_input_bottom), height=1, style="class:input-border", always_hide_cursor=True
        )

        # ── Overlay ──
        def _overlay():
            return render_overlay(self._state)

        overlay = Window(content=FormattedTextControl(_overlay), always_hide_cursor=True)
        overlay_mode = Condition(
            lambda: (
                self._state.screen != Screen.MAIN
                or bool(getattr(self._state, "palette", None) and getattr(self._state.palette, "open", False))
            )
        )

        # ── Focus mode filter: hide chrome when F12 is pressed ──
        _not_focus = Condition(lambda: not self._state.focus_mode)

        # ── Assemble ──
        # Message area
        msg_area = HSplit(
            [
                self.message_pane.pane,
                ConditionalContainer(thinking_win, filter=_not_focus),
                ConditionalContainer(activity, filter=_not_focus),
            ],
            style="class:app",
        )

        root = HSplit(
            [
                ConditionalContainer(overlay, filter=overlay_mode),
                ConditionalContainer(
                    header, filter=Condition(lambda: not self._state.focus_mode and self._state.screen == Screen.MAIN)
                ),
                ConditionalContainer(
                    sep, filter=Condition(lambda: not self._state.focus_mode and self._state.screen == Screen.MAIN)
                ),
                ConditionalContainer(msg_area, filter=Condition(lambda: True)),  # B4 fix: always show messages
                self.input_win,
                ConditionalContainer(input_bottom, filter=_not_focus),
                ConditionalContainer(status, filter=_not_focus),
            ],
            style="class:app",
        )

        # ── I/O: Git Bash Windows fix — force Vt100_Output when TERM is set ──
        from prompt_toolkit.input import create_input

        ptk_input = create_input(stdin=sys.stdin)
        if sys.platform == "win32" and "TERM" in os.environ:
            from prompt_toolkit.output.vt100 import Vt100_Output

            ptk_output = Vt100_Output.from_pty(sys.stdout, term=os.environ.get("TERM"))
        else:
            ptk_output = create_output(stdout=sys.stdout)

        app = Application(
            layout=Layout(root, focused_element=self.input_win),
            key_bindings=self.kb,
            input=ptk_input,
            output=ptk_output,
            full_screen=True,
            mouse_support=False,
            enable_page_navigation_bindings=False,
        )
        # Hook invalidate to drain chunks on UI thread before render.
        # Worker-thread invalidates schedule drain via event loop.
        _orig_invalidate = app.invalidate

        def _invalidate_with_drain():
            if threading.current_thread() is self._ui_thread:
                self._drain_chunks()
            elif hasattr(app, "loop") and app.loop and not app.loop.is_closed():
                app.loop.call_soon_threadsafe(self._drain_chunks)
            _orig_invalidate()

        app.invalidate = _invalidate_with_drain
        return app

    # ══════════════════════════════════════════════════════════════
    #  Lifecycle
    # ══════════════════════════════════════════════════════════════

    def _request_exit(self) -> None:
        self._cancel_stream_timeout()

    def run(self) -> None:
        """Start the application. ptk handles the game loop — we just call run()."""
        self._app.invalidate()  # force first render with welcome screen
        try:
            self._app.run()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception("V3App.run crashed: %s", e)
            sys.stderr.write(f"\n[CRUX TUI v3 crashed: {type(e).__name__}: {e}]\n")
            sys.stderr.flush()

    def shutdown(self) -> None:
        self._request_exit()
        self._cancel_stream_timeout()
