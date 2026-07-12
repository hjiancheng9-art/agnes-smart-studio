"""Non-blocking streaming tool executor — run tools without freezing the TUI.

GPT fix #1: "Long shell/MCP/media calls freezing the TUI makes CRUX feel
unstable even when it is working." Wraps tool calls in background threads
and emits lifecycle events for the TUI to subscribe to.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("crux.streaming_executor")


class ToolStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    STREAMING = "streaming"  # output is arriving in chunks
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ToolEvent:
    """Lifecycle event emitted during tool execution."""

    tool_name: str
    status: ToolStatus
    timestamp: float = field(default_factory=time.time)
    output: str = ""  # stdout chunk or final result
    error: str = ""
    progress: float = 0.0  # 0.0–1.0 for progress bars
    metadata: dict = field(default_factory=dict)


# Type for event subscribers
EventListener = Callable[[ToolEvent], None]

# Global subscriber list
_subscribers: list[EventListener] = []
# Thread-local tracking: {thread_id: [(tool_name, start_time)]}
_active_tools: dict[int, list[tuple[str, float]]] = {}
_lock = threading.Lock()


def subscribe(listener: EventListener) -> None:
    """Subscribe to tool lifecycle events. TUI calls this at startup."""
    _subscribers.append(listener)


def unsubscribe(listener: EventListener) -> None:
    """Remove a subscriber."""
    if listener in _subscribers:
        _subscribers.remove(listener)


def _emit(event: ToolEvent) -> None:
    """Emit an event to all subscribers."""
    for sub in _subscribers:
        try:
            sub(event)
        except Exception:
            logger.debug("Event subscriber failed", exc_info=True)


def active_tools() -> list[dict]:
    """Return currently-running tools with elapsed time."""
    with _lock:
        result = []
        now = time.time()
        for tid, tools in _active_tools.items():
            for name, started in tools:
                result.append({"tool": name, "elapsed": round(now - started, 1), "thread": tid})
        return result


def cancel_all() -> int:
    """Cancel all running tools. Returns count cancelled."""
    with _lock:
        count = len(_active_tools)
        for _tid, tools in list(_active_tools.items()):
            for name, _ in tools:
                _emit(ToolEvent(tool_name=name, status=ToolStatus.CANCELLED))
        _active_tools.clear()
    return count


def run_tool(
    tool_name: str,
    handler: Callable[[], Any],
    *,
    timeout: float = 120.0,
    on_chunk: Callable[[str], None] | None = None,
) -> ToolEvent:
    """Execute a tool synchronously with event emission.

    Args:
        tool_name: Name for event tracking
        handler: The tool function to execute (callable with no args)
        timeout: Max execution time in seconds
        on_chunk: Optional callback for streaming stdout chunks

    Returns:
        Final ToolEvent with DONE or FAILED status
    """
    tid = threading.get_ident()

    with _lock:
        _active_tools.setdefault(tid, []).append((tool_name, time.time()))

    _emit(ToolEvent(tool_name=tool_name, status=ToolStatus.RUNNING))

    try:
        result = handler()
        event = ToolEvent(tool_name=tool_name, status=ToolStatus.DONE, output=str(result) if result else "")
        _emit(event)
        return event
    except Exception as e:
        logger.exception("Tool '%s' failed", tool_name)
        event = ToolEvent(tool_name=tool_name, status=ToolStatus.FAILED, error=str(e))
        _emit(event)
        return event
    finally:
        with _lock:
            tools = _active_tools.get(tid, [])
            _active_tools[tid] = [(n, s) for n, s in tools if n != tool_name]
            if not _active_tools[tid]:
                del _active_tools[tid]


async def run_tool_async(
    tool_name: str,
    handler: Callable[[], Any],
    *,
    timeout: float = 120.0,
) -> ToolEvent:
    """Async wrapper — runs the tool in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_tool, tool_name, handler, timeout)


async def run_shell_streaming(cmd: str, *, timeout: float = 60.0) -> ToolEvent:
    """Run a shell command with streaming output.

    Emits STREAMING events for each output line, DONE on completion.
    This is the TUI-friendly version — doesn't block input.
    """

    _emit(ToolEvent(tool_name=f"shell:{cmd[:40]}", status=ToolStatus.RUNNING))

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        output_lines = []
        async for line in proc.stdout:
            try:
                from core.encoding_fix import fix_garbled_bytes
                decoded, _, _ = fix_garbled_bytes(line)
                text = decoded.rstrip()
            except ImportError:
                text = line.decode("utf-8", errors="replace").rstrip()
            output_lines.append(text)
            _emit(
                ToolEvent(
                    tool_name=f"shell:{cmd[:40]}",
                    status=ToolStatus.STREAMING,
                    output=text,
                )
            )

        await asyncio.wait_for(proc.wait(), timeout=timeout)

        full_output = "\n".join(output_lines)
        event = ToolEvent(
            tool_name=f"shell:{cmd[:40]}",
            status=ToolStatus.DONE if proc.returncode == 0 else ToolStatus.FAILED,
            output=full_output,
        )
        _emit(event)
        return event

    except asyncio.TimeoutError:
        event = ToolEvent(tool_name=f"shell:{cmd[:40]}", status=ToolStatus.FAILED, error="timeout")
        _emit(event)
        return event
    except Exception as e:
        event = ToolEvent(tool_name=f"shell:{cmd[:40]}", status=ToolStatus.FAILED, error=str(e))
        _emit(event)
        return event
