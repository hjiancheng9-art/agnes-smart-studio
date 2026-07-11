"""CRUX Stream Guard — UI 事件唯一入口。

规则：
- reasoning/analysis/debug/internal_prompt/tool_raw_output → 仅日志，不进聊天区
- tool_started/tool_progress/tool_finished/tool_failed → 单行状态栏
- assistant_delta/assistant_final/user_message → 聊天正文
- system_warning/system_error → 通知区
- 流式文本自动修复被拆分的 UTF-16 代理对
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

# ═══════════════════════════════════════════════════════════
# Event kinds
# ═══════════════════════════════════════════════════════════

class EventKind(str, Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"
    TOOL_RAW_OUTPUT = "tool_raw_output"


@dataclass(slots=True)
class UiEvent:
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""


# ═══════════════════════════════════════════════════════════
# UiSink protocol — UI 必须实现
# ═══════════════════════════════════════════════════════════

class UiSink(Protocol):
    def append_user_message(self, text: str) -> None: ...
    def append_assistant_delta(self, message_id: str, text: str) -> None: ...
    def finish_assistant_message(self, message_id: str, text: str) -> None: ...
    def update_status(self, text: str) -> None: ...
    def show_notice(self, text: str, *, error: bool = False) -> None: ...


# ═══════════════════════════════════════════════════════════
# Streaming Unicode sanitizer — 修复被拆分的代理对
# ═══════════════════════════════════════════════════════════

class StreamingUnicodeSanitizer:
    """有状态修复流式文本中的 UTF-16 代理对断裂。

    常见来源：CDP/Node 桥接层按错误边界切块、surrogatepass 解码、
    JSON 流被拆分、emoji 在分片边界断开。
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

            # 有 pending 高位：期待低位
            if self._pending_high is not None:
                high_code = ord(self._pending_high)
                if self._is_low_surrogate(code):
                    output.append(self._join_surrogate_pair(high_code, code))
                    self._pending_high = None
                    continue
                # 孤立高位 → 替换并继续
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                self._pending_high = None

            if self._is_high_surrogate(code):
                self._pending_high = char
                continue

            if self._is_low_surrogate(code):
                # 孤立低位 → 替换
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


# ═══════════════════════════════════════════════════════════
# UiStreamGuard — 事件分发守卫
# ═══════════════════════════════════════════════════════════

