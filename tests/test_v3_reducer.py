"""Smoke tests for the v3 reducer — pure function, no terminal needed."""

from ui.v3.events import (
    CancelRequested,
    ClearScreen,
    ResizeEvent,
    ScrollBy,
    StreamDone,
    StreamTextChunk,
    StreamThinkingChunk,
    StreamToolFinished,
    StreamToolStarted,
    SubmitInput,
    ToggleDashboard,
    ToggleFocusMode,
    ToggleInteractionMode,
)
from ui.v3.reducer import reduce_ui
from ui.v3.state import (
    InteractionMode,
    Screen,
    ScrollMode,
    StreamStatus,
    initial_state,
)


def test_initial_state_is_idle():
    state = initial_state()
    assert state.stream.status == StreamStatus.IDLE
    assert state.screen == Screen.MAIN
    assert state.interaction.mode == InteractionMode.NORMAL


def test_text_chunk_transitions_to_streaming():
    state = initial_state()
    state, _effects = reduce_ui(state, StreamTextChunk("hello"))
    assert state.stream.status == StreamStatus.STREAMING


def test_thinking_chunk_accumulates():
    state = initial_state()
    state, _ = reduce_ui(state, StreamThinkingChunk("analyzing..."))
    state, _ = reduce_ui(state, StreamThinkingChunk(" still thinking"))
    assert "analyzing... still thinking" in state.thinking.text
    assert state.thinking.visible is True


def test_stream_done_resets():
    state = initial_state()
    state, _ = reduce_ui(state, StreamTextChunk("hello"))
    state, _ = reduce_ui(state, StreamDone())
    assert state.stream.status == StreamStatus.IDLE  # reducer returns to IDLE on done


def test_tool_started_increments_seq():
    state = initial_state()
    state, _ = reduce_ui(state, StreamToolStarted("read_file"))
    assert state.stream.tool_seq == 1
    assert state.stream.tool_name == "read_file"


def test_scroll_up_goes_manual():
    state = initial_state()
    assert state.scroll.mode == ScrollMode.FOLLOW
    state, _ = reduce_ui(state, ScrollBy(-3))
    assert state.scroll.mode == ScrollMode.MANUAL
    assert state.scroll.offset == 3  # negative lines = up = positive offset


def test_scroll_to_bottom_goes_follow():
    state = initial_state()
    state, _ = reduce_ui(state, ScrollBy(-5))  # manual mode
    from ui.v3.events import ScrollTo

    state, _ = reduce_ui(state, ScrollTo("bottom"))
    assert state.scroll.mode == ScrollMode.FOLLOW


def test_cancel_during_stream_cancels():
    state = initial_state()
    state, _ = reduce_ui(state, StreamTextChunk("hello"))
    state, _effects = reduce_ui(state, CancelRequested())
    assert state.stream.status == StreamStatus.CANCELLING


def test_cancel_when_idle_exits():
    state = initial_state()
    state, effects = reduce_ui(state, CancelRequested())
    assert any(e.kind == "exit_app" for e in effects)


def test_cancel_on_overlay_closes_overlay():
    state = initial_state()
    state, _ = reduce_ui(state, ToggleDashboard())
    assert state.screen == Screen.DASHBOARD
    state, _effects = reduce_ui(state, CancelRequested())
    assert state.screen == Screen.MAIN


def test_submit_starts_stream():
    state = initial_state()
    state, effects = reduce_ui(state, SubmitInput("fix the bug"))
    assert state.stream.status == StreamStatus.THINKING
    assert any(e.kind == "run_model_stream" for e in effects)


def test_submit_command_does_not_start_stream():
    state = initial_state()
    state, effects = reduce_ui(state, SubmitInput("/theme blade"))
    assert state.stream.status == StreamStatus.IDLE
    assert any(e.kind == "execute_command" for e in effects)


