"""UiEvent — 类型化 UI 事件通道。

替代现有的 str-based role 过滤系统。
事件按 kind 分三类：
  VISIBLE  → append_user_message / append_assistant_delta (进聊天区)
  STATUS   → update_status (单行动态)
  NOTICE   → show_notice (通知栏浮动)

流式 UTF-16 代理对修复内置在 StreamingUnicodeSanitizer 中。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

# ── Event Kind ─────────────────────────────────────────────────

class EventKind(str, Enum):
    # VISIBLE — 进聊天正文
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"
    INFO = "info"

    # STATUS — 单行动态
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FAILED = "tool_failed"

    # NOTICE — 通知栏
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"
    CONNECTION_ERROR = "connection_error"
    PROVIDER_FALLBACK = "provider_fallback"

    # HIDDEN — 仅日志
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    TOOL_RAW_OUTPUT = "tool_raw_output"


# ── 可见性分类 ────────────────────────────────────────────────

VISIBLE_KINDS = frozenset({
    EventKind.USER_MESSAGE,
    EventKind.ASSISTANT_DELTA,
    EventKind.ASSISTANT_FINAL,
    EventKind.INFO,
})

STATUS_KINDS = frozenset({
    EventKind.TOOL_STARTED,
    EventKind.TOOL_FINISHED,
    EventKind.TOOL_PROGRESS,
    EventKind.TOOL_FAILED,
})

NOTICE_KINDS = frozenset({
    EventKind.SYSTEM_WARNING,
    EventKind.SYSTEM_ERROR,
    EventKind.CONNECTION_ERROR,
    EventKind.PROVIDER_FALLBACK,
})

HIDDEN_KINDS = frozenset({
    EventKind.REASONING,
    EventKind.ANALYSIS,
    EventKind.INTERNAL_PROMPT,
    EventKind.DEBUG,
    EventKind.TOOL_RAW_OUTPUT,
})


# ── 事件结构 ──────────────────────────────────────────────────

@dataclass(slots=True)
class UiEvent:
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""

    @property
    def is_visible(self) -> bool:
        return self.kind in VISIBLE_KINDS

    @property
    def is_status(self) -> bool:
        return self.kind in STATUS_KINDS

    @property
    def is_notice(self) -> bool:
        return self.kind in NOTICE_KINDS

    @property
    def is_hidden(self) -> bool:
        return self.kind in HIDDEN_KINDS


# ── UI Sink Protocol ──────────────────────────────────────────

@runtime_checkable
class UiSink(Protocol):
    """UI 输出接口。事件经过 reduce 后通过此接口渲染。"""

    def append_user_message(self, text: str) -> None:
        ...

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        ...

    def update_status(self, text: str) -> None:
        """单行动态状态条，每行只显示最新一条。"""
        ...

    def show_notice(self, text: str, *, error: bool = False) -> None:
        """通知栏浮动消息，不占用聊天区空间。"""
        ...


# ── 事件归约器 ────────────────────────────────────────────────

class EventReducer:
    """
    根据事件 kind 分发到对应的 UiSink 方法。
    是消息通道的单一控制点：所有 emit_assistant_message / emit_user_message 等
    最终都通过此处写入 UI。
    """

    def __init__(self, sink: UiSink, event_log_path: str | Path | None = None):
        self._sink = sink
        self._log_path = Path(event_log_path) if event_log_path else None
        self._logger = logging.getLogger("crux.ui.event")
        self._setup_logger()

        # 状态行聚合
        self._tool_count: int = 0
        self._tool_start_time: float = 0.0
        self._status_line: str = ""

    def _setup_logger(self) -> None:
        if not self._log_path:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(self._log_path), encoding="utf-8")
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
        self._logger.addHandler(handler)
        self._logger.setLevel(logging.DEBUG)

    def reduce(self, event: UiEvent) -> None:
        """单事件入口：按 kind 分类处理。"""
        if event.is_visible:
            self._handle_visible(event)
        elif event.is_status:
            self._handle_status(event)
        elif event.is_notice:
            self._handle_notice(event)
        else:
            self._handle_hidden(event)

    # ── Visible ──

    def _handle_visible(self, event: UiEvent) -> None:
        if event.kind == EventKind.USER_MESSAGE:
            self._sink.append_user_message(event.text)
        elif event.kind in (EventKind.ASSISTANT_DELTA, EventKind.ASSISTANT_FINAL):
            self._sink.append_assistant_delta(event.message_id, event.text)
        elif event.kind == EventKind.INFO:
            self._sink.show_notice(event.text)

    # ── Status (合并为单行动态) ──

    def _handle_status(self, event: UiEvent) -> None:
        now = time.time()
        if event.kind == EventKind.TOOL_STARTED:
            self._tool_count += 1
            self._tool_start_time = now
            self._status_line = f"⏳ {event.text[:80]}"
        elif event.kind == EventKind.TOOL_FINISHED:
            elapsed = now - self._tool_start_time if self._tool_start_time else 0
            self._status_line = f"✓ 已完成 {self._tool_count} 个工具 · {elapsed:.0f}s"
        elif event.kind == EventKind.TOOL_FAILED:
            self._status_line = f"✕ 工具执行失败: {event.text[:60]}"
        elif event.kind == EventKind.TOOL_PROGRESS:
            self._status_line = f"⏳ {event.text[:60]}"
        self._sink.update_status(self._status_line)

    # ── Notice ──

    def _handle_notice(self, event: UiEvent) -> None:
        is_error = event.kind in (EventKind.SYSTEM_ERROR, EventKind.CONNECTION_ERROR)
        self._sink.show_notice(event.text, error=is_error)

    # ── Hidden ──

    def _handle_hidden(self, event: UiEvent) -> None:
        self._logger.debug("[%s] %s", event.kind.value, event.text[:200])

    # ── Batch ──

    def reduce_batch(self, events: list[UiEvent]) -> None:
        for event in events:
            self.reduce(event)


# ── 流式代理对修复 ─────────────────────────────────────────────

class StreamingUnicodeSanitizer:
    """
    修复流式文本中被拆开的 UTF-16 代理对。

    Python 正常 Unicode 字符通常不会包含代理字符，但以下情况可能产生：
    1. 使用 surrogatepass 解码；
    2. 从 UTF-16 流按错误边界切块；
    3. 浏览器/CDP/Node 桥接层把代理项单独传给 Python；
    """

    def __init__(self):
        self._buffer = ""

    def sanitize(self, chunk: str) -> str:
        sanitized, rest = self._process_chunk(chunk)
        return sanitized

    def flush(self) -> str:
        if self._buffer:
            leftover = self._buffer
            self._buffer = ""
            return leftover
        return ""

    def _process_chunk(self, chunk: str) -> tuple[str, str]:
        combined = self._buffer + chunk
        cleaned: list[str] = []
        i = 0
        n = len(combined)

        while i < n:
            cp = ord(combined[i])
            # 高位代理 (U+D800-U+DBFF)
            if 0xD800 <= cp <= 0xDBFF:
                if i + 1 < n:
                    next_cp = ord(combined[i + 1])
                    if 0xDC00 <= next_cp <= 0xDFFF:
                        # 完整代理对 → 转成 BMP/SMP 字符
                        full = chr(0x10000 + (cp - 0xD800) * 0x400 + (next_cp - 0xDC00))
                        cleaned.append(full)
                        i += 2
                        continue
                # 不完整的高位代理，缓存等下一个 chunk
                self._buffer = combined[i:]
                return "".join(cleaned), self._buffer
            elif 0xDC00 <= cp <= 0xDFFF:
                # 孤立的低位代理，丢弃
                i += 1
                continue
            else:
                cleaned.append(combined[i])
                i += 1

        self._buffer = ""
        return "".join(cleaned), ""