class UiStreamGuard:
    """CRUX 事件进入 UI 前的唯一入口。过滤 + 清洗 + 分发。"""

    HIDDEN_EVENTS = frozenset({
        EventKind.REASONING,
        EventKind.ANALYSIS,
        EventKind.INTERNAL_PROMPT,
        EventKind.DEBUG,
        EventKind.TOOL_RAW_OUTPUT,
    })

    TOOL_EVENTS = frozenset({
        EventKind.TOOL_STARTED,
        EventKind.TOOL_PROGRESS,
        EventKind.TOOL_FINISHED,
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
                "Repaired invalid Unicode surrogate data; total=%d",
                self._surrogate_total,
            )
            self._last_surrogate_log = now

    # ── dispatch ─────────────────────────────────────────

    def dispatch(self, event: UiEvent) -> None:
        # 隐藏事件 → 仅日志
        if event.kind in self.HIDDEN_EVENTS:
            self.logger.debug(
                "Hidden event kind=%s message_id=%s text=%r",
                event.kind.value,
                event.message_id,
                event.text[:1000],
            )
            return

        # 用户消息
        if event.kind == EventKind.USER_MESSAGE:
            self.sink.append_user_message(event.text)
            return

        # 流式增量
        if event.kind == EventKind.ASSISTANT_DELTA:
            sanitizer = self._stream(event.message_id)
            before = sanitizer.repaired_count
            safe_text = sanitizer.feed(event.text)
            self._record_repairs(before, sanitizer)
            if safe_text:
                self.sink.append_assistant_delta(event.message_id, safe_text)
            return

        # 最终回答
        if event.kind == EventKind.ASSISTANT_FINAL:
            # 用独立 sanitizer 处理 final（不消耗流式 pending）
            final_text = StreamingUnicodeSanitizer()
            safe_final = final_text.feed(event.text) + final_text.finish()
            self._record_repairs(0, final_text)

            # 清掉旧流的 pending 代理
            old = self._sanitizers.pop(event.message_id, None)
            if old and old._pending_high is not None:
                self.logger.debug("Dropped orphan high surrogate for %s", event.message_id)

            self.sink.finish_assistant_message(event.message_id, safe_final)
            self.sink.update_status("已完成")
            return

        # 工具事件 → 单行状态
        if event.kind in self.TOOL_EVENTS:
            tool = event.tool_name or "工具"
            if event.kind == EventKind.TOOL_STARTED or event.kind == EventKind.TOOL_PROGRESS:
                self.sink.update_status(event.text or f"正在执行：{tool}")
            elif event.kind == EventKind.TOOL_FINISHED:
                self.sink.update_status(f"已完成：{tool}")
            elif event.kind == EventKind.TOOL_FAILED:
                self.sink.show_notice(
                    event.text or f"{tool} 执行失败",
                    error=True,
                )
            return

        # 系统通知
        if event.kind == EventKind.SYSTEM_WARNING:
            self.sink.show_notice(event.text, error=False)
            return

        if event.kind == EventKind.SYSTEM_ERROR:
            self.sink.show_notice(event.text, error=True)
            return

        self.logger.debug("Ignored unknown event: %r", event)


# ═══════════════════════════════════════════════════════════
# TUI logging — 全屏模式下禁止写 stdout/stderr
# ═══════════════════════════════════════════════════════════

def configure_tui_logging(
    log_path: str | Path = "logs/crux-runtime.log",
) -> logging.Logger:
    """全屏 TUI 模式下，只允许写文件，禁止 StreamHandler 写终端。

    print() / stderr 会破坏 prompt_toolkit 的屏幕缓冲区，导致：
    - 输入框消失
    - 光标位置错误
    - 旧字符没有擦除
    - 局部区域不断向下滚动
    """
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()

    # 删除所有控制台 Handler
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
        errors="backslashreplace",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    )

    root.addHandler(file_handler)
    root.setLevel(logging.INFO)
    logging.captureWarnings(True)

    return root


# ═══════════════════════════════════════════════════════════
# 独立演示 (python ui/stream_guard.py)
# ═══════════════════════════════════════════════════════════

class _DemoSink:
    def append_user_message(self, text: str) -> None:
        print(f"USER: {text}")

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        print(f"DELTA[{message_id}]: {text}")

    def finish_assistant_message(self, message_id: str, text: str) -> None:
        print(f"FINAL[{message_id}]: {text}")

    def update_status(self, text: str) -> None:
        print(f"STATUS: {text}")

    def show_notice(self, text: str, *, error: bool = False) -> None:
        level = "ERROR" if error else "NOTICE"
        print(f"{level}: {text}")


if __name__ == "__main__":
    guard = UiStreamGuard(_DemoSink())

    # 1. 隐藏事件不进 UI
    guard.dispatch(UiEvent(EventKind.ANALYSIS, "Let me check the file..."))
    guard.dispatch(UiEvent(EventKind.DEBUG, "variable x = 42"))

    # 2. 流式 delta + Unicode 修复
    guard.dispatch(UiEvent(EventKind.ASSISTANT_DELTA, "Hello 🌍", message_id="m1"))
    guard.dispatch(UiEvent(EventKind.ASSISTANT_DELTA, " more text", message_id="m1"))
    guard.dispatch(UiEvent(EventKind.ASSISTANT_FINAL, "Hello world final", message_id="m1"))

    # 3. 工具状态
    guard.dispatch(UiEvent(EventKind.TOOL_STARTED, tool_name="run_python"))
    guard.dispatch(UiEvent(EventKind.TOOL_FINISHED, tool_name="run_python"))

    # 4. 代理对修复演示
    sanitizer = StreamingUnicodeSanitizer()
    # 模拟 emoji 被拆开：🙂 = U+D83D U+DE42
    high = chr(0xD83D)
    low = chr(0xDE42)
    chunk1 = sanitizer.feed("abc" + high)
    chunk2 = sanitizer.feed(low + "def")
    print(f"\n代理对修复: '{chunk1}' + '{chunk2}' → 'abc🙂def'")
    print(f"修复计数: {sanitizer.repaired_count}")
