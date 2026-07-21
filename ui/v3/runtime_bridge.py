"""CRUX TUI v3 — runtime bridge.

Converts business-layer events (send_stream yields, control plane events,
session metadata) into UiEvent instances and posts them to the UI event
queue.

This is the ONLY place where backend threads interact with the UI.
All backend code calls:
    post_event(queue, some_ui_event)
or uses the converter helpers below.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

# ── Global event queue + app reference ─────────────────────────────
# Created by app.py, shared with bridge functions and worker threads.
from .events import (
    ImageSubmitted,
    ResizeEvent,
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
    SystemNotification,
    UiEvent,
)

if TYPE_CHECKING:
    from queue import SimpleQueue

    from prompt_toolkit.application import Application as PTKApplication

_event_queue: SimpleQueue[UiEvent] | None = None
_app_ref: PTKApplication | None = None


def set_event_queue(q: SimpleQueue[UiEvent]) -> None:
    """Called once by app.py to register the global queue."""
    global _event_queue
    _event_queue = q


def set_app_ref(app: PTKApplication) -> None:
    """Called once by app.py so post_event can trigger invalidate."""
    global _app_ref
    _app_ref = app


def post_event(event: UiEvent) -> None:
    """Post a UI event from ANY thread. Thread-safe.

    ONLY puts on queue. Does NOT trigger drain or invalidate.
    Worker threads call _trigger_drain() separately to schedule processing.
    """
    q = _event_queue
    if q is not None:
        q.put(event)


# ── Drain trigger (for worker threads) ────────────────────────────

_drain_fn: Any = None


def set_drain_fn(fn: Any) -> None:
    global _drain_fn
    _drain_fn = fn


def trigger_drain() -> None:
    """Schedule drain + invalidate on main thread. Safe from any thread."""
    app = _app_ref
    drain = _drain_fn
    if app is not None and drain is not None:
        try:
            app.call_soon_threadsafe(drain)
            app.call_soon_threadsafe(app.invalidate)
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)


# ── Stream yield → UiEvent converters ─────────────────────────────


def from_stream_yield(kind: str, payload: Any) -> UiEvent | None:
    """Convert a single send_stream yield (kind, payload) into a UiEvent.

    Called from the AI worker thread for each stream chunk.
    Returns None if the kind is uninteresting (skip it).
    """
    text = str(payload) if not isinstance(payload, str) else payload

    # ── Text ──
    if kind == "text":
        return StreamTextChunk(text)

    # ── Thinking / reasoning ──
    if kind == "thinking":
        return StreamThinkingChunk(text)

    # ── Tool lifecycle ──
    if kind == "info":
        msg = text.strip()
        if not msg:
            return None
        # Chinese tool-start pattern: "正在执行 <tool>", "正在生成 <action>"
        tool_match = re.match(r"正在(执行|生成)\s*(.+)", msg)
        if tool_match:
            tool_name = tool_match.group(2).rstrip(".")
            return StreamToolStarted(tool_name, message=msg)
        # Chinese tool-done pattern
        if "执行完成" in msg or "生成完成" in msg:
            return StreamToolFinished("", success=True, message=msg)
        # Error patterns
        if "fallback" in msg.lower() or "连接中断" in msg:
            return StreamInfo(message=msg)
        return StreamInfo(message=msg)

    if kind == "tool_result":
        return StreamToolFinished(
            tool_name=str(payload.get("name", "")) if isinstance(payload, dict) else "",
            success=True,
        )

    if kind in ("tool_started",):
        return StreamToolStarted(
            tool_name=str(payload.get("name", "")) if isinstance(payload, dict) else str(payload),
        )

    if kind in ("tool_finished",):
        return StreamToolFinished(
            tool_name=str(payload.get("name", "")) if isinstance(payload, dict) else str(payload),
            success=True,
        )

    # ── Errors ──
    if kind == "error":
        return StreamError(error_type="stream", message=text)

    if kind == "tool_failed":
        return StreamToolError(
            tool_name=str(payload.get("name", "")) if isinstance(payload, dict) else "",
            error=text,
        )

    # ── Status-line events (watchdog, provider, system) ──
    status_error_kinds = {
        "watchdog_alert",
        "watchdog_warning",
        "system_warning",
        "system_error",
        "provider_fallback",
        "connection_error",
    }
    status_info_kinds = {
        "status_update",
        "notice",
        "system_info",
        "tool_progress",
    }

    if kind in status_error_kinds:
        return SystemNotification(level="error", message=text)
    if kind in status_info_kinds:
        return SystemNotification(level="info", message=text)

    # ── Media ──
    if kind in ("image", "video"):
        loc = payload.get("local_path", "") or payload.get("url", "") if isinstance(payload, dict) else str(payload)
        if loc:
            return StreamInfo(message=f"Generated: {loc}")

    # ── Stream boundaries ──
    if kind == "stream_start":
        return None  # handled at higher level

    return None


def stream_done_event(elapsed: float = 0.0, tool_count: int = 0) -> StreamDone:
    """Create a StreamDone event after the generator exhausts."""
    return StreamDone(elapsed=elapsed, tool_count=tool_count)


def stream_cancelled_event(reason: str = "") -> StreamCancelled:
    """Create a StreamCancelled event."""
    return StreamCancelled(reason=reason)


def stream_error_event(error_type: str, message: str, hint: str = "") -> StreamError:
    """Create a StreamError event."""
    return StreamError(error_type=error_type, message=message, hint=hint)


# ── Session metadata → UiEvent ────────────────────────────────────


def session_update_event(
    model: str = "",
    cwd: str = "",
    git_branch: str = "",
    context_pct: float = 0.0,
    latency: float | None = None,
    method_level: str = "",
) -> SessionUpdate:
    """Create a SessionUpdate event from current session metadata."""
    return SessionUpdate(
        model=model,
        cwd=cwd,
        git_branch=git_branch,
        context_pct=context_pct,
        latency=latency,
        method_level=method_level,
    )


def resize_event(cols: int, rows: int) -> ResizeEvent:
    """Create a ResizeEvent."""
    return ResizeEvent(cols=cols, rows=rows)


def image_submitted_event(path: str) -> ImageSubmitted:
    """Create an ImageSubmitted event."""
    return ImageSubmitted(path=path)
