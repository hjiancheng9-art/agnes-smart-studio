"""UI Event Sink — typed event channel with surrogate-safe streaming.

Defines:
- EventKind: typed categories for all UI events
- UiEvent: structured event with kind, text, metadata
- UiSink: protocol (interface) for UI backends
- StreamingUnicodeSanitizer: fixes split UTF-16 surrogate pairs
- HiddenEventLogger: writes hidden events to rotating log files
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol


class EventKind(str, Enum):
    """Typed event categories — controls routing to chat vs status vs log."""
    # ── Chat-visible ──
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # ── Hidden from chat (internal reasoning) ──
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    SYSTEM_WARNING = "system_warning"
    TOOL_RAW_OUTPUT = "tool_raw_output"
    SYSTEM_ERROR = "system_error"

    # ── Tool status (compact one-line) ──
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"

    # ── System alerts (notification bar) ──
    CONNECTION_ERROR = "connection_error"
    PROVIDER_FALLBACK = "provider_fallback"
    WATCHDOG_WARNING = "watchdog_warning"


@dataclass(slots=True)
class UiEvent:
    """Structured UI event with routing metadata."""
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class UiSink(Protocol):
    """Protocol for UI backends (TUI, CLI, WebSocket)."""

    def append_user_message(self, text: str) -> None:
        ...

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        ...

    def update_status(self, text: str) -> None:
        ...

    def show_notice(self, text: str, *, error: bool = False) -> None:
        ...


# ── Event routing tables ──
VISIBLE_CHAT_EVENTS: frozenset[EventKind] = frozenset({
    EventKind.USER_MESSAGE,
    EventKind.ASSISTANT_DELTA,
    EventKind.ASSISTANT_FINAL,
})

HIDDEN_EVENTS: frozenset[EventKind] = frozenset({
    EventKind.REASONING,
    EventKind.ANALYSIS,
    EventKind.INTERNAL_PROMPT,
    EventKind.DEBUG,
    EventKind.TOOL_RAW_OUTPUT,
})

TOOL_STATUS_EVENTS: frozenset[EventKind] = frozenset({
    EventKind.TOOL_STARTED,
    EventKind.TOOL_PROGRESS,
    EventKind.TOOL_FINISHED,
    EventKind.TOOL_FAILED,
})

SYSTEM_ALERT_EVENTS: frozenset[EventKind] = frozenset({
    EventKind.CONNECTION_ERROR,
    EventKind.PROVIDER_FALLBACK,
    EventKind.WATCHDOG_WARNING,
    EventKind.SYSTEM_ERROR,
})

EVENT_TO_ROLE: dict[EventKind, str] = {
    EventKind.USER_MESSAGE: "user",
    EventKind.ASSISTANT_DELTA: "assistant_delta",
    EventKind.ASSISTANT_FINAL: "assistant_final",
    EventKind.SYSTEM_WARNING: "info",
    EventKind.SYSTEM_ERROR: "error",
}


class StreamingUnicodeSanitizer:
    """修复流式文本中被拆开的 UTF-16 代理对 (低位代理崩溃)。

    场景:
    1. surrogatepass 解码
    2. UTF-16 流按错误边界切块
    3. 浏览器/CDP/Node 桥接层把代理项单独传给 Python
    4. JSON 流被错误拆分
    """

    REPLACEMENT = "\uFFFD"

    def __init__(self) -> None:
        self._pending_high: str | None = None
        self.repaired_count = 0

    @staticmethod
    def _is_high_surrogate(code: int) -> bool:
        return 0xD800 <= code <= 0xDBFF

    @staticmethod
    def _is_low_surrogate(code: int) -> bool:
        return 0xDC00 <= code <= 0xDFFF

    @staticmethod
    def _join_surrogate_pair(high: int, low: int) -> str:
        codepoint = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
        return chr(codepoint)

    def feed(self, text: str | None) -> str:
        """处理流式文本块，修复被拆开的代理对。"""
        if not text:
            return ""

        output: list[str] = []

        for char in text:
            code = ord(char)

            if self._pending_high is not None:
                high_code = ord(self._pending_high)
                if self._is_low_surrogate(code):
                    output.append(self._join_surrogate_pair(high_code, code))
                    self._pending_high = None
                    continue
                # 上一个高位代理没有遇到低位代理 → 替换
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                self._pending_high = None

            if self._is_high_surrogate(code):
                self._pending_high = char
            elif self._is_low_surrogate(code):
                # Lone low surrogate (no pending high) — replace with U+FFFD.
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
            else:
                output.append(char)

        return "".join(output)

    def flush(self) -> str:
        """清空待处理的高位代理（流结束时调用）。"""
        if self._pending_high is not None:
            self.repaired_count += 1
            result = self.REPLACEMENT
            self._pending_high = None
            return result
        return ""

    def reset(self) -> None:
        """重置状态（开始新流时调用）。"""
        self._pending_high = None


class HiddenEventLogger:
    """将隐藏事件写入轮转日志文件，不污染聊天区。"""

    def __init__(self, log_dir: str | Path = ".crux_memory"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger("crux.ui.hidden")
        self._logger.setLevel(logging.DEBUG)
        self._logger.handlers.clear()

        handler = RotatingFileHandler(
            self.log_dir / "hidden_events.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(message)s"
        ))
        self._logger.addHandler(handler)

    def log(self, event: UiEvent) -> None:
        """记录一个结构化事件。"""
        self._logger.debug("[%s] %s", event.kind.value, event.text[:500])

    def log_raw(self, kind: str, text: str) -> None:
        """记录原始字符串事件（向后兼容）。"""
        self._logger.debug("[%s] %s", kind, text[:500])