def test_toggle_focus_mode():
    state = initial_state()
    assert not state.focus_mode
    state, _ = reduce_ui(state, ToggleFocusMode())
    assert state.focus_mode
    state, _ = reduce_ui(state, ToggleFocusMode())
    assert not state.focus_mode


def test_toggle_vim_mode():
    state = initial_state()
    state, _ = reduce_ui(state, ToggleInteractionMode())
    assert state.interaction.mode == InteractionMode.VIM
    state, _ = reduce_ui(state, ToggleInteractionMode())
    assert state.interaction.mode == InteractionMode.NORMAL


def test_resize_updates_terminal():
    state = initial_state(cols=80, rows=24)
    state, effects = reduce_ui(state, ResizeEvent(120, 40))
    assert state.terminal.cols == 120
    assert state.terminal.rows == 40
    assert any(e.kind == "recalculate_layout" for e in effects)


def test_clear_resets_thinking_and_activity():
    state = initial_state()
    state, _ = reduce_ui(state, StreamThinkingChunk("reasoning..."))
    assert state.thinking.text
    state, _ = reduce_ui(state, ClearScreen())
    assert state.thinking.text == ""
    assert not state.activity.items


def test_state_is_immutable():
    """Verify that we can't accidentally mutate state."""
    state = initial_state()
    try:
        state.stream.status = StreamStatus.STREAMING  # type: ignore
        raise AssertionError("Should have raised FrozenInstanceError")
    except Exception:
        pass  # expected


def test_full_stream_lifecycle():
    """Simulate a complete stream: text → thinking → tool → done."""
    state = initial_state()

    # User submits
    state, fx = reduce_ui(state, SubmitInput("fix bug"))
    assert state.stream.status == StreamStatus.THINKING
    assert any(e.kind == "run_model_stream" for e in fx)

    # Thinking arrives
    state, fx = reduce_ui(state, StreamThinkingChunk("hmm..."))
    assert state.thinking.text == "hmm..."
    assert any(e.kind == "stream_append_thinking" for e in fx)

    # Text arrives
    state, fx = reduce_ui(state, StreamTextChunk("The bug is in"))
    assert state.stream.status == StreamStatus.STREAMING
    assert any(e.kind == "stream_append_text" for e in fx)

    # Tool runs
    state, fx = reduce_ui(state, StreamToolStarted("read_file"))
    assert state.stream.tool_seq == 1
    assert state.stream.tool_name == "read_file"

    # Tool finishes
    state, fx = reduce_ui(state, StreamToolFinished("read_file", success=True))
    assert state.stream.tool_name == ""

    # More text
    state, fx = reduce_ui(state, StreamTextChunk(" line 42."))

    # Stream done
    state, fx = reduce_ui(state, StreamDone(elapsed=2.5, tool_count=1))
    assert state.stream.status == StreamStatus.IDLE  # reducer returns to IDLE on done
    assert any(e.kind == "finalize_stream" for e in fx)


def test_cancel_during_thinking_cancels_stream():
    """Cancel while model is thinking."""
    state = initial_state()
    state, _ = reduce_ui(state, SubmitInput("fix bug"))
    assert state.stream.status == StreamStatus.THINKING
    state, fx = reduce_ui(state, CancelRequested())
    assert state.stream.status == StreamStatus.CANCELLING
    assert any(e.kind == "cancel_model_stream" for e in fx)


def test_scroll_during_stream_increments_unseen():
    """When user scrolls up during streaming, unseen counter increments."""
    state = initial_state()
    state, _ = reduce_ui(state, StreamTextChunk("hello"))
    # User scrolls up
    state, _ = reduce_ui(state, ScrollBy(-5))
    assert state.scroll.mode == ScrollMode.MANUAL
    assert state.scroll.unseen == 0  # No new messages yet
    # New text arrives while user is scrolled up
    state, _ = reduce_ui(state, StreamTextChunk(" more text"))
    assert state.scroll.unseen == 1  # One new chunk unseen
