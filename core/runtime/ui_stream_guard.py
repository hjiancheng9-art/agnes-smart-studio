"""UiStreamGuard — 事件进入 UI 前的唯一入口管道。

职责：
- 事件按类型分类：聊天内容 / 工具状态 / 隐藏事件
- 流式 Unicode 代理对修复（跨分片）
- 工具信息合并为单行动态状态栏
- 最终回答替换流式气泡

依赖：仅 Python 标准库。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

# ── 事件类型枚举 ─────────────────────────────────────────────

class EventKind(str, Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    TOOL_RAW_OUTPUT = "tool_raw_output"
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"
    SYSTEM_INFO = "system_info"
    WATCHDOG_WARNING = "watchdog_warning"
    PROVIDER_FALLBACK = "provider_fallback"
    CONNECTION_ERROR = "connection_error"


# ── 事件数据结构 ─────────────────────────────────────────────

@dataclass(slots=True)
class UiEvent:
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""


# ── UI 接收端接口 ────────────────────────────────────────────

class UiSink(Protocol):
    """UI 端实现的回调接口，UiStreamGuard 通过它写入最终内容。"""

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


# ── 流式 Unicode 代理对修复器 ───────────────────────────────

class StreamingUnicodeSanitizer:
    """
    修复流式文本中被拆开的 UTF-16 代理对。

    流式场景中，一个 emoji（如 🎉 = U+1F389）在 UTF-16 中被编码为
    \uD83C\uDF89 两个代理项。如果它们被分到两个流式分片里，
    逐块 replace 会把它们都变成 �。

    此修复器：
    - 暂存末尾的高位代理
    - 检测后一块的开头是否为低位代理 → 拼接
    - 孤立代理 → 替换为 U+FFFD
    """

    REPLACEMENT = "\uFFFD"

    def __init__(self) -> None:
        self._pending_high: str | None = None
        self.repaired_count: int = 0

    # ── 代理判断 ─────────────────────────────────────────────

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

    # ── 主入口 ───────────────────────────────────────────────

    def feed(self, text: str | None) -> str:
        """送入一个文本块，返回修复后的字符串。"""
        if not text:
            return ""

        output: list[str] = []
        for char in text:
            code = ord(char)

            # 处理上一个高位代理
            if self._pending_high is not None:
                high_code = ord(self._pending_high)
                if self._is_low_surrogate(code):
                    # 配对成功
                    output.append(self._join_surrogate_pair(high_code, code))
                    self._pending_high = None
                    continue
                # 上一个高位没有后续低位
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                self._pending_high = None

            if self._is_high_surrogate(code):
                self._pending_high = char
                continue

            if self._is_low_surrogate(code):
                # 孤儿低位代理
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                continue

            output.append(char)

        return "".join(output)

    def finish(self) -> str:
        """清空末尾暂存的高位代理（流结束）。"""
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
    - reasoning/analysis/debug/internal_prompt → 只写日志
    - tool_* → 只更新状态栏单行
    - user_message / assistant_delta / assistant_final → 进入聊天区
    - Unicode 代理对按 message_id 跨分片修复
    - 流式最终定稿清理残留代理
    """

    # 绝不进入聊天区的事件
    HIDDEN_EVENTS = frozenset({
        EventKind.REASONING,
        EventKind.ANALYSIS,
        EventKind.INTERNAL_PROMPT,
        EventKind.DEBUG,
        EventKind.TOOL_RAW_OUTPUT,
    })

    # 只更新状态栏的事件
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
        self._last_surrogate_log: float = 0.0
        self._surrogate_total: int = 0

    def _get_sanitizer(self, message_id: str) -> StreamingUnicodeSanitizer:
        """获取或创建按 message_id 隔离的流式清洗器。"""
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
        # 最多每 30 秒写一次警告日志，绝不发送 UI 事件。
        if now - self._last_surrogate_log >= 30:
            self.logger.warning(
                "Repaired %d invalid surrogate pairs; total=%d",
                repaired,
                self._surrogate_total,
            )
            self._last_surrogate_log = now

    # ── 主派发入口 ──────────────────────────────────────────

    def dispatch(self, event: UiEvent) -> None:
        """接收一个 UI 事件，按类型路由到 sink 或日志。"""
        # ── 隐藏事件：直接丢弃（仅日志） ──
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

        # ── 流式增量 ──
        if event.kind == EventKind.ASSISTANT_DELTA:
            sanitizer = self._get_sanitizer(event.message_id)
            before = sanitizer.repaired_count
            safe_text = sanitizer.feed(event.text)
            self._record_repairs(before, sanitizer)
            if safe_text:
                self.sink.append_assistant_delta(
                    event.message_id,
                    safe_text,
                )
            return

        # ── 流式最终定稿 ──
        if event.kind == EventKind.ASSISTANT_FINAL:
            sanitizer = self._sanitizers.pop(
                event.message_id,
                StreamingUnicodeSanitizer(),
            )
            before = sanitizer.repaired_count
            safe_final = sanitizer.feed(event.text) + sanitizer.finish()
            self._record_repairs(before, sanitizer)

            # final 文本中也可能再有残留的孤立代理
            final_cleaner = StreamingUnicodeSanitizer()
            safe_final = final_cleaner.feed(safe_final) + final_cleaner.finish()
            self._record_repairs(0, final_cleaner)

            self.sink.finish_assistant_message(
                event.message_id,
                safe_final,
            )
            self.sink.update_status("已完成")
            return

        # ── 工具事件 → 单行状态栏 ──
        if event.kind in self.TOOL_EVENTS:
            self._handle_tool_event(event)
            return

        # ── 系统通知 ──
        if event.kind == EventKind.SYSTEM_WARNING:
            self.sink.show_notice(event.text, error=False)
            return

        if event.kind == EventKind.SYSTEM_ERROR:
            self.sink.show_notice(event.text, error=True)
            return

        # ── 未知事件 ──
        self.logger.debug("Ignored unknown event: kind=%s", event.kind.value)

    def _handle_tool_event(self, event: UiEvent) -> None:
        """工具事件合并为单行动态状态。"""
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


