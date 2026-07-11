"""CRUX UI Stream Guard — 事件进入 UI 前的唯一入口。

规则：
- 原始工具输出/内部分析/推理只进入日志文件
- 流式回答进入聊天区（含代理对修复）
- 工具状态只更新一行状态栏
- 禁止任何日志直接写入 stdout/stderr（保护全屏 TUI）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

# ── Event kinds ────────────────────────────────────────────

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


# ── Data ────────────────────────────────────────────────────

@dataclass(slots=True)
class UiEvent:
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""


# ── Sink protocol ───────────────────────────────────────────

class UiSink(Protocol):
    def append_user_message(self, text: str) -> None: ...
    def append_assistant_delta(self, message_id: str, text: str) -> None: ...
    def finish_assistant_message(self, message_id: str, text: str) -> None: ...
    def update_status(self, text: str) -> None: ...
    def show_notice(self, text: str, *, error: bool = False) -> None: ...


# ── Streaming Unicode Sanitizer ─────────────────────────────

class StreamingUnicodeSanitizer:
    """修复流式文本中被拆开的 UTF-16 代理对。

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
                        self._join_surrogate_pair(
                            ord(self._pending_high), code
                        )
                    )
                    self._pending_high = None
                    continue
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
        self._pending_high = None
        self.repaired_count += 1
        return self.REPLACEMENT


# ── Stream Guard ────────────────────────────────────────────

class UiStreamGuard:
    """CRUX 事件进入 UI 前的唯一入口。

    规则：
    - reasoning/analysis/debug 只进入日志文件
    - 工具信息只更新一行状态栏
    - 最终回答和流式回答进入聊天区（含代理对修复）
    - 系统告警写入通知区
    """

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
        if now - self._last_surrogate_log >= 30:
            self.logger.warning(
                "Repaired invalid Unicode surrogate data; total=%d",
                self._surrogate_total,
            )
            self._last_surrogate_log = now

    def dispatch(self, event: UiEvent) -> None:
        """将 UI 事件路由到正确的通道。"""

        # ── 隐藏事件 → 仅日志 ──
        if event.kind in self.HIDDEN_EVENTS:
            self.logger.debug(
                "Hidden event kind=%s message_id=%s text=%r",
                event.kind.value,
                event.message_id,
                event.text[:1000],
            )
            return

        # ── 用户消息 ──
        if event.kind == EventKind.USER_MESSAGE:
            self.sink.append_user_message(event.text)
            return

        # ── 流式回答 ──
        if event.kind == EventKind.ASSISTANT_DELTA:
            sanitizer = self._stream(event.message_id)
            before = sanitizer.repaired_count
            safe_text = sanitizer.feed(event.text)
            self._record_repairs(before, sanitizer)
            if safe_text:
                self.sink.append_assistant_delta(
                    event.message_id,
                    safe_text,
                )
            return

        # ── 最终回答 ──
        if event.kind == EventKind.ASSISTANT_FINAL:
            sanitizer = self._sanitizers.pop(
                event.message_id,
                StreamingUnicodeSanitizer(),
            )
            before = sanitizer.repaired_count
            final_text = StreamingUnicodeSanitizer()
            safe_final = final_text.feed(event.text) + final_text.finish()
            self._record_repairs(before, sanitizer)
            self._record_repairs(0, final_text)
            self.sink.finish_assistant_message(
                event.message_id,
                safe_final,
            )
            self.sink.update_status("已完成")
            return

        # ── 工具事件 → 单行状态 ──
        if event.kind in self.TOOL_EVENTS:
            tool = event.tool_name or "工具"
            if event.kind == EventKind.TOOL_STARTED:
                self.sink.update_status(event.text or f"正在执行：{tool}")
            elif event.kind == EventKind.TOOL_PROGRESS:
                self.sink.update_status(event.text or f"执行中：{tool}")
            elif event.kind == EventKind.TOOL_FINISHED:
                self.sink.update_status(f"已完成：{tool}")
            elif event.kind == EventKind.TOOL_FAILED:
                self.sink.show_notice(
                    event.text or f"{tool} 执行失败",
                    error=True,
                )
            return

        # ── 系统事件 ──
        if event.kind == EventKind.SYSTEM_WARNING:
            self.sink.show_notice(event.text, error=False)
            return

        if event.kind == EventKind.SYSTEM_ERROR:
            self.sink.show_notice(event.text, error=True)
            return

        self.logger.debug("Ignored unknown event: %r", event)


# ── TUI-safe logging ────────────────────────────────────────

def configure_tui_logging(
    log_path: str | Path = "logs/crux-runtime.log",
) -> logging.Logger:
    """全屏 TUI 模式下，只允许写文件，禁止 StreamHandler 写终端。"""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 删除所有控制台 Handler
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler):
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
    logging.captureWarnings(True)

    return logging.getLogger("crux")


# ── Demo ────────────────────────────────────────────────────

if __name__ == "__main__":
    class DemoSink:
        def append_user_message(self, text: str) -> None:
            print(f"USER: {text}")

        def append_assistant_delta(
            self, message_id: str, text: str
        ) -> None:
            print(f"DELTA[{message_id}]: {text!r}")

        def finish_assistant_message(
            self, message_id: str, text: str
        ) -> None:
            print(f"FINAL[{message_id}]: {text}")

        def update_status(self, text: str) -> None:
            print(f"STATUS: {text}")

        def show_notice(
            self, text: str, *, error: bool = False
        ) -> None:
            print(f"{'ERROR' if error else 'NOTICE'}: {text}")

    sink = DemoSink()
    guard = UiStreamGuard(sink)
    configure_tui_logging("logs/demo.log")

    # 模拟 emoji 被拆成两个代理项
    guard.dispatch(UiEvent(EventKind.ASSISTANT_DELTA, "结果：\ud83d", "msg-1"))
    guard.dispatch(UiEvent(EventKind.ASSISTANT_DELTA, "\ude80 已完成", "msg-1"))
    # 内部推理 → 不能显示
    guard.dispatch(UiEvent(EventKind.REASONING, "I need to check source.", "msg-1"))
    guard.dispatch(UiEvent(EventKind.ASSISTANT_FINAL, "结果：🚀 已完成", "msg-1"))

    print("\n✅ Demo complete — check logs/demo.log for hidden events")
