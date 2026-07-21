"""CRUX TUI v3 — pure reducer.

reduce_ui(state, event) → (new_state, effects)

This is the ONLY place where UiState is modified. Every state transition
is explicit and traceable. No other code may mutate state — not views,
not key handlers, not background threads.

Background threads call post_event() to enqueue events into the main
loop; the main loop drains the queue and calls reduce_ui() before each
render frame.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from .effects import Effect
from .events import (
    CancelRequested,
    ClearScreen,
    CopyFocusedMessage,
    CopySelectedMessage,
    EnterCopyMode,
    ExecuteCommand,
    ExitCopyMode,
    ExitRequested,
    ImageSubmitted,
    KeyPressed,
    MoveCopySelection,
    NavigateBack,
    NavigateTo,
    OpenMessageDetail,
    PaletteFilter,
    PaletteMoveDown,
    PaletteMoveUp,
    PaletteSelect,
    ResizeEvent,
    ScrollBy,
    ScrollTo,
    SessionUpdate,
    StreamCancelled,
    StreamDone,
    StreamError,
    StreamInfo,
    StreamTextChunk,
    StreamThinkingChunk,
    StreamToolError,
    StreamToolFinished,
    StreamToolStarted,
    SubmitInput,
    SystemNotification,
    TickEvent,
    ToggleActivity,
    ToggleDashboard,
    ToggleFocusMode,
    ToggleInteractionMode,
    TogglePalette,
    ToggleThinking,
)
from .state import (
    ActivityState,
    InteractionMode,
    Screen,
    ScrollMode,
    ScrollState,
    StreamState,
    StreamStatus,
    TerminalState,
    ThinkingState,
    UiState,
)


def reduce_ui(state: UiState, event: Any) -> tuple[UiState, list[Effect]]:
    """The single entry point for all UI state transitions.

    Returns (new_state, effects) where effects is a list of side-effects
    to execute after state is updated.
    """
    effects: list[Effect] = []

    # ── Stream events ─────────────────────────────────────────
    if isinstance(event, StreamTextChunk):
        state = _on_text(state)
        effects.append(Effect("stream_append_text", {"text": event.text}))

    elif isinstance(event, StreamThinkingChunk):
        state = _on_thinking(state, event.text)
        effects.append(Effect("stream_append_thinking", {"text": event.text}))

    elif isinstance(event, StreamToolStarted):
        state = _on_tool_start(state, event.tool_name, event.message)
        state = _append_activity(state, "●", "class:activity-running", f"#{state.stream.tool_seq} {event.tool_name}")
        effects.append(Effect.render_activity())

    elif isinstance(event, StreamToolFinished):
        state = _on_tool_finish(state, event.tool_name, event.success)
        effects.append(Effect.render_activity())

    elif isinstance(event, StreamToolError):
        state = _on_tool_finish(state, event.tool_name, False)
        effects.append(Effect.render_activity())

    elif isinstance(event, StreamInfo):
        effects.append(Effect.render_activity())

    elif isinstance(event, StreamError):
        state = replace(state, stream=StreamState(status=StreamStatus.ERROR))
        effects.append(Effect.render_chat())

    elif isinstance(event, StreamDone):
        state = replace(
            state,
            stream=StreamState(status=StreamStatus.DONE, tool_seq=state.stream.tool_seq),
            scroll=ScrollState(mode=ScrollMode.FOLLOW),
        )
        effects.append(Effect.finalize_stream())
        effects.append(Effect("scroll_sync"))

    elif isinstance(event, StreamCancelled):
        state = replace(state, stream=StreamState(status=StreamStatus.IDLE))
        effects.append(Effect.finalize_stream())

    # ── Keyboard / user actions ───────────────────────────────
    elif isinstance(event, CancelRequested):
        state, fx = _on_cancel(state)
        effects.extend(fx)

    elif isinstance(event, SubmitInput):
        state, fx = _on_submit(state, event.text)
        effects.extend(fx)

    elif isinstance(event, ToggleFocusMode):
        state = replace(state, focus_mode=not state.focus_mode)

    elif isinstance(event, ToggleInteractionMode):
        new_mode = event.target
        if new_mode is None:
            # toggle NORMAL ↔ VIM, skip COPY mode
            current = state.interaction.mode
            new_mode = InteractionMode.VIM if current == InteractionMode.NORMAL else InteractionMode.NORMAL
        state = replace(state, interaction=replace(state.interaction, mode=new_mode))

    elif isinstance(event, ToggleActivity):
        state = replace(state, activity=replace(state.activity, expanded=not state.activity.expanded))

    elif isinstance(event, ToggleThinking):
        state = replace(state, thinking=replace(state.thinking, pinned=not state.thinking.pinned))

    elif isinstance(event, ToggleDashboard):
        new_screen = Screen.MAIN if state.screen == Screen.DASHBOARD else Screen.DASHBOARD
        state = replace(state, screen=new_screen)

    elif isinstance(event, ScrollBy):
        state = _on_scroll_by(state, event.lines)
        effects.append(Effect("scroll_sync"))

    elif isinstance(event, ScrollTo):
        state = _on_scroll_to(state, event.position)
        effects.append(Effect("scroll_sync"))

    elif isinstance(event, CopyFocusedMessage):
        effects.append(Effect.copy_to_clipboard("", as_markdown=event.as_markdown))

    elif isinstance(event, OpenMessageDetail):
        pass  # handled by view layer reading interaction.focus_idx

    elif isinstance(event, ClearScreen):
        state = replace(state, activity=ActivityState(), thinking=ThinkingState())
        effects.append(Effect("clear_messages"))

    elif isinstance(event, NavigateTo):
        if event.screen in Screen:
            state = replace(state, screen=event.screen)

    elif isinstance(event, NavigateBack):
        state = replace(state, screen=Screen.MAIN)

    elif isinstance(event, ExecuteCommand):
        effects.append(Effect.execute_command(event.command))

    elif isinstance(event, ExitRequested):
        effects.append(Effect.exit_app())

    elif isinstance(event, ImageSubmitted):
        effects.append(Effect.analyze_image(event.path))

    # ── System events ─────────────────────────────────────────
    elif isinstance(event, ResizeEvent):
        state = replace(
            state,
            terminal=TerminalState(cols=max(1, event.cols), rows=max(1, event.rows)),
        )
        effects.append(Effect.recalculate_layout())
        effects.append(Effect("scroll_sync"))  # re-clamp scroll after resize

    elif isinstance(event, SessionUpdate):
        state = _on_session_update(state, event)

    elif isinstance(event, SystemNotification):
        effects.append(Effect.render_status())

    elif isinstance(event, TickEvent):
        pass  # views use time.monotonic(), no state change needed

    elif isinstance(event, KeyPressed):
        # KeyPressed is a fallback; most keys map to specific events above
        pass

    # ── Palette events ──
    elif isinstance(event, TogglePalette):
        p = state.palette
        if not p.open:
            # Save current interaction mode, switch to palette-modal
            state = replace(state, palette=replace(p, open=True, query="", selected=0))
        else:
            state = replace(state, palette=replace(p, open=False, query="", selected=0))
    elif isinstance(event, PaletteFilter):
        query = event.text
        from .views.palette import _clamp_selected

        state = replace(
            state,
            palette=replace(
                state.palette,
                query=query,
                selected=_clamp_selected(query, state.palette.selected),
            ),
        )
    elif isinstance(event, PaletteMoveUp):
        p = state.palette
        state = replace(state, palette=replace(p, selected=max(0, p.selected - 1)))
    elif isinstance(event, PaletteMoveDown):
        from .views.palette import match_commands

        p = state.palette
        max_idx = max(0, len(match_commands(p.query)) - 1)
        state = replace(state, palette=replace(p, selected=min(max_idx, p.selected + 1)))
    elif isinstance(event, PaletteSelect):
        from .views.palette import match_commands

        p = state.palette
        matches = match_commands(p.query)
        if 0 <= p.selected < len(matches):
            cmd, _ = matches[p.selected]
            effects.append(Effect.execute_command(cmd))
        state = replace(state, palette=replace(p, open=False, query="", selected=0))

    # ── Copy mode events ──
    elif isinstance(event, EnterCopyMode):
        i = state.interaction
        state = replace(state, interaction=replace(i, mode=InteractionMode.COPY, focus_idx=event.total_messages - 1))
    elif isinstance(event, ExitCopyMode):
        i = state.interaction
        state = replace(state, interaction=replace(i, mode=InteractionMode.NORMAL))
    elif isinstance(event, MoveCopySelection):
        i = state.interaction
        total = event.total if event.total > 0 else 9999
        new_idx = max(0, min(total - 1, i.focus_idx + event.delta))
        state = replace(state, interaction=replace(i, focus_idx=new_idx))
    elif isinstance(event, CopySelectedMessage):
        idx = state.interaction.focus_idx
        effects.append(Effect.copy_to_clipboard(f"message:{idx}"))

    return state, effects


# ── Private reducers ──────────────────────────────────────────────


def _on_text(state: UiState) -> UiState:
    """A text chunk arrived → transition to STREAMING if not already."""
    now = time.monotonic()
    s = state.stream
    if s.status == StreamStatus.IDLE or s.status == StreamStatus.THINKING:
        # First text token — record latency
        first_token_at = s.started_at if s.started_at else now
        started_at = now if not s.started_at else s.started_at
        return replace(
            state,
            stream=StreamState(
                status=StreamStatus.STREAMING,
                tool_name=s.tool_name,
                tool_seq=s.tool_seq,
                started_at=started_at,
                first_token_at=first_token_at,
            ),
            # auto-follow if in FOLLOW mode
            scroll=_maybe_follow(state.scroll),
        )
    return replace(
        state,
        stream=replace(s, status=StreamStatus.STREAMING),
        scroll=_maybe_follow(state.scroll),
    )


def _on_thinking(state: UiState, text: str) -> UiState:
    """Accumulate thinking text, stay in THINKING status."""
    s = state.stream
    now = time.monotonic()
    started_at = s.started_at if s.started_at else now
    return replace(
        state,
        stream=replace(s, status=StreamStatus.THINKING, started_at=started_at),
        thinking=replace(
            state.thinking,
            text=state.thinking.text + text,
            visible=True,
        ),
    )


def _on_tool_start(state: UiState, tool_name: str, message: str = "") -> UiState:
    """A tool started executing. Track in inspector panel."""
    s = state.stream
    state = replace(
        state,
        stream=replace(s, tool_name=tool_name, tool_seq=s.tool_seq + 1, status=StreamStatus.STREAMING),
        activity=replace(state.activity),
    )
    _file_tools = {
        "read_file",
        "write_file",
        "edit_file",
        "patch_file",
        "search_files",
        "glob_files",
        "run_test",
        "run_bash",
        "agent_swarm",
        "multi_agent",
        "code_review",
    }
    if tool_name in _file_tools:
        from .views.inspector import InspectorFile

        # Use tool name as the entry — shows what CRUX is doing right now
        label = {
            "read_file": "📖 reading",
            "write_file": "✏️ writing",
            "edit_file": "✏️ editing",
            "patch_file": "🔧 patching",
            "search_files": "🔍 searching",
            "glob_files": "🔍 finding",
            "run_test": "🧪 testing",
            "run_bash": "⚡ running",
            "agent_swarm": "🤖 swarming",
            "multi_agent": "🤖 multi-agent",
            "code_review": "👀 reviewing",
        }.get(tool_name, f"🔧 {tool_name}")
        files = list(state.inspector.files)
        path = f"{label} #{state.stream.tool_seq}"
        existing = {f.path for f in files}
        if path not in existing:
            files.append(InspectorFile(path=path, status="running"))
        state = replace(state, inspector=replace(state.inspector, files=tuple(files[-6:])))
    return state


def _append_activity(state: UiState, icon: str, style: str, msg: str) -> UiState:
    """Pure function: append an item to the activity log tuple."""
    old = state.activity
    items = [*list(old.items), (icon, style, msg)]
    if len(items) > 500:
        items = items[-500:]
    return replace(state, activity=old.__class__(items=tuple(items), expanded=old.expanded))


def _on_tool_finish(state: UiState, tool_name: str, success: bool) -> UiState:
    """A tool finished (successfully or with error)."""
    return replace(
        state,
        stream=replace(state.stream, tool_name=""),
    )


def _on_cancel(state: UiState) -> tuple[UiState, list[Effect]]:
    """Ctrl+C: context-sensitive cancel."""
    fx: list[Effect] = []
    s = state.stream

    if s.status in (StreamStatus.THINKING, StreamStatus.STREAMING):
        # Cancel active stream
        state = replace(state, stream=StreamState(status=StreamStatus.CANCELLING))
        fx.append(Effect.cancel_stream())
    elif state.screen != Screen.MAIN:
        # Close overlay
        state = replace(state, screen=Screen.MAIN)
    elif state.focus_mode:
        state = replace(state, focus_mode=False)
    elif state.interaction.mode == InteractionMode.COPY:
        state = replace(state, interaction=replace(state.interaction, mode=InteractionMode.NORMAL))
    else:
        # Idle → exit
        fx.append(Effect.exit_app())

    return state, fx


def _on_submit(state: UiState, text: str) -> tuple[UiState, list[Effect]]:
    """User submitted text from the input buffer."""
    fx: list[Effect] = []

    if not text.strip():
        return state, fx

    if text.startswith("/"):
        fx.append(Effect.execute_command(text))
        return state, fx

    if state.stream.status in (StreamStatus.THINKING, StreamStatus.STREAMING):
        # Queue as priority message while streaming
        fx.append(Effect.execute_command(text))  # routed via control plane
        return state, fx

    # Normal submit — start a new stream
    state = replace(
        state,
        stream=StreamState(status=StreamStatus.THINKING, started_at=time.monotonic()),
        thinking=ThinkingState(),
        scroll=ScrollState(mode=ScrollMode.FOLLOW),
    )
    fx.append(Effect.run_stream(text))
    return state, fx


def _on_scroll_by(state: UiState, lines: int) -> UiState:
    """Scroll chat by N lines (negative = scroll up / back in time).

    Convention:
      offset = how many lines ABOVE the visible bottom (always >= 0).
      offset 0 = at the bottom = FOLLOW mode.
      lines < 0 = scroll up (increase offset).
      lines > 0 = scroll down (decrease offset).
    """
    sc = state.scroll
    new_offset = max(0, sc.offset - lines)  # minus because positive lines=scroll down
    if new_offset <= 0:
        return replace(state, scroll=ScrollState(mode=ScrollMode.FOLLOW))
    return replace(
        state,
        scroll=ScrollState(mode=ScrollMode.MANUAL, offset=new_offset, unseen=sc.unseen),
    )


def _on_scroll_to(state: UiState, position: str) -> UiState:
    """Jump to top/bottom/page."""
    if position == "bottom":
        return replace(state, scroll=ScrollState(mode=ScrollMode.FOLLOW))
    elif position == "top":
        return replace(state, scroll=ScrollState(mode=ScrollMode.MANUAL, offset=9999))
    # page_up/page_down are handled by ScrollBy in the keymap
    return state


def _on_session_update(state: UiState, event: SessionUpdate) -> UiState:
    """Apply metadata updates from the session."""
    updates: dict[str, Any] = {}
    if event.model:
        updates["model"] = event.model
    if event.cwd:
        updates["cwd"] = event.cwd
    if event.git_branch:
        updates["git_branch"] = event.git_branch
    if event.context_pct:
        updates["context_pct"] = event.context_pct
    if event.latency is not None:
        updates["latency"] = event.latency
    if event.method_level:
        updates["method_level"] = event.method_level
    if not updates:
        return state

    current = state.session
    merged = replace(current, **{k: v for k, v in updates.items() if v})
    return replace(state, session=merged)


def _maybe_follow(sc: ScrollState) -> ScrollState:
    """If in FOLLOW mode, stay there. Otherwise increment unseen."""
    if sc.mode == ScrollMode.FOLLOW:
        return sc
    return replace(sc, unseen=sc.unseen + 1)
