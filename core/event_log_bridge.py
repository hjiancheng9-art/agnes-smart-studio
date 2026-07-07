"""EventLog ↔ EventBus Bridge — 自动将工具调用事件写入 EventLog

挂载方式（在 crux_studio.py 初始化时）：
    from core.event_log_bridge import bridge_event_log
    bridge_event_log(event_bus, session_id="...")

此后每次 TOOL_CALL_* 事件都会自动记录到 EventLog。
"""

import time
from typing import Any

from core.event_bus import (
    TOOL_CALL_COMPLETE,
    TOOL_CALL_FAILED,
    TOOL_CALL_START,
    TOOL_CALL_TIMEOUT,
)
from core.event_log import record_event

# ── Per-call tracking ─────────────────────────────────────
_pending_calls: dict[str, dict[str, Any]] = {}


def _on_tool_start(event: str, **kwargs):
    """Record tool call start time."""
    call_id = kwargs.get("call_id", "")
    if call_id:
        _pending_calls[call_id] = {
            "start_time": time.time(),
            "tool": kwargs.get("tool_name", ""),
            "intent": kwargs.get("intent", ""),
            "session_id": kwargs.get("session_id", ""),
            "metadata": kwargs.get("metadata", {}),
        }


def _on_tool_end(event: str, **kwargs):
    """Record tool completion (success/failure/fallback/timeout)."""
    call_id = kwargs.get("call_id", "")
    pending = _pending_calls.pop(call_id, None)

    duration_ms = 0
    tool = kwargs.get("tool_name", "")
    intent = ""
    metadata = {}

    if pending:
        duration_ms = int((time.time() - pending["start_time"]) * 1000)
        tool = tool or pending["tool"]
        intent = pending["intent"]
        pending["session_id"]
        metadata = pending.get("metadata", {})

    # Merge result metadata
    if kwargs.get("result_metadata"):
        metadata = {**metadata, **kwargs["result_metadata"]}

    # Determine status
    if event == TOOL_CALL_COMPLETE:
        status = "success"
    elif event == TOOL_CALL_FAILED:
        status = "failure"
    elif event == TOOL_CALL_TIMEOUT:
        status = "timeout"
    else:
        status = "unknown"

    error_type = kwargs.get("error_type", "")

    record_event(
        intent=intent,
        tool=tool,
        status=status,
        duration_ms=duration_ms,
        error_type=error_type,
        metadata={
            **metadata,
            "call_id": call_id,
        },
    )


def bridge_event_log(event_bus, session_id: str = ""):
    """Wire EventLog to EventBus.

    After this call, all TOOL_CALL_* events are automatically logged.
    """
    from core.event_log import get_event_log

    # Init EventLog with session
    log = get_event_log(session_id=session_id)

    # Register listeners on EventBus
    event_bus.on(TOOL_CALL_START, _on_tool_start)
    event_bus.on(TOOL_CALL_COMPLETE, _on_tool_end)
    event_bus.on(TOOL_CALL_FAILED, _on_tool_end)
    event_bus.on(TOOL_CALL_TIMEOUT, _on_tool_end)

    # Also hook events we missed: if a call was emitted without start tracking
    # just record it directly
    def _direct_log(event: str, **kwargs):
        call_id = kwargs.get("call_id", "")
        if call_id not in _pending_calls:
            _on_tool_end(event, **kwargs)

    event_bus.on(TOOL_CALL_COMPLETE, _direct_log)
    event_bus.on(TOOL_CALL_FAILED, _direct_log)

    print(f"[EventLog] Bridged to EventBus (session={session_id[:8]}...)")
    return log
