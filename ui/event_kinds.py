"""Typed event kinds for CRUX UI channel isolation.

P0 事件通道隔离的核心类型系统。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class EventKind(str, Enum):
    """事件类型 — 决定消息出现在哪个 UI 区域。"""

    # ── 可见聊天事件 ──
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # ── 隐藏的内部事件（不进聊天区，仅日志）──
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    TOOL_RAW_OUTPUT = "tool_raw_output"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"

    # ── 工具事件（合并为单行动态状态）──
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"

    # ── 系统事件（通知栏）──
    WATCHDOG_WARNING = "watchdog_warning"
    PROVIDER_FALLBACK = "provider_fallback"
    CONNECTION_ERROR = "connection_error"
    NOTICE = "notice"


# ── 角色名 → EventKind 映射（向前兼容 message_pane.append_message）──
ROLE_TO_EVENTKIND: dict[str, EventKind] = {
    "user": EventKind.USER_MESSAGE,
    "assistant": EventKind.ASSISTANT_FINAL,
    "assistant_delta": EventKind.ASSISTANT_DELTA,
    "assistant_final": EventKind.ASSISTANT_FINAL,
    "analysis": EventKind.ANALYSIS,
    "reasoning": EventKind.REASONING,
    "debug": EventKind.DEBUG,
    "internal_prompt": EventKind.INTERNAL_PROMPT,
    "tool_raw_output": EventKind.TOOL_RAW_OUTPUT,
    "tool_started": EventKind.TOOL_STARTED,
    "tool_finished": EventKind.TOOL_FINISHED,
    "tool_progress": EventKind.TOOL_PROGRESS,
    "tool_failed": EventKind.TOOL_FAILED,
    "watchdog_warning": EventKind.WATCHDOG_WARNING,
    "connection_error": EventKind.CONNECTION_ERROR,
    "info": EventKind.NOTICE,
    "error": EventKind.SYSTEM_ERROR,
}

# ── 可见白名单 ──
VISIBLE_CHAT_KINDS = frozenset({
    EventKind.USER_MESSAGE,
    EventKind.ASSISTANT_DELTA,
    EventKind.ASSISTANT_FINAL,
    EventKind.NOTICE,
})

# ── 隐藏（仅日志）──
HIDDEN_KINDS = frozenset({
    EventKind.REASONING,
    EventKind.ANALYSIS,
    EventKind.INTERNAL_PROMPT,
    EventKind.DEBUG,
    EventKind.TOOL_RAW_OUTPUT,
})

# ── 工具状态（合并为单行）──
TOOL_STATUS_KINDS = frozenset({
    EventKind.TOOL_STARTED,
    EventKind.TOOL_PROGRESS,
    EventKind.TOOL_FINISHED,
    EventKind.TOOL_FAILED,
})

# ── 系统告警（通知栏）──
SYSTEM_ALERT_KINDS = frozenset({
    EventKind.WATCHDOG_WARNING,
    EventKind.PROVIDER_FALLBACK,
    EventKind.CONNECTION_ERROR,
    EventKind.SYSTEM_ERROR,
    EventKind.SYSTEM_WARNING,
})


@dataclass(slots=True)
class UiEvent:
    """类型化的 UI 事件。"""
    kind: EventKind
    text: str = ""
    message_id: str = "default"
    tool_name: str = ""


class UiSink(Protocol):
    """UI 输出接口 — 各角色只需调用这些方法，不直接操作缓冲区。"""

    def append_user_message(self, text: str) -> None:
        ...

    def append_assistant_delta(self, message_id: str, text: str) -> None:
        ...

    def update_status(self, text: str) -> None:
        """更新单行动态状态行（工具进度等）。"""
        ...

    def show_notice(self, text: str, *, error: bool = False) -> None:
        """显示通知（错误/警告等）。"""
        ...


def kind_from_role(role: str) -> EventKind:
    """角色名 → EventKind 转换，未知 role 归为 DEBUG。"""
    return ROLE_TO_EVENTKIND.get(role, EventKind.DEBUG)
