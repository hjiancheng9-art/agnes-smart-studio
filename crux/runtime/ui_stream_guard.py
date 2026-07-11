"""UiStreamGuard — CRUX 事件进入 UI 前的唯一入口。

职责：
1. 事件路由：按 kind 分发到聊天区/状态栏/通知/日志
2. 流式 Unicode 清洗：修复被流式分片拆开的 UTF-16 代理对
3. 日志隔离：全屏 TUI 模式下只写文件，不破坏 prompt_toolkit 屏幕缓冲区
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

# ── 事件类型 ─────────────────────────────────────────────────


class EventKind(str, Enum):
    """CRUX 内部所有事件类型，按展示位置分组。"""

    # ── 聊天区 ──
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # ── 状态栏（单行动态） ──
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"

    # ── 通知（短暂弹出） ──
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"

    # ── 仅日志（不进入 UI） ──
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    TOOL_RAW_OUTPUT = "tool_raw_output"

    # ── 状态更新（非聊天） ──
    STATUS = "status"


# ── 事件载荷 ─────────────────────────────────────────────────


@dataclass(slots=True)
class UiEvent:
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""


# ── UI 回调接口 ─────────────────────────────────────────────


class UiSink(Protocol):
    """后端与前端 TUI 的契约接口。"""

    def append_user_message(self, text: str) -> None:
        ...

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        ...

    def finish_assistant_message(self, message_id: str, text: str) -> None:
        ...

    def update_status(self, text: str) -> None:
        ...

    def show_notice(self, text: str, *, error: bool = False) -> None:
        ...


# ── 流式 Unicode 代理对修复 ─────────────────────────────────


class StreamingUnicodeSanitizer:
    """
    修复流式文本中被拆开的 UTF-16 代理对。

    Python 正常 Unicode 字符通常不包含代理字符，但以下情况可能产生：
    1. 使用 surrogatepass 解码；
    2. 从 UTF-16 流按错误边界切块；
    3. 浏览器/CDP/Node 桥接层把代理项单独传给 Python；
    4. JSON 流被错误拆分。

    不能对每个 chunk 简单执行：
        text.encode("utf-8", errors="replace").decode("utf-8")
    因为一个代理对可能被拆成：
        chunk 1: 高位代理  (如 \\ud83d)
        chunk 2: 低位代理  (如 \\ude80)
    逐块替换会把合法的 emoji 变成 �。
    """

    REPLACEMENT = "\uFFFD"

    def __init__(self) -> None:
        self._pending_high: str | None = None
        self.repaired_count = 0

    # ── 代理判断 ──

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

    # ── 主入口 ──

    def feed(self, text: str | None) -> str:
        """处理一段流式文本，返回清洗后的安全字符串。"""
        if not text:
            return ""

        output: list[str] = []

        for char in text:
            code = ord(char)

            # 处理上一块残留的高位代理
            if self._pending_high is not None:
                high_code = ord(self._pending_high)
                if self._is_low_surrogate(code):
                    # 配对成功
                    output.append(self._join_surrogate_pair(high_code, code))
                    self._pending_high = None
                    continue
                # 上一个高位代理没有遇到低位代理 → 替换
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                self._pending_high = None

            # 当前字符是高位代理 → 暂存
            if self._is_high_surrogate(code):
                self._pending_high = char
                continue

            # 孤立的低位代理 → 替换
            if self._is_low_surrogate(code):
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                continue

            output.append(char)

        return "".join(output)

    def finish(self) -> str:
        """清空残留的高位代理（流结束时的最后一块）。"""
        if self._pending_high is None:
            return ""
        self.repaired_count += 1
        self._pending_high = None
        return self.REPLACEMENT


# ── 事件路由守卫 ────────────────────────────────────────────


class UiStreamGuard:
    """
    CRUX 事件进入 UI 前的唯一入口。

    规则：
    - 原始工具输出不进入聊天区；
    - reasoning/analysis/debug 只进入日志文件；
    - 工具信息只更新一行状态栏；
    - 最终回答和流式回答进入聊天区；
    - Unicode 清洗按 message_id 保存流式状态。
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

        # message_id → StreamingUnicodeSanitizer
        self._sanitizers: dict[str, StreamingUnicodeSanitizer] = {}

        # 代理对修复统计
        self._last_surrogate_log = 0.0
        self._surrogate_total = 0

    # ── 内部工具 ──

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
        """记录代理对修复次数（仅写日志，不触发 UI 事件）。"""
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

    # ── 主入口 ──

    def dispatch(self, event: UiEvent) -> None:
        """事件分派：根据 kind 路由到正确的位置。"""

        # ── 完全隐藏的事件 ──
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
            safe_final = sanitizer.feed(event.text) + sanitizer.finish()
            self._record_repairs(before, sanitizer)
            self.sink.finish_assistant_message(
                event.message_id,
                safe_final,
            )
            self.sink.update_status("已完成")
            return

        # ── 工具事件 ──
        if event.kind in self.TOOL_EVENTS:
            tool = event.tool_name or "工具"
            if event.kind == EventKind.TOOL_STARTED:
                self.sink.update_status(
                    event.text or f"正在执行：{tool}",
                )
            elif event.kind == EventKind.TOOL_PROGRESS:
                self.sink.update_status(
                    event.text or f"执行中：{tool}",
                )
            elif event.kind == EventKind.TOOL_FINISHED:
                self.sink.update_status(
                    event.text or f"已完成：{tool}",
                )
            elif event.kind == EventKind.TOOL_FAILED:
                self.sink.show_notice(
                    event.text or f"{tool} 执行失败",
                    error=True,
                )
            return

        # ── 系统通知 ──
        if event.kind == EventKind.SYSTEM_WARNING:
            self.sink.show_notice(event.text, error=False)
            return

        if event.kind == EventKind.SYSTEM_ERROR:
            self.sink.show_notice(event.text, error=True)
            return

        # ── 未知事件 ──
        self.logger.debug("Ignored unknown event: %r", event)