# ── TUI 日志配置 ────────────────────────────────────────────

def configure_tui_logging(
    log_path: str | Path = "logs/crux-runtime.log",
    level: int = logging.INFO,
) -> None:
    """
    全屏 TUI 模式下只允许写文件，禁止 StreamHandler 写终端。

    任何绕过此配置的 print/stderr 输出都会破坏 prompt_toolkit
    的屏幕缓冲区，导致状态栏、输入框和聊天区相互覆盖。
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

    # 添加滚动文件 Handler
    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
        ),
    )
    file_handler.setLevel(level)
    root.addHandler(file_handler)
    root.setLevel(level)

    # 捕获 warnings 模块到日志
    logging.captureWarnings(True)


# ── 独立运行演示 ────────────────────────────────────────────

class DemoSink:
    """演示用接收端：直接打印到终端。"""

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


if __name__ == "__main__":
    import logging

    configure_tui_logging("logs/demo.log")

    sink = DemoSink()
    guard = UiStreamGuard(sink)

    # 模拟 emoji 被拆成两个分片
    guard.dispatch(UiEvent(
        kind=EventKind.ASSISTANT_DELTA,
        text="结果：\ud83d",
        message_id="msg-1",
    ))
    guard.dispatch(UiEvent(
        kind=EventKind.ASSISTANT_DELTA,
        text="\ude89 是完成标志",
        message_id="msg-1",
    ))

    # 模拟分析事件（应被隐藏）
    guard.dispatch(UiEvent(
        kind=EventKind.REASONING,
        text="I need to check the file...",
        message_id="msg-1",
    ))

    # 模拟工具事件
    guard.dispatch(UiEvent(
        kind=EventKind.TOOL_STARTED,
        tool_name="run_python",
        text="执行 Python 脚本",
    ))

    guard.dispatch(UiEvent(
        kind=EventKind.ASSISTANT_FINAL,
        text="分析完毕，\ud83d\udc4d 一切正常。",
        message_id="msg-1",
    ))

    print("\n✅ 演示完成")
    print(f"修复代理对次数：{sum(s.repaired_count for s in guard._sanitizers.values())}")
