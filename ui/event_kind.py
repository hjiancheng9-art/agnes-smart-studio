"""CRUX 事件类型枚举 — 所有进入 UI 的事件必须先归类。"""

from enum import Enum


class EventKind(str, Enum):
    """事件种类。值即为字符串标签，方便序列化。"""

    # ── 聊天正文（进入消息区）──
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"

    # ── 工具状态（合并为单行动态）──
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_PROGRESS = "tool_progress"
    TOOL_FAILED = "tool_failed"

    # ── 隐藏事件（只写日志，不进聊天区）──
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    INTERNAL_PROMPT = "internal_prompt"
    DEBUG = "debug"
    TOOL_RAW_OUTPUT = "tool_raw_output"

    # ── 系统通知（状态栏/弹窗）──
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"
    SYSTEM_INFO = "system_info"


# 快捷分类集合
CHAT_KINDS = frozenset({EventKind.USER_MESSAGE, EventKind.ASSISTANT_DELTA, EventKind.ASSISTANT_FINAL})
TOOL_KINDS = frozenset({EventKind.TOOL_STARTED, EventKind.TOOL_FINISHED, EventKind.TOOL_PROGRESS, EventKind.TOOL_FAILED})
HIDDEN_KINDS = frozenset({EventKind.REASONING, EventKind.ANALYSIS, EventKind.INTERNAL_PROMPT, EventKind.DEBUG, EventKind.TOOL_RAW_OUTPUT})
SYSTEM_KINDS = frozenset({EventKind.SYSTEM_WARNING, EventKind.SYSTEM_ERROR, EventKind.SYSTEM_INFO})
