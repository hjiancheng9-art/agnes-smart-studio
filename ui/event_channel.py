"""CRUX UI Event channel — structured event dispatch.
Replaces raw string-based role passing with typed events and sink protocol.

P0: 禁止 analysis/reasoning/debug/tool_raw 进入聊天区。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

# ── 事件类型 ────────────────────────────────────────────

class EventKind(str, Enum):
    """事件分类。只有 CHAT 类进入聊天区，其余写入日志或状态栏。"""
    # → 聊天正文
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # → 状态栏（单行）
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"
    STATUS_UPDATE = "status_update"

    # → 通知区（可自动消失）
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"
    PROVIDER_FALLBACK = "provider_fallback"
    WATCHDOG_ALERT = "watchdog_alert"

    # → 仅日志（绝不进入 UI）
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    TOOL_RAW_OUTPUT = "tool_raw_output"


# ── 结构化事件 ──────────────────────────────────────────

@dataclass(slots=True)
class UiEvent:
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ── UI Sink 协议 ────────────────────────────────────────

class UiSink(Protocol):
    """任何实现此协议的 UI 后端都可接收 CRUX 事件。"""

    def append_user_message(self, text: str) -> None:
        ...

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        ...

    def append_assistant_final(self, message_id: str, text: str) -> None:
        ...

    def update_status(self, text: str) -> None:
        ...

    def show_notice(self, text: str, *, error: bool = False) -> None:
        ...


# ── 流式文本 Unicode 修复 ──────────────────────────────
# Re-export the canonical sanitizer from stream_guard instead of maintaining
# a broken duplicate here. The previous in-file version misjudged complete
# surrogate pairs and flush() returned raw surrogates.
from ui.stream_guard import StreamingUnicodeSanitizer

# Per-stream sanitizer cache: message_id → sanitizer instance.
_SANITIZERS: dict[str, StreamingUnicodeSanitizer] = {}


# ── 隐藏事件日志 ────────────────────────────────────────

_HIDDEN_LOG: RotatingFileHandler | None = None

_HIDDEN_KINDS = frozenset({
    EventKind.REASONING,
    EventKind.ANALYSIS,
    EventKind.INTERNAL_PROMPT,
    EventKind.DEBUG,
    EventKind.TOOL_RAW_OUTPUT,
})


def _get_hidden_logger() -> logging.Logger:
    global _HIDDEN_LOG
    if _HIDDEN_LOG is None:
        log_dir = Path(".crux_memory")
        log_dir.mkdir(exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "hidden_events.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        _HIDDEN_LOG = handler
    logger = logging.getLogger("crux.ui.hidden")
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(_HIDDEN_LOG)
        logger.setLevel(logging.DEBUG)
    return logger


def dispatch_event(event: UiEvent, sink: UiSink) -> None:
    """根据事件类型分发到 UI 的不同区域。"""
    kind = event.kind

    if kind == EventKind.USER_MESSAGE:
        sink.append_user_message(event.text)

    elif kind == EventKind.ASSISTANT_DELTA:
        # Sanitize streaming delta through the canonical surrogate-pair repair.
        mid = event.message_id or "_default"
        san = _SANITIZERS.get(mid)
        if san is None:
            san = StreamingUnicodeSanitizer()
            _SANITIZERS[mid] = san
        clean = san.feed(event.text)
        if clean:
            sink.append_assistant_delta(mid, clean)

    elif kind == EventKind.ASSISTANT_FINAL:
        # Flush any remaining pending surrogate and clean up the sanitizer.
        mid = event.message_id or "_default"
        san = _SANITIZERS.pop(mid, None)
        tail = san.finish() if san else ""
        final_text = event.text
        # Feed through sanitizer to catch broken surrogates
        if final_text:
            final_text = san.feed(final_text)
        final_text += san.finish()
        if tail:
            final_text = tail + final_text
        sink.append_assistant_final(mid, final_text)

    elif kind in (EventKind.TOOL_STARTED, EventKind.TOOL_FINISHED, EventKind.TOOL_FAILED):
        sink.update_status(f"⚙ {event.tool_name}: {event.text[:80]}")

    elif kind == EventKind.STATUS_UPDATE:
        sink.update_status(event.text)

    elif kind in (EventKind.SYSTEM_WARNING, EventKind.PROVIDER_FALLBACK, EventKind.WATCHDOG_ALERT):
        sink.show_notice(event.text, error=False)

    elif kind == EventKind.SYSTEM_ERROR:
        sink.show_notice(event.text, error=True)

    elif kind in _HIDDEN_KINDS:
        _get_hidden_logger().debug("[%s] %s", kind.value, event.text[:500])

    else:
        _get_hidden_logger().debug("[%s] %s", kind.value, event.text[:500])
