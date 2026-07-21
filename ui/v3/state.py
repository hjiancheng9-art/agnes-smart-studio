"""CRUX TUI v3 — frozen UI state.

Single source of truth for the entire UI. Only the reducer (reducer.py)
may produce new UiState instances. Views and external code read only.

Design:
  - All dataclasses are frozen → every state change produces a new object.
  - Use dataclasses.replace() for incremental updates.
  - Never mutate. Never hold references across reduce cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

# ── Sub-states ────────────────────────────────────────────────────


class StreamStatus(Enum):
    IDLE = auto()  # no active stream
    THINKING = auto()  # model is reasoning (before first text token)
    STREAMING = auto()  # model is producing text / tools
    DONE = auto()  # stream completed normally
    CANCELLING = auto()  # cancellation in flight
    ERROR = auto()  # stream failed


class ScrollMode(Enum):
    FOLLOW = auto()  # auto-scroll to latest message
    MANUAL = auto()  # user has scrolled up; don't auto-follow


class Screen(Enum):
    MAIN = auto()
    DASHBOARD = auto()
    INCIDENTS = auto()
    REMEDIATE = auto()
    REPLAY = auto()
    APPROVAL = auto()


class InteractionMode(Enum):
    NORMAL = auto()
    VIM = auto()
    COPY = auto()  # Ctrl+F: navigate messages for copy


@dataclass(frozen=True)
class StreamState:
    """What the model/stream is doing right now."""

    status: StreamStatus = StreamStatus.IDLE
    tool_name: str = ""  # current tool name (for activity log)
    tool_seq: int = 0  # how many tools run so far this turn
    first_token_at: float = 0.0  # monotonic timestamp of first token
    started_at: float = 0.0  # monotonic timestamp of stream start


@dataclass(frozen=True)
class InteractionState:
    """How the user is currently interacting with the UI."""

    mode: InteractionMode = InteractionMode.NORMAL
    focus_idx: int = -1  # which message is focused (-1 = latest)


@dataclass(frozen=True)
class ScrollState:
    """Chat scroll position."""

    mode: ScrollMode = ScrollMode.FOLLOW
    offset: int = 0  # lines scrolled from bottom
    unseen: int = 0  # how many new lines arrived while MANUAL


@dataclass(frozen=True)
class SessionView:
    """Read-only snapshot of current session metadata."""

    model: str = ""
    cwd: str = ""
    git_branch: str = ""
    context_pct: float = 0.0
    latency: float | None = None  # first-token latency in seconds
    method_level: str = ""  # A / B / C / D


@dataclass(frozen=True)
class TerminalState:
    """Current terminal dimensions."""

    cols: int = 80
    rows: int = 24


@dataclass(frozen=True)
class ActivityState:
    """Tool execution activity log shown between chat and input."""

    items: tuple = ()  # tuple of (icon, style_class, message)
    expanded: bool = False  # user pressed F8 to expand


@dataclass(frozen=True)
class ThinkingState:
    """Model reasoning / chain-of-thought panel."""

    text: str = ""  # accumulated thinking text
    visible: bool = False  # has any thinking content
    pinned: bool = False  # user pinned via Ctrl+T


@dataclass(frozen=True)
class InspectorState:
    """Right-side inspector panel data."""

    files: tuple = ()  # tuple of InspectorFile
    agents: tuple = ()  # tuple of InspectorAgent


@dataclass(frozen=True)
class PaletteState:
    """Command palette overlay state."""

    open: bool = False
    query: str = ""
    selected: int = 0


# ── Root state ────────────────────────────────────────────────────


@dataclass(frozen=True)
class UiState:
    """The immutable root of all UI truth.

    Every 16ms (or on event), the main loop:
        events = drain_queue()
        for e in events: state, effects = reduce_ui(state, e)
        execute(effects)
        render(state)
    """

    stream: StreamState = field(default_factory=StreamState)
    interaction: InteractionState = field(default_factory=InteractionState)
    scroll: ScrollState = field(default_factory=ScrollState)
    session: SessionView = field(default_factory=SessionView)
    terminal: TerminalState = field(default_factory=TerminalState)
    activity: ActivityState = field(default_factory=ActivityState)
    thinking: ThinkingState = field(default_factory=ThinkingState)
    inspector: InspectorState = field(default_factory=InspectorState)
    palette: PaletteState = field(default_factory=PaletteState)

    screen: Screen = Screen.MAIN
    focus_mode: bool = False  # F12: hide chrome, show only messages
    dashboard_mode: bool = False  # show problem-oriented dashboard


# ── Factory ───────────────────────────────────────────────────────


def initial_state(cols: int = 80, rows: int = 24) -> UiState:
    """Create the initial UI state with terminal dimensions."""
    return UiState(terminal=TerminalState(cols=max(1, cols), rows=max(1, rows)))
