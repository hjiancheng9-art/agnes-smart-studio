"""UI 事件协议 — 代理对修复 + 事件通道隔离。

定义：
- EventKind: 事件类型枚举
- UiEvent: 结构化事件
- UiSink: UI 端接口协议
- StreamingUnicodeSanitizer: 流式 UTF-16 代理对修复
- UiStreamGuard: CRUX 事件进入 UI 前的唯一入口
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class EventKind(str, Enum):
    """CRUX → UI 事件类型。"""

    # ── 可见事件（进入聊天正文） ──
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # ── 工具状态（单行动态） ──
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"

    # ── 隐藏事件（仅写日志） ──
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    SYSTEM_WARNING = "system_warning"
    TOOL_RAW_OUTPUT = "tool_raw_output"
    SYSTEM_ERROR = "system_error"


@dataclass(slots=True)
class UiEvent:
    """标准 UI 事件结构。"""

    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""


class UiSink(Protocol):
    """UI 端需要实现的最小接口。"""

    def append_user_message(self, text: str) -> None:
        ...

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        ...

    def update_status(self, text: str) -> None:
        ...

    def show_notice(self, text: str, *, error: bool = False) -> None:
        ...


# ── StreamingUnicodeSanitizer ─────────────────────────────────────────────


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

            # 处理上一步残留的高位代理
            if self._pending_high is not None:
                high_code = ord(self._pending_high)
                if self._is_low_surrogate(code):
                    # 成功配对
                    output.append(self._join_surrogate_pair(high_code, code))
                    self._pending_high = None
                    continue
                # 上一个高位代理没有遇到低位代理 → 替换
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                self._pending_high = None

            if self._is_high_surrogate(code):
                self._pending_high = char
                continue

            if self._is_low_surrogate(code):
                # 孤立的低位代理
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                continue

            output.append(char)

        return "".join(output)

    def finish(self) -> str:
        if self._pending_high is None:
            return ""
        self._pending_high = None
        self.repaired_count += 1
        return self.REPLACEMENT


# ── UiStreamGuard ─────────────────────────────────────────────────────────


class UiStreamGuard:
    """
    CRUX 事件进入 UI 前的唯一入口。

    规则：
    - reasoning/analysis/debug 只进入日志文件；
    - 原始工具输出不进入聊天区；
    - Unicode 清洗按 message_id 保存流式状态。
    """

    # 绝不进入聊天区的事件
    HIDDEN_EVENTS = frozenset({
        EventKind.REASONING,
        EventKind.ANALYSIS,
        EventKind.INTERNAL_PROMPT,
        EventKind.DEBUG,
        EventKind.TOOL_RAW_OUTPUT,
    })

    # 合并为单行动态状态的事件
    TOOL_STATUS_EVENTS = frozenset({
        EventKind.TOOL_STARTED,
        EventKind.TOOL_FINISHED,
        EventKind.TOOL_PROGRESS,
        EventKind.TOOL_FAILED,
    })

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

    def _stream(self, message_id: str) -> StreamingUnicodeSanitizer:
        return self._sanitizers.setdefault(
            message_id,
            StreamingUnicodeSanitizer(),
        )

    def _record_repairs(
        self,
        before: int,
        sanitizer: StreamingUnicodeSanitizer,
    ) -> None:
        repaired = sanitizer.repaired_count - before
        if repaired <= 0:
            return
        self._surrogate_total += repaired
        now = time.monotonic()
        # 最多每 30 秒写一次文件日志，绝不发送 UI 事件
        if now - self._last_surrogate_log >= 30:
            self.logger.warning(
                "Repaired %d surrogate pairs (total=%d)",
                repaired,
                self._surrogate_total,
            )
            self._last_surrogate_log = now

    def dispatch(self, event: UiEvent) -> None:
        if event.kind in self.HIDDEN_EVENTS:
            self.logger.debug(
                "Hidden event kind=%s message_id=%s text=%r",
                event.kind,
                event.message_id,
                event.text[:200],
            )
            return

        sanitizer = self._stream(event.message_id)
        before = sanitizer.repaired_count
        cleaned = sanitizer.feed(event.text)
        self._record_repairs(before, sanitizer)

        if event.kind == EventKind.USER_MESSAGE:
            self.sink.append_user_message(cleaned)
        elif event.kind in (EventKind.ASSISTANT_DELTA, EventKind.ASSISTANT_FINAL):
            self.sink.append_assistant_delta(event.message_id, cleaned)
        elif event.kind in self.TOOL_STATUS_EVENTS:
            self.sink.update_status(cleaned)
        elif event.kind == EventKind.SYSTEM_WARNING:
            self.sink.show_notice(cleaned)
        elif event.kind == EventKind.SYSTEM_ERROR:
            self.sink.show_notice(cleaned, error=True)
        else:
            self.logger.debug("Unhandled event kind=%s", event.kind)

    def finish_message(self, message_id: str) -> None:
        """消息结束时冲洗未配对的代理对。"""
        sanitizer = self._sanitizers.pop(message_id, None)
        if sanitizer is None:
            return
        before = sanitizer.repaired_count
        tail = sanitizer.finish()
        if tail:
            self.logger.warning(
                "Message %s ended with unpaired surrogate, repaired=%d",
                message_id,
                sanitizer.repaired_count - before,
            )


# ── 日志配置 ──────────────────────────────────────────────────────────────


def configure_event_log(dir_path: str | Path = ".crux/logs") -> logging.Logger:
    """配置专门的事件日志，与主日志分离。"""
    log_dir = Path(dir_path)
    log_dir.mkdir(parents=True, exist_ok=True)

    log = logging.getLogger("crux.ui.guard")
    log.setLevel(logging.DEBUG)

    handler = logging.handlers.RotatingFileHandler(
        log_dir / "hidden_events.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
    ))
    log.addHandler(handler)

    return log
