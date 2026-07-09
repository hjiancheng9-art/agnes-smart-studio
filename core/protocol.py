"""
CRUX Dual-Mode Protocol — Shared Backend for TUI + GUI
========================================================
Per 3-platform debate conclusion (R9):
    TUI = developer cockpit (terminal)
    GUI = creative production cockpit (browser/desktop)
    Both share the same backend protocol, task state, and workflow data.

Architecture:
    ┌─────────────────────────────────────────────┐
    │              CRUX Engine                     │
    │  (session, model, tools, agents, comfyui)    │
    └─────────────────┬───────────────────────────┘
                      │
              ┌───────┴───────┐
              │  Protocol Bus  │  ← core/protocol.py
              │  (JSON events) │
              └───┬───────┬───┘
                  │       │
          ┌───────┴┐  ┌───┴───────┐
          │  TUI   │  │  GUI      │
          │ (term) │  │ (web/app) │
          └────────┘  └───────────┘

Protocol: JSON-over-STDIO (TUI) + WebSocket (GUI)
Events:  All state changes flow through a unified event bus
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum

# ── Event Types ────────────────────────────────────────────


class EventType(Enum):
    # Session events
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    MODEL_CHANGED = "model.changed"

    # Message events
    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_STREAMING = "message.streaming"  # token-by-token

    # Tool events
    TOOL_CALLED = "tool.called"
    TOOL_RESULT = "tool.result"
    TOOL_ERROR = "tool.error"

    # Agent events
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # ComfyUI events
    COMFYUI_QUEUED = "comfyui.queued"
    COMFYUI_PROGRESS = "comfyui.progress"  # {node, progress, total}
    COMFYUI_DONE = "comfyui.done"
    COMFYUI_ERROR = "comfyui.error"

    # System events
    SYSTEM_METRICS = "system.metrics"  # CPU/memory/disk
    DASHBOARD_UPDATE = "dashboard.update"  # full state refresh
    ERROR_OCCURRED = "error.occurred"

    # UI events (for persistence/sync)
    UI_STATE_CHANGED = "ui.state.changed"  # theme, layout, panels


@dataclass
class Event:
    """A single protocol event."""

    type: str  # EventType as string
    data: dict  # Event payload
    timestamp: float = field(default_factory=time.monotonic)
    source: str = "engine"  # 'engine', 'tui', 'gui'

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> Event:
        data = json.loads(raw)
        return cls(**data)


# ── State Snapshot ────────────────────────────────────────


@dataclass
class SessionState:
    """Immutable snapshot of current CRUX session state."""

    model: str = ""
    thinking: bool = False
    streaming: bool = False
    context_pct: float = 0.0
    context_used: int = 0
    context_total: int = 128000
    messages: int = 0
    active_agents: int = 0

    # Tool chain
    current_tool: str = ""
    tool_status: str = "idle"
    tool_error: str = ""

    # ComfyUI
    comfyui_online: bool = False
    comfyui_queue: int = 0
    comfyui_progress: float = 0.0

    # System (optional, only when panel visible)
    cpu_pct: float = 0.0
    memory_pct: float = 0.0
    disk_pct: float = 0.0
    processes: int = 0

    # UI state (for GUI to restore)
    theme: str = "normal"
    dashboard_visible: bool = False
    focus_mode: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# ── Event Bus ──────────────────────────────────────────────


class EventBus:
    """
    Thread-safe pub/sub event bus.

    Both TUI and GUI connect to this bus.
    TUI: reads from in-process queue, renders in terminal
    GUI: reads from WebSocket bridge, renders in browser

    Usage:
        bus = EventBus()
        bus.subscribe("message.*", my_handler)
        bus.publish(Event(EventType.MESSAGE_RECEIVED, {...}))
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: list[tuple[str, Callable]] = []
        self._history: list[Event] = []
        self._history_max = 500
        self._latest_state: SessionState | None = None

    def publish(self, event: Event):
        """Publish an event to all matching subscribers."""
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_max:
                self._history = self._history[-self._history_max :]

            # Update latest state if session state changed
            if event.type in (
                EventType.MESSAGE_SENT.value,
                EventType.MESSAGE_RECEIVED.value,
                EventType.MODEL_CHANGED.value,
                EventType.DASHBOARD_UPDATE.value,
                EventType.SYSTEM_METRICS.value,
            ):
                self._latest_state = self._build_state()

            for pattern, callback in self._subscribers:
                if self._matches(pattern, event.type):
                    with contextlib.suppress(Exception):
                        callback(event)

    def subscribe(self, pattern: str, callback: Callable):
        """
        Subscribe to events matching a pattern.
        Patterns: 'message.*', 'tool.*', '*', 'error.occurred'
        """
        with self._lock:
            self._subscribers.append((pattern, callback))

    def unsubscribe(self, pattern: str, callback: Callable):
        with self._lock:
            self._subscribers = [(p, c) for p, c in self._subscribers if not (p == pattern and c == callback)]

    def get_history(self, since: float = 0.0, limit: int = 50) -> list[Event]:
        """Get events since a timestamp."""
        with self._lock:
            return [e for e in self._history[-limit:] if e.timestamp > since]

    @property
    def latest_state(self) -> SessionState | None:
        return self._latest_state

    def _build_state(self) -> SessionState:
        """Build a SessionState from recent events."""
        # This is populated by the engine calling update_state()
        if self._latest_state:
            return self._latest_state
        return SessionState()

    def update_state(self, **kwargs):
        """Update the cached session state."""
        with self._lock:
            if self._latest_state is None:
                self._latest_state = SessionState()
            for k, v in kwargs.items():
                if hasattr(self._latest_state, k):
                    setattr(self._latest_state, k, v)

    def get_replay(self, event_types: list[str] | None = None) -> list[dict]:
        """Get serializable event history for GUI replay/restore."""
        with self._lock:
            events = self._history
            if event_types:
                events = [e for e in events if e.type in event_types]
            return [asdict(e) for e in events]

    @staticmethod
    def _matches(pattern: str, event_type: str) -> bool:
        """Simple wildcard matching: 'message.*' matches 'message.sent'."""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            return event_type.startswith(pattern[:-1])
        return pattern == event_type


# ── Global singleton ─────────────────────────────────────

_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> EventBus:
    """Get or create the global event bus singleton."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus


# ── Convenience helpers ──────────────────────────────────


def emit(event_type: EventType, data: dict, source: str = "engine"):
    """Quick-publish an event."""
    bus = get_bus()
    bus.publish(Event(type=event_type.value, data=data, source=source))


def emit_state(**kwargs):
    """Update the global state snapshot and emit a dashboard update event."""
    bus = get_bus()
    bus.update_state(**kwargs)
    if bus.latest_state:
        emit(EventType.DASHBOARD_UPDATE, bus.latest_state.to_dict())


def update_and_emit(event_type: EventType, data: dict, state_updates: dict = None):
    """Update state and emit event atomically."""
    bus = get_bus()
    if state_updates:
        bus.update_state(**state_updates)
    bus.publish(Event(type=event_type.value, data=data))
