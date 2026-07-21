"""CRUX TUI v3 — event-driven UI core.

Architecture:
  events (dataclasses) → reducer (pure function) → (state, effects)
                                                     │
                                                     ▼
                                               app.py executes effects,
                                               views read state for rendering

The key invariant: ONLY reducer.py touches UiState. Background threads,
keyboard handlers, and views never mutate state — they produce events.
"""

from .effects import Effect
from .events import (
    CancelRequested,
    ClearScreen,
    ExitRequested,
    KeyPressed,
    NavigateTo,
    ResizeEvent,
    ScrollBy,
    ScrollTo,
    SessionUpdate,
    StreamDone,
    StreamTextChunk,
    StreamThinkingChunk,
    StreamToolFinished,
    StreamToolStarted,
    SubmitInput,
    ToggleActivity,
    ToggleDashboard,
    ToggleFocusMode,
    ToggleInteractionMode,
    ToggleThinking,
    UiEvent,
)
from .reducer import reduce_ui
from .state import UiState, initial_state

__all__ = [
    "CancelRequested",
    "ClearScreen",
    "Effect",
    "ExitRequested",
    "KeyPressed",
    "NavigateTo",
    "ResizeEvent",
    "ScrollBy",
    "ScrollTo",
    "SessionUpdate",
    "StreamDone",
    "StreamTextChunk",
    "StreamThinkingChunk",
    "StreamToolFinished",
    "StreamToolStarted",
    # re-export common event types for convenience
    "SubmitInput",
    "ToggleActivity",
    "ToggleDashboard",
    "ToggleFocusMode",
    "ToggleInteractionMode",
    "ToggleThinking",
    "UiEvent",
    "UiState",
    "initial_state",
    "reduce_ui",
]
