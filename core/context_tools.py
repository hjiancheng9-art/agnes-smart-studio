"""上下文窗口管理工具 —— 单条消息截断 + token 估算。

从 core/agent.py 的 ContextManager._truncate_messages / estimate_tokens 提取为
模块级纯函数，供 ChatSession / AsyncChatSession / ContextManager 共用。

截断策略（head+tail）：
    超过 max_chars 的文本保留头部 2/3 + 尾部 1/3，中间用省略标记：
    "<head>\n\n...[truncated N chars]...\n\n<tail>"
    确保关键信息（文件头部的 import/签名 + 尾部的错误/返回值）不丢。

token 估算（CJK 感知）：
    窄字符（ASCII/Latin）约 4 chars/token，宽字符（CJK/Kana/Hangul）约 2 chars/token。
    用 Unicode East Asian Width 判定，无需外部依赖。
"""

from __future__ import annotations

import unicodedata

__all__ = [
    "DEFAULT_MAX_CHARS",
    "estimate_tokens",
    "truncate_tool_result",
    "truncate_messages",
]

# 与 ContextManager._MAX_MSG_CHARS 保持一致（agent.py:179）
DEFAULT_MAX_CHARS = 8000

# 截断标记（与 ContextManager._truncate_messages 的格式逐字一致，保证行为兼容）
_TRUNCATED_MARKER = "\n\n...[truncated {n} chars]...\n\n"


def truncate_tool_result(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """截断超长工具结果，保留 head(2/3) + tail(1/3) + 中间省略标记。

    与 ContextManager._truncate_messages 单条消息的截断语义完全一致：
        head = max_chars * 2 // 3
        tail = max_chars - head
        result = text[:head] + 标记 + text[-tail:]

    Args:
        text: 原始工具结果文本
        max_chars: 字符上限（含标记后的总长度约等于 max_chars + 标记长度）

    Returns:
        截断后的文本；未超限则原样返回。
    """
    if not isinstance(text, str) or len(text) <= max_chars:
        return text
    head = max_chars * 2 // 3
    tail = max_chars - head
    return (
        text[:head]
        + _TRUNCATED_MARKER.format(n=len(text) - max_chars)
        + text[-tail:]
    )


def truncate_messages(
    messages: list[dict],
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict]:
    """对 messages 列表中单条 content 超限的消息应用截断。

    仅处理 role=tool / role=user / role=assistant 的 str content；
    multimodal（list content）不动。非超限消息原样保留（浅拷贝引用）。

    与 ContextManager._truncate_messages 行为一致：超限消息生成新 dict，
    未超限消息保留原引用（不强制深拷贝，避免无谓开销）。
    """
    out: list[dict] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str) and len(content) > max_chars:
            new_msg = dict(msg)
            new_msg["content"] = truncate_tool_result(content, max_chars)
            out.append(new_msg)
        else:
            out.append(msg)
    return out


def estimate_tokens(text: str) -> int:
    """估算文本 token 数（CJK 感知，无外部依赖）。

    启发式：窄字符 4 chars/token，宽字符 2 chars/token。
    用 Unicode East Asian Width 判定宽字符（'W' 全宽 / 'F' 半宽）。

    与 ContextManager.estimate_tokens 逻辑完全一致，提取为模块级函数后
    ContextManager 改为委托调用（保持向后兼容）。
    """
    if not text:
        return 0
    wide_count = sum(
        1 for c in text
        if unicodedata.east_asian_width(c) in ('W', 'F')
    )
    narrow_count = len(text) - wide_count
    return wide_count // 2 + narrow_count // 4 + 1
