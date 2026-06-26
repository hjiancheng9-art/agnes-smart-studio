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

import math
import re
import unicodedata
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

__all__ = [
    "DEFAULT_MAX_CHARS",
    "abstractive_compress",
    "compress_tool_result",
    "estimate_tokens",
    "extractive_compress",
    "truncate_messages",
    "truncate_tool_result",
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
    return text[:head] + _TRUNCATED_MARKER.format(n=len(text) - max_chars) + text[-tail:]


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
    wide_count = sum(1 for c in text if unicodedata.east_asian_width(c) in ("W", "F"))
    narrow_count = len(text) - wide_count
    return wide_count // 2 + narrow_count // 4 + 1


# ======================================================================
# Tier 2: 语义压缩（#3 — 上下文窗口管理增强）
# ======================================================================

# 复用 rag.py:36 的 _tokenize 正则模式作为独立函数（rag.RAGEngine 是有状态实例）
_TOKENIZE_RE = re.compile(r"[a-zA-Z_]\w+|[\u4e00-\u9fff]+")


def _tokenize_text(text: str) -> list[str]:
    """将文本拆分为有意义的 token 列表（与 rag.RAGEngine._tokenize 同构）。

    匹配 ASCII 标识符（≥2字符）和 CJK 字符序列，统一小写。
    """
    return [t for t in _TOKENIZE_RE.findall(text.lower()) if len(t) >= 2]


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """计算两个稀疏向量的余弦相似度（与 rag.RAGEngine._cosine_similarity 同构）。

    向量为 {term: weight} 形式的稀疏字典。
    """
    all_keys = set(vec_a) | set(vec_b)
    dot = sum(vec_a.get(k, 0) * vec_b.get(k, 0) for k in all_keys)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _split_sentences(text: str) -> list[str]:
    """按句子边界切分文本（中英文标点 + 换行符）。

    每个片段保留原始文本顺序和内容。
    """
    # 按句子结束符切分，保留分隔符
    parts = re.split(r"(?<=[.!?。！？\n])\s*", text)
    # 过滤空片段
    return [p.strip() for p in parts if p.strip()]


def extractive_compress(
    text: str,
    query_hint: str = "",
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """零 LLM 成本的抽取式压缩：TF-IDF 打分取 top-N 句子。

    策略：
    1. 按句子切分
    2. 每句做 TF 向量
    3. 若有 query_hint，按 cosine similarity 排序；否则按 TF 权重排序
    4. 取 top-N 句子直到累积 ≤ max_chars，按原文顺序重组

    Args:
        text: 原始工具结果文本
        query_hint: 可选查询提示，用于相关性排序
        max_chars: 压缩后最大字符数

    Returns:
        压缩后的文本；短文本或失败时回退 truncate_tool_result。
    """
    if not isinstance(text, str) or len(text) <= max_chars:
        return text

    try:
        sentences = _split_sentences(text)
        if len(sentences) <= 1:
            # 单句无法抽取，回退截断
            return truncate_tool_result(text, max_chars)

        # 计算每句 TF 向量
        sent_data: list[tuple[int, str, dict[str, float]]] = []
        for i, sent in enumerate(sentences):
            tokens = _tokenize_text(sent)
            if not tokens:
                continue
            tf = Counter(tokens)
            total = max(len(tf), 1)
            vec = {term: count / total for term, count in tf.items()}
            sent_data.append((i, sent, vec))

        if not sent_data:
            return truncate_tool_result(text, max_chars)

        # 排序：有 query_hint 用 cosine similarity，否则用 TF 总权重
        if query_hint:
            query_tokens = _tokenize_text(query_hint)
            query_vec: dict[str, float] = {}
            if query_tokens:
                qtf = Counter(query_tokens)
                qtotal = max(len(qtf), 1)
                query_vec = {t: c / qtotal for t, c in qtf.items()}
            # 按 cosine similarity 降序
            scored = []
            for i, sent, vec in sent_data:
                score = _cosine_similarity(query_vec, vec) if query_vec else sum(vec.values())
                scored.append((i, sent, score))
        else:
            # 按 TF 总权重降序
            scored = [(i, sent, sum(vec.values())) for i, sent, vec in sent_data]

        scored.sort(key=lambda x: x[2], reverse=True)

        # 贪心选取：按得分从高到低，累积字符直到 ≤ max_chars
        selected_indices = set()
        total_chars = 0
        for i, sent, _score in scored:
            cost = len(sent) + 1  # +1 为可能的空格/换行
            if total_chars + cost > max_chars:
                continue
            selected_indices.add(i)
            total_chars += cost

        if not selected_indices:
            return truncate_tool_result(text, max_chars)

        # 按原文顺序重组
        result_parts = [sentences[i] for i in sorted(selected_indices)]
        return " ".join(result_parts)

    except (RuntimeError, ValueError, TypeError) as e:
        # 失败回退截断，但记录异常类型以便排查
        import logging

        _log = logging.getLogger("crux.context")
        _log.warning("extractive_compress failed (%s: %s), falling back to truncate", type(e).__name__, e)
        return truncate_tool_result(text, max_chars)


_ABSTRACT_COMPRESS_PROMPT = (
    "Summarize the following tool output, preserving:\n"
    "- Key facts, numbers, file paths, and identifiers\n"
    "- Error messages and stack traces (if any)\n"
    "- Code structure (function/class names, import statements)\n"
    "- Actionable conclusions or decisions\n\n"
    "Output a concise summary (max 300 words):\n\n"
)


def abstractive_compress(
    text: str,
    client: Any,
    model: str = "deepseek-v4-pro",
) -> str:
    """LLM 抽象压缩：用辅助模型将长文本压缩为精炼摘要。

    复用 agent.py:159-163 的 client.chat(model, messages, max_tokens) 调用形态。
    失败时回退 extractive_compress。

    Args:
        text: 原始工具结果文本
        client: CruxClient 实例
        model: 用于压缩的模型名称（默认 deepseek-v4-pro）

    Returns:
        压缩后的文本；LLM 调用失败时回退 extractive_compress。
    """
    try:
        # 限制输入长度，避免超出模型上下文
        input_text = text[:16000] if len(text) > 16000 else text
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": _ABSTRACT_COMPRESS_PROMPT + input_text}],
            max_tokens=600,
        )
        summary = response["choices"][0]["message"]["content"]
        if summary:
            return summary.strip()
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as e:
        import logging

        _log = logging.getLogger("crux.context")
        _log.warning("abstractive_compress failed (%s: %s), falling back to extractive", type(e).__name__, e)
        pass  # 静默回退

    return extractive_compress(text)


def compress_tool_result(
    text: str,
    client: Any = None,
    model: str = "deepseek-v4-pro",
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """智能压缩工具结果：三级路由（零成本 → LLM → 兜底截断）。

    路由策略：
    1. len(text) <= max_chars → 原样返回（不触发任何处理）
    2. extractive_compress（零 LLM 成本，TF-IDF 抽取）
    3. 若仍超限且 client 可用 → abstractive_compress（LLM 成本）
    4. 最终兜底 truncate_tool_result（现有 Tier 1）

    Args:
        text: 原始工具结果
        client: CruxClient 实例（可选，用于 LLM 压缩）
        model: 用于 LLM 压缩的模型名称
        max_chars: 目标最大字符数

    Returns:
        压缩后的工具结果。
    """
    # 快速路径：无需处理
    if not isinstance(text, str) or len(text) <= max_chars:
        return text

    try:
        from core.observability import metrics as _m
    except ImportError:
        _m = None

    # Tier 2a: 抽取式压缩（零成本）
    extracted = extractive_compress(text, max_chars=max_chars)
    if len(extracted) <= max_chars:
        if _m:
            _m.increment("tool_result_extractive")
        return extracted

    # Tier 2b: 抽象压缩（LLM 成本）
    if client is not None:
        try:
            abstracted = abstractive_compress(text, client, model)
            if abstracted and len(abstracted) <= max_chars * 2:
                if _m:
                    _m.increment("tool_result_abstractive")
                return abstracted
        except (ImportError, RuntimeError, OSError):
            pass  # 静默降级

    # 兜底: 硬截断（Tier 1）
    if _m:
        _m.increment("tool_result_truncated_fallback")
    return truncate_tool_result(text, max_chars)