# ── TUI 日志配置 ────────────────────────────────────────────


def configure_tui_logging(
    log_path: str | Path = "logs/crux-runtime.log",
) -> logging.Logger:
    """
    全屏 TUI 模式下，只允许写文件，禁止 StreamHandler 写终端。

    任何绕过 renderer 的终端输出都会破坏 prompt_toolkit 的全屏缓冲区，
    产生：光标错位、输入框消失、旧字符残留、布局跳跃。
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

    # 只保留文件 Handler
    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
        errors="backslashreplace",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
        ),
    )
    file_handler.setLevel(logging.INFO)

    root.addHandler(file_handler)
    root.setLevel(logging.INFO)

    # 捕获 warnings 模块的输出
    logging.captureWarnings(True)

    return root.getLogger("crux.runtime")


# ── 演示入口 ────────────────────────────────────────────────


class DemoSink:
    """命令行演示用的 UI 回调实现。"""

    def append_user_message(self, text: str) -> None:
        print(f"USER: {text}")

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        print(f"DELTA[{message_id}]: {text!r}")

    def finish_assistant_message(self, message_id: str, text: str) -> None:
        print(f"FINAL[{message_id}]: {text}")

    def update_status(self, text: str) -> None:
        print(f"STATUS: {text}")

    def show_notice(self, text: str, *, error: bool = False) -> None:
        print(f"{'ERROR' if error else 'NOTICE'}: {text}")


def demo() -> None:
    """演示流式代理对修复 + 事件路由。"""
    sink = DemoSink()
    guard = UiStreamGuard(sink)  # type: ignore[arg-type]
    configure_tui_logging("logs/demo.log")

    guard.dispatch(
        UiEvent(
            EventKind.ASSISTANT_DELTA,
            # 模拟一个 emoji 🚀 被拆成两个代理项
            "结果：\ud83d",
            "message-1",
        ),
    )

    guard.dispatch(
        UiEvent(
            EventKind.ASSISTANT_DELTA,
            "\ude80 已完成",
            "message-1",
        ),
    )

    # 这条内容不会显示到聊天区
    guard.dispatch(
        UiEvent(
            EventKind.REASONING,
            "I need inspect the source code first.",
            "message-1",
        ),
    )

    guard.dispatch(
        UiEvent(
            EventKind.ASSISTANT_FINAL,
            "结果：🚀 已完成",
            "message-1",
        ),
    )


if __name__ == "__main__":
    demo()
