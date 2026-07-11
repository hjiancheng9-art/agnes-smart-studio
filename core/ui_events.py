"""CRUX → UI 事件协议：EventKind、UiEvent、UiSink、UiStreamGuard。

低位代理修复 + 事件通道隔离，单入口守卫所有 UI 事件。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class EventKind(str, Enum):
    """事件种类。只有 VISIBLE_CHAT 类进入聊天正文。"""

    # ── 用户可见聊天消息 ──
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # ── 通知（可见，但非聊天正文） ──
    INFO = "info"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"
    TOOL_STATUS = "tool_status"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"

    # ── 内部事件（仅写日志，不进 UI） ──
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    TOOL_RAW_OUTPUT = "tool_raw_output"


# ── 分类集合 ──
VISIBLE_CHAT_KINDS = frozenset({
    EventKind.USER_MESSAGE,
    EventKind.ASSISTANT_DELTA,
    EventKind.ASSISTANT_FINAL,
})

NOTICE_KINDS = frozenset({
    EventKind.INFO,
    EventKind.SYSTEM_WARNING,
    EventKind.SYSTEM_ERROR,
})

TOOL_KINDS = frozenset({
    EventKind.TOOL_STATUS,
    EventKind.TOOL_STARTED,
    EventKind.TOOL_FINISHED,
})

HIDDEN_KINDS = frozenset({
    EventKind.REASONING,
    EventKind.ANALYSIS,
    EventKind.INTERNAL_PROMPT,
    EventKind.DEBUG,
    EventKind.TOOL_RAW_OUTPUT,
})


@dataclass(slots=True)
class UiEvent:
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""


# ── UI 需要实现的接口 ──

class UiSink(Protocol):
    """UI 侧只需实现这四个方法，所有过滤由 UiStreamGuard 完成。"""

    def append_user_message(self, text: str) -> None:
        ...

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        ...

    def update_status(self, text: str) -> None:
        ...

    def show_notice(self, text: str, *, error: bool = False) -> None:
        ...


# ── 流式 Unicode 清洗 ──

class StreamingUnicodeSanitizer:
    """
    修复流式文本中被拆开的 UTF-16 代理对。

    Python 正常 Unicode 字符通常不会包含代理字符，但以下情况可能产生：
    1. 使用 surrogatepass 解码；
    2. 从 UTF-16 流按错误边界切块；
    3. 浏览器/CDP/Node 桥接层把代理项单独传给 Python；
    4. JSON 流被错误拆分。
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
        if not text:
            return ""
        output: list[str] = []
        for char in text:
            code = ord(char)
            if self._pending_high is not None:
                if self._is_low_surrogate(code):
                    output.append(
                        self._join_surrogate_pair(ord(self._pending_high), code)
                    )
                    self._pending_high = None
                    continue
                # 上一个高位代理没有遇到低位代理。
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                self._pending_high = None
            if self._is_high_surrogate(code):
                self._pending_high = char
                continue
            if self._is_low_surrogate(code):
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                continue
            output.append(char)
        return "".join(output)

    def finish(self) -> str:
        if self._pending_high is None:
            return ""
        self.repaired_count += 1
        self._pending_high = None
        return self.REPLACEMENT


# ── 单一守卫入口 ──

class UiStreamGuard:
    """
    CRUX 事件进入 UI 前的唯一入口。

    规则：
    - 原始工具输出不进入聊天区；
    - Unicode 清洗按 message_id 保存流式状态；
    - reasoning/analysis/debug 只进入日志文件；
    - 工具状态合并为单行，不占聊天正文空间。
    """

    HIDDEN_KINDS = {
        EventKind.REASONING,
        EventKind.ANALYSIS,
        EventKind.INTERNAL_PROMPT,
        EventKind.DEBUG,
        EventKind.TOOL_RAW_OUTPUT,
    }

    TOOL_PROGRESS_KINDS = {
        EventKind.TOOL_FINISHED,
        EventKind.TOOL_STARTED,
        EventKind.TOOL_STATUS,
    }

    def __init__(
        self,
        sink: UiSink,
        logger: logging.Logger | None = None,
    ) -> None:
        self.sink = sink
        self.logger = logger or logging.getLogger("crux.ui.guard")
        self._sanitizers: dict[str, StreamingUnicodeSanitizer] = {}
        self._last_surrogate_log = 0.0
        self._surrogate_total = 0

    def push(self, event: UiEvent) -> None:
        """单入口：所有 CRUX 事件通过此方法进入 UI。"""
        kind = event.kind

        # ── 隐藏事件 → 日志 ──
        if kind in self.HIDDEN_KINDS:
            self.logger.debug("[hidden/%s] %s", kind.value, event.text[:200])
            return

        # ── 工具进度 → 单行状态栏 ──
        if kind in self.TOOL_PROGRESS_KINDS:
            status_text = self._format_tool_status(event)
            self.sink.update_status(status_text)
            return

        # ── 通知类 → show_notice ──
        if kind in NOTICE_KINDS:
            self.sink.show_notice(
                event.text,
                error=kind in (EventKind.SYSTEM_ERROR,),
            )
            return

        # ── 聊天消息 → 清洗 + 发送 ──
        if kind is EventKind.USER_MESSAGE:
            self.sink.append_user_message(event.text)
            return

        if kind is EventKind.ASSISTANT_DELTA:
            cleaned = self._sanitize_stream(event.message_id, event.text)
            if cleaned:
                self.sink.append_assistant_delta(event.message_id, cleaned)
            return

        if kind is EventKind.ASSISTANT_FINAL:
            # 刷新流式缓冲
            sanitizer = self._sanitizers.pop(event.message_id, None)
            if sanitizer:
                tail = sanitizer.finish()
                if tail:
                    self.sink.append_assistant_delta(event.message_id, tail)
                    self._surrogate_total += sanitizer.repaired_count
            self.sink.append_assistant_delta(event.message_id, "")  # 标记结束
            return

        # 未知种类 → 日志 + 降级
        self.logger.warning("[unknown_event_kind] %s", kind.value)
        self.sink.show_notice(f"[{kind.value}] {event.text[:100]}")

    def _sanitize_stream(self, message_id: str, text: str) -> str:
        if message_id not in self._sanitizers:
            self._sanitizers[message_id] = StreamingUnicodeSanitizer()
        cleaned = self._sanitizers[message_id].feed(text)
        if self._sanitizers[message_id].repaired_count:
            now = time.time()
            if now - self._last_surrogate_log > 10:
                self.logger.warning(
                    "Streaming surrogate repaired: %d so far",
                    self._surrogate_total + self._sanitizers[message_id].repaired_count,
                )
                self._last_surrogate_log = now
        return cleaned

    def _format_tool_status(self, event: UiEvent) -> str:
        if event.kind is EventKind.TOOL_STARTED:
            return f"⏳ {event.tool_name or event.text[:60]}"
        if event.kind is EventKind.TOOL_FINISHED:
            return f"✓ {event.tool_name or 'done'} · {event.text[:40]}"
        if event.kind is EventKind.TOOL_STATUS:
            return f"⚙ {event.text[:80]}"
        return str(event.text[:80])
