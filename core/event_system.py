"""
事件系统规范 — 所有 UI 事件统一经过此层
========================================
职责: 定义事件类型、UI 接口、流式文本修复
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

_log = logging.getLogger("crux.event")


class EventKind(str, Enum):
    """事件类型 — 严格分类，不可混淆"""

    # ── 用户输入 ──
    USER_MESSAGE = "user_message"

    # ── 助理回复 ──
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # ── 内部推理（不进入聊天区） ──
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"

    # ── 工具执行 ──
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"
    TOOL_RAW_OUTPUT = "tool_raw_output"

    # ── 系统 ──
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"
    SYSTEM_NOTICE = "system_notice"

    # ── 流式终了（内部用） ──
    STREAM_END = "stream_end"


# ── 可见白名单 ──
VISIBLE_CHAT_EVENTS = frozenset(
    {
        EventKind.USER_MESSAGE,
        EventKind.ASSISTANT_DELTA,
        EventKind.ASSISTANT_FINAL,
    }
)

TOOL_INLINE_EVENTS = frozenset(
    {
        EventKind.TOOL_STARTED,
        EventKind.TOOL_PROGRESS,
        EventKind.TOOL_FINISHED,
        EventKind.TOOL_FAILED,
    }
)


@dataclass(slots=True)
class UiEvent:
    """结构化 UI 事件"""

    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class UiSink(Protocol):
    """UI 输出端口 — 事件消费者实现此接口"""

    def append_user_message(self, text: str) -> None: ...

    def append_assistant_delta(self, message_id: str, text: str) -> None: ...

    def append_assistant_final(self, message_id: str, text: str) -> None: ...

    def update_tool_status(self, text: str) -> None: ...

    def show_notice(self, text: str, *, error: bool = False) -> None: ...


class StreamingUnicodeSanitizer:
    """
    修复流式文本中被拆开的 UTF-16 代理对。

    Python 正常 Unicode 字符通常不会包含代理字符，但以下情况可能产生：
    1. 使用 surrogatepass 解码；
    2. 从 UTF-16 流按错误边界切块；
    3. 浏览器/CDP/Node 桥接层把代理项单独传给 Python；
    4. JSON 流被错误拆分。
    """

    REPLACEMENT = "\ufffd"

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
        """处理流式文本，返回修复后的字符串"""
        if not text:
            return ""

        output: list[str] = []

        for char in text:
            code = ord(char)

            # 有悬空的 high surrogate
            if self._pending_high is not None:
                if self._is_low_surrogate(code):
                    # 完整的 surrogate pair
                    output.append(self._join_surrogate_pair(ord(self._pending_high), code))
                    self.repaired_count += 1
                else:
                    # 前一个 high surrogate 无法配对 → 用替换字符
                    output.append(self.REPLACEMENT)
                    output.append(char)
                self._pending_high = None
                continue

            # 新的 high surrogate → 暂存
            if self._is_high_surrogate(code):
                self._pending_high = char
                continue

            # 普通字符
            output.append(char)

        return "".join(output)

    def flush(self) -> str:
        """结束流式输入，返回残存的 pending high surrogate（若有）"""
        if self._pending_high is not None:
            result = self.REPLACEMENT
            self._pending_high = None
            return result
        return ""


# 全局单例
_sanitizer = StreamingUnicodeSanitizer()


def sanitize_stream(text: str | None) -> str:
    """全局流式文本修复入口"""
    return _sanitizer.feed(text)


def sanitize_flush() -> str:
    """全局 flush"""
    return _sanitizer.flush()
