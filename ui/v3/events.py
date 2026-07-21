"""CRUX TUI v3 — UI events.

Every state change begins as an event. Events are produced by:
  - Keyboard bindings (key presses)
  - Runtime bridge (stream chunks, system notifications)
  - Scheduler (ticks, resize)
  - Internal UI actions (mode toggles, navigation)

Events are consumed by reducer.reduce_ui() which produces (new_state, effects).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import InteractionMode, Screen

# ── Keyboard ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class KeyPressed:
    """A key was pressed, already resolved by the keymap router."""

    action: str  # e.g. "submit", "cancel", "scroll_up", "toggle_focus"


# ── Stream events (from runtime_bridge) ───────────────────────────


@dataclass(frozen=True)
class StreamTextChunk:
    """Model produced a text token."""

    text: str


@dataclass(frozen=True)
class StreamThinkingChunk:
    """Model produced a reasoning/thinking token."""

    text: str


@dataclass(frozen=True)
class StreamToolStarted:
    """A tool call began executing."""

    tool_name: str
    message: str = ""


@dataclass(frozen=True)
class StreamToolFinished:
    """A tool call completed."""

    tool_name: str
    success: bool = True
    message: str = ""


@dataclass(frozen=True)
class StreamToolError:
    """A tool call failed."""

    tool_name: str
    error: str


@dataclass(frozen=True)
class StreamInfo:
    """Informational message from the stream (provider switch, etc.)."""

    message: str


@dataclass(frozen=True)
class StreamError:
    """Stream-level error (connection, auth, timeout)."""

    error_type: str  # ConnectionError, TimeoutError, etc.
    message: str
    hint: str = ""


@dataclass(frozen=True)
class StreamDone:
    """Stream completed normally."""

    elapsed: float = 0.0
    tool_count: int = 0


@dataclass(frozen=True)
class StreamCancelled:
    """Stream was cancelled by user."""

    reason: str = ""


# ── System events ─────────────────────────────────────────────────


@dataclass(frozen=True)
class SystemNotification:
    """Provider fallback, connection issues, watchdog alerts."""

    level: str  # "info" | "warn" | "error"
    message: str


@dataclass(frozen=True)
class ResizeEvent:
    """Terminal was resized."""

    cols: int
    rows: int


@dataclass(frozen=True)
class TickEvent:
    """Periodic refresh tick (~10 fps when animating, ~1 fps idle)."""

    pass


# ── User actions ──────────────────────────────────────────────────


@dataclass(frozen=True)
class SubmitInput:
    """User pressed Enter with text in the input buffer."""

    text: str


@dataclass(frozen=True)
class CancelRequested:
    """User pressed Ctrl+C or equivalent."""

    pass


@dataclass(frozen=True)
class ToggleFocusMode:
    """F12: toggle full-screen message focus."""

    pass


@dataclass(frozen=True)
class ToggleInteractionMode:
    """F7: cycle NORMAL → VIM → NORMAL."""

    target: InteractionMode | None = None  # None = toggle


@dataclass(frozen=True)
class ToggleActivity:
    """F8: expand/collapse the activity log."""

    pass


@dataclass(frozen=True)
class ToggleThinking:
    """Ctrl+T: pin/unpin the thinking panel."""

    pass


@dataclass(frozen=True)
class ToggleDashboard:
    """Toggle problem-oriented dashboard overlay."""

    pass


@dataclass(frozen=True)
class ScrollBy:
    """Scroll the chat view by N lines (negative = up)."""

    lines: int


@dataclass(frozen=True)
class ScrollTo:
    """Jump to a specific scroll position."""

    position: str  # "top" | "bottom" | "page_up" | "page_down"


@dataclass(frozen=True)
class CopyFocusedMessage:
    """Copy the currently focused message."""

    as_markdown: bool = False


@dataclass(frozen=True)
class OpenMessageDetail:
    """Open message detail overlay."""

    pass


@dataclass(frozen=True)
class ClearScreen:
    """Ctrl+L: clear chat and activity."""

    pass


@dataclass(frozen=True)
class NavigateTo:
    """Switch to a different screen / overlay."""

    screen: Screen


@dataclass(frozen=True)
class NavigateBack:
    """Pop the current screen / overlay."""

    pass


@dataclass(frozen=True)
class ExitRequested:
    """User requested exit (Ctrl+Q or /quit)."""

    pass


@dataclass(frozen=True)
class ExecuteCommand:
    """A slash command was entered."""

    command: str  # e.g. "/theme blade", "/dashboard"


@dataclass(frozen=True)
class ImageSubmitted:
    """User pasted/dropped an image."""

    path: str


@dataclass(frozen=True)
class SessionUpdate:
    """Metadata refresh: model changed, git branch changed, etc."""

    model: str = ""
    cwd: str = ""
    git_branch: str = ""
    context_pct: float = 0.0
    latency: float | None = None
    method_level: str = ""


@dataclass(frozen=True)
class TogglePalette:
    """Open/close the command palette (Ctrl+P)."""

    pass


@dataclass(frozen=True)
class PaletteFilter:
    """Update the palette search query."""

    text: str


@dataclass(frozen=True)
class PaletteSelect:
    """Select the highlighted palette item."""

    pass


@dataclass(frozen=True)
class PaletteMoveUp:
    """Move palette selection up."""

    pass


@dataclass(frozen=True)
class PaletteMoveDown:
    """Move palette selection down."""

    pass


@dataclass(frozen=True)
class EnterCopyMode:
    """Enter copy mode (Ctrl+F)."""

    total_messages: int = 0


@dataclass(frozen=True)
class ExitCopyMode:
    """Exit copy mode."""

    pass


@dataclass(frozen=True)
class MoveCopySelection:
    """Move copy selection up (-1) or down (+1)."""

    delta: int
    total: int = 9999  # total message count for clamping


@dataclass(frozen=True)
class CopySelectedMessage:
    """Copy currently selected message to clipboard."""

    pass


@dataclass
class ActivityLogged:
    """A UI activity item was logged (tool start, copy, command, etc.)."""

    icon: str
    style: str
    msg: str


# ── Unified event type ────────────────────────────────────────────

# All events that the reducer handles.  Using a flat union of dataclass
# types avoids inheritance hierarchies while keeping dispatch simple.
UiEvent = (
    KeyPressed
    | StreamTextChunk
    | StreamThinkingChunk
    | StreamToolStarted
    | StreamToolFinished
    | StreamToolError
    | StreamInfo
    | StreamError
    | StreamDone
    | StreamCancelled
    | SystemNotification
    | ResizeEvent
    | TickEvent
    | SubmitInput
    | CancelRequested
    | ToggleFocusMode
    | ToggleInteractionMode
    | ToggleActivity
    | ToggleThinking
    | ToggleDashboard
    | ScrollBy
    | ScrollTo
    | CopyFocusedMessage
    | OpenMessageDetail
    | ClearScreen
    | NavigateTo
    | NavigateBack
    | ExitRequested
    | ExecuteCommand
    | ImageSubmitted
    | SessionUpdate
    | TogglePalette
    | PaletteFilter
    | PaletteSelect
    | PaletteMoveUp
    | PaletteMoveDown
    | EnterCopyMode
    | ExitCopyMode
    | MoveCopySelection
    | CopySelectedMessage
    | ActivityLogged
)
