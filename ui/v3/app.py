"""CRUX TUI v3 — application entry point.

Event-driven architecture:
  1. Background threads post UiEvent → SimpleQueue
  2. Main loop drains queue → reduce_ui → effects → render
  3. Views read immutable UiState, never mutate

Single refresh timer (scheduler) replaces three independent threads.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import SimpleQueue
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
    CancelRequested,
    ClearScreen,
    CopyFocusedMessage,
    CopySelectedMessage,
    EnterCopyMode,
    ExitCopyMode,
    ExitRequested,
    MoveCopySelection,
    NavigateBack,
    PaletteSelect,
    ResizeEvent,
    ScrollBy,
    ScrollTo,
    StreamDone,
    StreamError,
    StreamToolStarted,
    SubmitInput,
    TickEvent,
    ToggleActivity,
    ToggleDashboard,
    ToggleFocusMode,
    ToggleInteractionMode,
    UiEvent,
)
from .reducer import reduce_ui
from .runtime_bridge import post_event, set_app_ref, set_drain_fn, set_event_queue
from .scheduler import Scheduler
from .state import (
    InteractionMode,
    Screen,
    ScrollMode,
    SessionView,
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

        # ── Event queue ──
        self._queue: SimpleQueue[UiEvent] = SimpleQueue()
        set_event_queue(self._queue)

        # ── State ──
        tw = _tw()
        th = shutil.get_terminal_size().lines
        model = getattr(session, "model", "") if session else ""
        self._state = initial_state(cols=tw, rows=th)
        self._state = self._state.__class__(
            **{
                **self._state.__dict__,
                "session": SessionView(
                    model=model,
                    cwd=str(self.cwd),
                ),
            }
        )

        # ── State lock (protects _state read/write from invalidate callbacks) ──
        self._state_lock = threading.Lock()

        # ── Scheduler: post events + drain + invalidate (UI thread only) ──
        self._scheduler = Scheduler(idle_interval=0.25, active_interval=0.1)
        self._scheduler.on_tick(lambda: post_event(TickEvent()))
        self._scheduler.on_tick(self._check_resize)
        self._scheduler.on_tick(lambda: self._app.call_soon_threadsafe(self._drain_and_reduce) if self._app else None)

        # Anim thread removed (B1 fix: scheduler is sole render driver)
        self._running = False
        self._last_term_size = (self._state.terminal.cols, self._state.terminal.rows)
        self._term_cols = max(1, self._state.terminal.cols)

        # ── Message rendering (reuses existing MessagePane) ──
        self._msg_store = MessageStore()
        self.message_pane = MessagePane()
        self.message_pane._msg_store = self._msg_store
        self.thinking_panel = ThinkingPanel()
        self._setup_welcome()
        self._closing = False

        # ── Effects dispatcher ──
        self._effect_handlers = self._build_effect_handlers()

        # ── Input buffer ──
        self._history = InMemoryHistory()
        self.input_buffer = Buffer(
            accept_handler=self._on_input_accept,
            history=self._history,
        )

        # ── Key bindings ──
        self.kb = self._build_keybindings()

        # ── Build ptk Application ──
        self._app = self._build_app()
        set_app_ref(self._app)
        set_drain_fn(self._drain_and_reduce)

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
    #  Event loop integration
    # ══════════════════════════════════════════════════════════════

    def _drain_and_reduce(self) -> None:
        """Drain the event queue and apply all events to state.

        Called from a before_render handler or timer.  This is the ONLY
        place where _state is modified on the main thread.
        """
        with self._state_lock:
            self._drain_and_reduce_locked()

    def _drain_and_reduce_locked(self) -> None:
        """Inner drain loop — caller must hold _state_lock."""
        drained = 0
        while drained < 50:  # safety limit: max 50 events per frame
            try:
                event = self._queue.get_nowait()
            except Exception:
                break
            drained += 1
            try:
                new_state, effects = reduce_ui(self._state, event)
                self._state = new_state
                for fx in effects:
                    self._execute_effect(fx)
            except Exception:
                logger.exception("reduce_ui failed for event %s", type(event).__name__)

    def _execute_effect(self, fx: Effect) -> None:
        """Execute a side-effect."""
        handler = self._effect_handlers.get(fx.kind)
        if handler:
            try:
                handler(fx)
            except Exception:
                logger.exception("Effect handler failed: %s", fx.kind)

    def _sync_terminal_size(self):
        """Update UiState.terminal from actual terminal dimensions."""
        try:
            tw = _tw()
            th = shutil.get_terminal_size().lines
            st = self._state
            if st.terminal.cols != tw or st.terminal.rows != th:
                from .state import TerminalState

                self._state = st.__class__(**{**st.__dict__, "terminal": TerminalState(cols=tw, rows=th)})
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

    def _ui(self, fn, *a, _force: bool = False):
        """Thread-safe UI callback — call fn + invalidate from any thread."""
        self._sync_terminal_size()
        try:
            if a:
                fn(*a)
            else:
                fn()
        except Exception:
            logger.warning("_ui callback failed", exc_info=True)
        try:
            app = self._app
            if app is not None and app.is_running:
                now = time.monotonic()
                last = getattr(self, "_last_invalidate", 0.0)
                if _force or now - last > 0.030:
                    self._last_invalidate = now
                    if hasattr(app, "call_soon_threadsafe"):
                        app.call_soon_threadsafe(app.invalidate)
                    else:
                        app.invalidate()
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

    def _post_and_invalidate(self, event: UiEvent) -> None:
        """Post event + drain + render in one synchronous sequence (UI thread)."""
        post_event(event)  # 1. enqueue
        self._drain_and_reduce()  # 2. process NOW (includes this event)
        try:
            self._app.invalidate()  # 3. render with updated state
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

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
        """Start model stream in background thread.

        Worker only updates MessagePane/ThinkingPanel via _ui().
        State transitions (THINKING→STREAMING→DONE→IDLE) happen through
        the reducer — the worker must NOT mutate self._state directly.
        """
        text = (fx.payload or {}).get("text", "")
        image_url = (fx.payload or {}).get("image_url")

        # ── Show user message + start assistant stream ──
        if not image_url:
            self.message_pane.append_message("user", text)
            self._msg_store.append("user", text)
        self.message_pane.stream_start("crux")
        self.thinking_panel.clear()

        def worker():
            import time as _time

            t0 = _time.monotonic()
            tool_count = 0
            try:
                if image_url:
                    gen = self.session.send_stream("Describe this image.", image_url=image_url)
                else:
                    gen = self.session.send_stream(text)
                for kind, payload in gen:
                    if kind == "text":
                        self._ui(self.message_pane.stream_append, str(payload))
                    elif kind == "thinking":
                        self._ui(self.thinking_panel.append, str(payload))
                    elif kind == "info" and ("执行" in str(payload) or "生成" in str(payload)):
                        tool_count += 1
                        # Post events for tool tracking (reducer owns state)
                        from .runtime_bridge import post_event as _pe
                        from .runtime_bridge import trigger_drain as _td

                        _pe(StreamToolStarted(str(payload)[:40], str(payload)))
                        _td()
                    elif kind == "error":
                        self._ui(self.message_pane.append_error, str(payload))
                elapsed = _time.monotonic() - t0
                self._ui(self.message_pane.append_info, f"[Done] {elapsed:.1f}s · {tool_count} tools")
                self._ui(self.message_pane.stream_end, _force=True)
                self._ui(self.thinking_panel.done)
                # Post stream-done event so reducer transitions state to IDLE
                from .runtime_bridge import post_event as _pe2
                from .runtime_bridge import trigger_drain as _td2

                _pe2(StreamDone(elapsed=elapsed, tool_count=tool_count))
                _td2()
                # Restore focus
                self._ui(self._restore_focus, _force=True)
            except Exception as e:
                self._ui(self.message_pane.append_error, f"{type(e).__name__}: {e!s}")
                self._ui(self.message_pane.stream_end, _force=True)
                from .runtime_bridge import post_event as _pe3
                from .runtime_bridge import trigger_drain as _td3

                _pe3(StreamError(error_type=type(e).__name__, message=str(e)))
                _td3()
                self._ui(self._restore_focus, _force=True)

        t = threading.Thread(target=worker, daemon=True, name="v3-stream")
        t.start()
        self._scheduler.set_streaming(True)

    def _fx_cancel_stream(self, _fx: Effect) -> None:
        self._scheduler.set_streaming(False)

    def _fx_finalize_stream(self, _fx: Effect) -> None:
        """Stream done — tell MessagePane, ThinkingPanel, and clean up."""
        self.message_pane.stream_end()
        self.thinking_panel.done()
        self._scheduler.set_streaming(False)
        if self.wire:
            try:
                self.wire.record_turn("assistant", "[streamed]")
            except Exception:
                import logging

                logging.getLogger(__name__).debug("silent except", exc_info=True)

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
            post_event(ToggleDashboard())  # no recursive drain from effect handler
            return
        if cmd.startswith("/theme "):
            # Forward to cli
            pass
        if cmd in ("/clear", "/cls"):
            self._post_and_invalidate(ClearScreen())
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
        """Append to activity log (UI thread only)."""
        old = self._state.activity
        items = [*list(old.items), (icon, style, msg)]
        if len(items) > 500:
            items = items[-500:]
        self._state = self._state.__class__(
            **{
                **self._state.__dict__,
                "activity": old.__class__(items=tuple(items), expanded=old.expanded),
            }
        )

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
            post_event(ResizeEvent(cols=cur[0], rows=cur[1]))

    def _fx_clear_messages(self, _fx: Effect) -> None:
        self.message_pane.clear()

    def _fx_noop(self, _fx: Effect) -> None:
        pass

    # ══════════════════════════════════════════════════════════════
    #  Key bindings (produce events, never mutate state directly)
    # ══════════════════════════════════════════════════════════════

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        # ── Palette modal guard ──
        _palette_open = Condition(
            lambda: bool(getattr(self._state, "palette", None) and getattr(self._state.palette, "open", False))
        )

        @kb.add("c-c")
        def _(event):
            with self._state_lock:
                streaming = self._state.stream.status in (StreamStatus.THINKING, StreamStatus.STREAMING)
            if streaming:
                self._post_and_invalidate(CancelRequested())
            else:
                self._post_and_invalidate(ExitRequested())

        @kb.add("c-q")
        def _(event):
            self._post_and_invalidate(ExitRequested())

        # ── Newline ──
        @kb.add("escape", "enter")
        @kb.add("c-j")
        def _(event):
            self.input_buffer.insert_text("\n")

        # ── Scroll ──
        @kb.add("pageup", eager=True)
        def _(event):
            self.message_pane.scroll_page_up()
            self._app.invalidate()

        @kb.add("pagedown", eager=True)
        def _(event):
            self.message_pane.scroll_page_down()
            self._app.invalidate()

        @kb.add("c-p")
        def _(event):
            """Ctrl+P: Toggle command palette."""
            from .events import TogglePalette

            self._post_and_invalidate(TogglePalette())

        # ── Palette navigation (when open) ──
        @kb.add("up")
        def _palette_up(event):
            if bool(getattr(self._state, "palette", None) and getattr(self._state.palette, "open", False)):
                from .events import PaletteMoveUp

                self._post_and_invalidate(PaletteMoveUp())

        @kb.add("down")
        def _palette_down(event):
            if bool(getattr(self._state, "palette", None) and getattr(self._state.palette, "open", False)):
                from .events import PaletteMoveDown

                self._post_and_invalidate(PaletteMoveDown())

        @kb.add("enter")
        def _(event):
            # Palette open → select item
            p = getattr(self._state, "palette", None)
            if p and p.open:
                self._post_and_invalidate(PaletteSelect())
                return
            if self._state.interaction.mode == InteractionMode.COPY:
                return  # Copy mode: c to copy, Esc to exit, Enter does nothing
            buf = event.current_buffer
            text = buf.text.strip()
            buf.reset()
            if not text:
                return
            if text in ("/q", "/quit", "/exit"):
                self._app.exit()
                return
            # Post SubmitInput — reducer + _fx_run_stream handles the rest
            self._post_and_invalidate(SubmitInput(text))

        @kb.add("escape")
        def _palette_close(event):
            if bool(getattr(self._state, "palette", None) and getattr(self._state.palette, "open", False)):
                from .events import TogglePalette

                self._post_and_invalidate(TogglePalette())

        @kb.add("c-home", eager=True)
        def _(event):
            self._post_and_invalidate(ScrollTo("top"))

        @kb.add("c-end", eager=True)
        def _(event):
            self._post_and_invalidate(ScrollTo("bottom"))

        # ── Mode toggles: direct state mutation + invalidate ──
        # Bypass the event/reducer pipeline because these keys are captured
        # before ptk's event loop can process them. Direct mutation is safe
        # since we're on the UI thread.
        @kb.add("f12", eager=True)
        def _(event):
            self._post_and_invalidate(ToggleFocusMode())

        @kb.add("f7", eager=True)
        def _(event):
            self._post_and_invalidate(ToggleInteractionMode())

        @kb.add("f8", eager=True)
        def _(event):
            self._post_and_invalidate(ToggleActivity())

        @kb.add("f6", eager=True)
        def _(event):
            self.thinking_panel.toggle_pin()
            self._app.invalidate()

        # ── Copy (quick) ──
        @kb.add("c")
        def _(event):
            if event.app.current_buffer is self.input_buffer:
                event.current_buffer.insert_text("c")
                return
            self._post_and_invalidate(CopyFocusedMessage())

        @kb.add("C")
        def _(event):
            if event.app.current_buffer is self.input_buffer:
                event.current_buffer.insert_text("C")
                return
            self._post_and_invalidate(CopyFocusedMessage(as_markdown=True))

        # ── Misc ──
        @kb.add("c-l", eager=True)
        def _(event):
            self.message_pane.clear()
            self.thinking_panel.clear()
            self._app.invalidate()

        @kb.add("escape")
        def _(event):
            s = self._state.screen
            if s != Screen.MAIN:
                self._post_and_invalidate(NavigateBack())
                return
            if self._state.interaction.mode == InteractionMode.COPY:
                self._post_and_invalidate(ToggleInteractionMode(target=InteractionMode.NORMAL))
                return
            self._post_and_invalidate(CancelRequested())

        @kb.add("c-v")
        def _(event):
            self.input_buffer.paste_from_clipboard(event.app.clipboard.get_data())

        @kb.add("escape", "escape")
        def _(event):
            self.input_buffer.reset()

        @kb.add("c-k")
        def _(event):
            self.input_buffer.reset()

        # ── Copy mode (Ctrl+F) ──
        @kb.add("f3", eager=True)
        def _enter_copy(event):
            if self._state.interaction.mode == InteractionMode.COPY:
                self._post_and_invalidate(ExitCopyMode())
                return
            total = len(self._msg_store)
            if total > 0:
                self._post_and_invalidate(EnterCopyMode(total_messages=total))

        _copy = Condition(lambda: self._state.interaction.mode == InteractionMode.COPY)

        @kb.add("up", filter=_copy)
        def _copy_up(event):
            total = len(self._msg_store)
            self._post_and_invalidate(MoveCopySelection(delta=-1, total=total))

        @kb.add("down", filter=_copy)
        def _copy_down(event):
            total = len(self._msg_store)
            self._post_and_invalidate(MoveCopySelection(delta=1, total=total))

        @kb.add("c", filter=_copy)
        def _copy_selected(event):
            idx = self._state.interaction.focus_idx
            msg = self._msg_store.get(idx)
            if msg:
                # Post copy effect directly
                self._post_and_invalidate(CopySelectedMessage())
                # Also do the actual clipboard copy now (side effect)
                try:
                    import pyperclip

                    pyperclip.copy(msg.text)
                except Exception:
                    import logging

                    logging.getLogger(__name__).debug("silent except", exc_info=True)
            self._post_and_invalidate(ExitCopyMode())

        # ── Vim mode ──
        _vim = Condition(lambda: self._state.interaction.mode == InteractionMode.VIM)

        @kb.add("j", filter=_vim)
        def _(event):
            self._post_and_invalidate(ScrollBy(-3))

        @kb.add("k", filter=_vim)
        def _(event):
            self._post_and_invalidate(ScrollBy(3))

        @kb.add("g", "g", filter=_vim)
        def _(event):
            self._post_and_invalidate(ScrollTo("top"))

        @kb.add("G", filter=_vim)
        def _(event):
            self._post_and_invalidate(ScrollTo("bottom"))

        return kb

    # ══════════════════════════════════════════════════════════════
    #  Input handler
    # ══════════════════════════════════════════════════════════════

    def _on_input_accept(self, buf: Buffer) -> bool:
        text = buf.text
        buf.reset()
        self._post_and_invalidate(SubmitInput(text))
        return True

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
            self._sync_terminal_size()
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

        return Application(
            layout=Layout(root, focused_element=self.input_win),
            key_bindings=self.kb,
            input=ptk_input,
            output=ptk_output,
            full_screen=True,
            mouse_support=False,
            enable_page_navigation_bindings=False,
        )

    # ══════════════════════════════════════════════════════════════
    #  Lifecycle
    # ══════════════════════════════════════════════════════════════

    def _restore_focus(self) -> None:
        """Force focus back to input buffer. Called after stream ends."""
        try:
            self._app.layout.focus(self.input_win)
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

    def _request_exit(self) -> None:
        self._closing = True
        self._running = False

    def run(self) -> None:
        """Start the application."""
        self._running = True
        self._scheduler.start()
        self._app.invalidate()  # force first render with welcome screen

        try:
            self._app.run()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception("V3App.run crashed: %s", e)
            sys.stderr.write(f"\n[CRUX TUI v3 crashed: {type(e).__name__}: {e}]\n")
            sys.stderr.flush()
        finally:
            self._running = False
            self._scheduler.stop()

    def shutdown(self) -> None:
        self._request_exit()
        self._scheduler.stop()
