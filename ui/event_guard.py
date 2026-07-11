"""
CRUX 事件通道隔离 + 流式 Unicode 清洗
======================================
唯一入口：所有模型输出、工具结果、系统事件必须经过 UiStreamGuard.dispatch() 才能进入 UI。

规则：
- reasoning/analysis/debug/internal_prompt/tool_raw_output → 仅日志文件
- tool_started/tool_finished → 合并为单行状态
- assistant_delta → 流式清洗（修复代理对 + 去噪）后进入聊天区
- assistant_final/user_message → 直接进入聊天区
- system_warning/system_error → 通知区
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

# ═══════════════════════════════════════════════════════════════
# Event taxonomy
# ═══════════════════════════════════════════════════════════════

class EventKind(str, Enum):
    """事件类型枚举"""
    # ── 可进入聊天区 ──
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # ── 工具状态（合并为单行） ──
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"

    # ── 系统通知（进入通知区） ──
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"

    # ── 内部事件（仅日志，不进入 UI） ──
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    TOOL_RAW_OUTPUT = "tool_raw_output"


@dataclass(slots=True)
class UiEvent:
    """统一 UI 事件"""
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""


# ═══════════════════════════════════════════════════════════════
# UI 接收端协议
# ═══════════════════════════════════════════════════════════════

class UiSink(Protocol):
    """UI 层必须实现的接口"""

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


# ═══════════════════════════════════════════════════════════════
# 流式 Unicode 清洗器（修复 UTF-16 代理对拆分）
# ═══════════════════════════════════════════════════════════════

class StreamingUnicodeSanitizer:
    """
    修复流式文本中被拆开的 UTF-16 代理对。

    触发场景：
    1. 使用 surrogatepass 解码
    2. 从 UTF-16 流按错误边界切块
    3. 浏览器/CDP/Node 桥接层把代理项单独传给 Python
    4. JSON 流被错误拆分

    高位代理 (U+D800-U+DBFF) 如果没有紧随低位代理 (U+DC00-U+DFFF)，
    则替换为 U+FFFD (REPLACEMENT CHARACTER)。
    """

    REPLACEMENT = "\uFFFD"

    def __init__(self) -> None:
        self._pending_high: str | None = None
        self.repaired_count: int = 0

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
        """喂入一块文本，返回清洗后的内容"""
        if not text:
            return ""

        output: list[str] = []
        for char in text:
            code = ord(char)

            # 上一个 chunk 留下了未配对的 high surrogate
            if self._pending_high is not None:
                high_code = ord(self._pending_high)
                if self._is_low_surrogate(code):
                    # 成功配对
                    output.append(self._join_surrogate_pair(high_code, code))
                    self._pending_high = None
                    continue
                # 孤立的 high surrogate，替换
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                self._pending_high = None
                # 继续处理当前字符

            if self._is_high_surrogate(code):
                self._pending_high = char
                continue

            if self._is_low_surrogate(code):
                # 孤立的 low surrogate
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                continue

            output.append(char)

        return "".join(output)

    def finish(self) -> str:
        """流结束：处理最后一个未配对的 high surrogate"""
        if self._pending_high is None:
            return ""
        self._pending_high = None
        self.repaired_count += 1
        return self.REPLACEMENT


# ═══════════════════════════════════════════════════════════════
# 事件守卫（唯一入口）
# ═══════════════════════════════════════════════════════════════

class UiStreamGuard:
    """
    CRUX 事件进入 UI 前的唯一入口。

    - 原始工具输出不进入聊天区
    - reasoning/analysis/debug 只进入日志文件
    - 流式文本按 message_id 清洗 Unicode
    - tool_started/tool_finished 合并为单行状态
    """

    HIDDEN_EVENTS = frozenset({
        EventKind.REASONING,
        EventKind.ANALYSIS,
        EventKind.INTERNAL_PROMPT,
        EventKind.DEBUG,
        EventKind.TOOL_RAW_OUTPUT,
    })

    def __init__(
        self,
        sink: UiSink,
        logger: logging.Logger | None = None,
    ) -> None:
        self.sink = sink
        self.logger = logger or logging.getLogger("crux.ui.guard")
        self._sanitizers: dict[str, StreamingUnicodeSanitizer] = {}
        self._last_surrogate_log: float = 0.0
        self._surrogate_total: int = 0
        self._tool_count: int = 0
        self._tool_start_time: float = 0.0

    def _get_sanitizer(self, message_id: str) -> StreamingUnicodeSanitizer:
        """获取或创建按 message_id 隔离的清洗器"""
        if message_id not in self._sanitizers:
            self._sanitizers[message_id] = StreamingUnicodeSanitizer()
        return self._sanitizers[message_id]

    def _record_repairs(self, before: int, sanitizer: StreamingUnicodeSanitizer) -> None:
        """记录修复次数，最多每30s写一次日志"""
        repaired = sanitizer.repaired_count - before
        if repaired <= 0:
            return
        self._surrogate_total += repaired
        now = time.monotonic()
        if now - self._last_surrogate_log >= 30:
            self.logger.warning(
                "Unicode surrogate repair: +%d this batch, %d total",
                repaired,
                self._surrogate_total,
            )
            self._last_surrogate_log = now

    def dispatch(self, event: UiEvent) -> None:
        """分发事件：隐藏/合并/清洗/入区"""

        # ── 隐藏事件：仅日志 ──
        if event.kind in self.HIDDEN_EVENTS:
            self.logger.debug(
                "Hidden event kind=%s message_id=%s text=%.1000r",
                event.kind.value,
                event.message_id,
                event.text,
            )
            return

        # ── 用户消息 ──
        if event.kind == EventKind.USER_MESSAGE:
            self.sink.append_user_message(event.text)
            return

        # ── 流式 delta：清洗后入区 ──
        if event.kind == EventKind.ASSISTANT_DELTA:
            sanitizer = self._get_sanitizer(event.message_id)
            before = sanitizer.repaired_count
            cleaned = sanitizer.feed(event.text)
            self._record_repairs(before, sanitizer)
            if cleaned:
                self.sink.append_assistant_delta(event.message_id, cleaned)
            return

        # ── 最终回答：冲洗残余 + 清洗 ──
        if event.kind == EventKind.ASSISTANT_FINAL:
            sanitizer = self._get_sanitizer(event.message_id)
            before = sanitizer.repaired_count
            # 先冲掉可能残留的 high surrogate
            remnant = sanitizer.finish()
            cleaned = sanitizer.feed(event.text)
            if remnant:
                cleaned = remnant + cleaned
            self._record_repairs(before, sanitizer)
            self.sink.append_assistant_final(event.message_id, cleaned)
            # 清理该 message_id 的清洗器
            self._sanitizers.pop(event.message_id, None)
            return

        # ── 工具状态：合并为单行 ──
        if event.kind == EventKind.TOOL_STARTED:
            self._tool_count += 1
            self._tool_start_time = time.time()
            self.sink.update_status(f"⏳ {event.tool_name or event.text[:60]}")
            return

        if event.kind in (EventKind.TOOL_FINISHED, EventKind.TOOL_FAILED):
            elapsed = time.time() - self._tool_start_time if self._tool_start_time else 0
            prefix = "✕" if event.kind == EventKind.TOOL_FAILED else "✓"
            self.sink.update_status(f"{prefix} 已完成 {self._tool_count} 个工具 · {elapsed:.0f}s")
            return

        # ── 系统通知 ──
        if event.kind == EventKind.SYSTEM_WARNING:
            self.sink.show_notice(event.text, error=False)
            return

        if event.kind == EventKind.SYSTEM_ERROR:
            self.sink.show_notice(event.text, error=True)
            return

        # ── 未知事件：安全降级为日志 ──
        self.logger.warning("Unknown event kind=%s dropped", event.kind.value)


# ═══════════════════════════════════════════════════════════════
# 后台线程 stdout/stderr 拦截器
# ═══════════════════════════════════════════════════════════════

class StdioInterceptor:
    """
    解决后台线程直接向 stdout/stderr 输出破坏 prompt_toolkit 屏幕缓冲的问题。

    用法（在 TUI 启动时）:
        with StdioInterceptor(logger=crux_logger):
            app.run()
    """

    def __init__(
        self,
        log_path: Path | str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._log_path = Path(log_path) if log_path else None
        self._logger = logger or logging.getLogger("crux.stdio")
        self._real_stdout_write = None
        self._real_stderr_write = None

    def _capture_stdout(self, text: str) -> int:
        """拦截 stdout.write，重定向到日志文件"""
        if text and text.strip():
            self._logger.info("stdout: %s", text.rstrip())
        return len(text)

    def _capture_stderr(self, text: str) -> int:
        """拦截 stderr.write，重定向到日志文件"""
        if text and text.strip():
            self._logger.warning("stderr: %s", text.rstrip())
        return len(text)

    def __enter__(self):
        import sys
        self._real_stdout_write = sys.stdout.write
        self._real_stderr_write = sys.stderr.write
        sys.stdout.write = self._capture_stdout  # type: ignore[assignment]
        sys.stderr.write = self._capture_stderr  # type: ignore[assignment]
        return self

    def __exit__(self, *args):
        import sys
        if self._real_stdout_write:
            sys.stdout.write = self._real_stdout_write
        if self._real_stderr_write:
            sys.stderr.write = self._real_stderr_write
