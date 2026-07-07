"""
CRUX TUI v2 — Message Prefix System
====================================
Color-blind accessible message type prefixes per debate conclusion.
Each message type gets a unique text prefix + symbol, not relying on color alone.

Prefixes:
    [U]  User message        (虎 / Tiger / #f2cdcd)
    [A]  Assistant reply     (龙 / Dragon / #89b4fa)
    [S]  System notification (雀 / Phoenix / #fab387)
    [E]  Error               (翼 / Wing / #f5c2e7)
    [✓]  Success             (武 / Warrior / #a6e3a1)
    [T]  Thinking chain      (麟 / Qilin / #cba6f7)
    [·]  Info / timestamp    (蛇 / Snake / #94e2d5)
"""

from enum import Enum
from typing import NamedTuple


class MsgType(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    ERROR = "error"
    SUCCESS = "success"
    THINKING = "thinking"
    INFO = "info"


class MsgPrefix(NamedTuple):
    """Visual prefix for a message type."""
    symbol: str          # Single char symbol
    label: str           # One-char prefix label
    short: str           # 2-char abbreviation
    style_class: str     # CSS-like class for theming
    description: str     # Human-readable description


# ── Prefix definitions ────────────────────────────────────

PREFIX_MAP: dict[MsgType, MsgPrefix] = {
    MsgType.USER: MsgPrefix(
        symbol="▸",
        label="U",
        short="[U]",
        style_class="msg-user",
        description="用户消息",
    ),
    MsgType.ASSISTANT: MsgPrefix(
        symbol="◆",
        label="A",
        short="[A]",
        style_class="msg-assistant",
        description="AI 回复",
    ),
    MsgType.SYSTEM: MsgPrefix(
        symbol="⚙",
        label="S",
        short="[S]",
        style_class="msg-system",
        description="系统通知",
    ),
    MsgType.ERROR: MsgPrefix(
        symbol="✕",
        label="E",
        short="[E]",
        style_class="msg-error",
        description="错误",
    ),
    MsgType.SUCCESS: MsgPrefix(
        symbol="✓",
        label="✓",
        short="[✓]",
        style_class="msg-success",
        description="成功",
    ),
    MsgType.THINKING: MsgPrefix(
        symbol="…",
        label="T",
        short="[T]",
        style_class="msg-thinking",
        description="推理过程",
    ),
    MsgType.INFO: MsgPrefix(
        symbol="·",
        label="·",
        short="[·]",
        style_class="msg-info",
        description="信息",
    ),
}


def get_prefix(msg_type: str, mode: str = "compact") -> str:
    """
    Get prefix for message type.

    Args:
        msg_type: Message type string ('user', 'assistant', etc.)
        mode: 'symbol' | 'label' | 'compact' | 'full' | 'accessible'

    Returns:
        Prefix string
    """
    try:
        msgt = MsgType(msg_type)
    except ValueError:
        return ""

    prefix = PREFIX_MAP.get(msgt)
    if prefix is None:
        return ""

    if mode == "symbol":
        return f" {prefix.symbol} "
    elif mode == "label":
        return f"[{prefix.label}] "
    elif mode == "compact":
        return f"{prefix.short} "
    elif mode == "full":
        return f"{prefix.short} {prefix.description} "
    elif mode == "accessible":
        return f"[{prefix.label}] "  # same as label, designed for screen readers
    else:
        return f"{prefix.short} "


def get_prefix_style_class(msg_type: str) -> str:
    """Get the CSS-like style class for a message type prefix."""
    try:
        msgt = MsgType(msg_type)
    except ValueError:
        return ""

    prefix = PREFIX_MAP.get(msgt)
    return prefix.style_class if prefix else ""


# ── Color mapping for prefix styles (prompt_toolkit style strings) ──

PREFIX_STYLES = {
    "msg-user": "fg:#f2cdcd bold",       # 虎 - rose
    "msg-assistant": "fg:#89b4fa bold",   # 龙 - blue
    "msg-system": "fg:#fab387",           # 雀 - peach
    "msg-error": "fg:#f5c2e7 bold",       # 翼 - pink
    "msg-success": "fg:#a6e3a1",          # 武 - green
    "msg-thinking": "fg:#cba6f7 italic",  # 麟 - mauve
    "msg-info": "fg:#94e2d5",             # 蛇 - teal
}
