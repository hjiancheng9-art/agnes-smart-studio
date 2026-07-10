"""
融合提示词构建器
=================
将 GPT Advisor 的建议与用户问题融合，生成发给 DeepSeek 的最终 prompt。
"""

from __future__ import annotations

from advisor.base import AdvisorResult


def build_fusion_prompt(
    user_query: str,
    crux_context: str,
    advisor_result: AdvisorResult,
) -> str:
    """构建融合了 GPT Advisor 建议的 DeepSeek prompt。

    如果 GPT 可用，注入其结构化建议；否则让 DeepSeek 独立回答。
    """
    if advisor_result.ok:
        advisor_block = _format_advisor_ok(advisor_result)
    else:
        advisor_block = _format_advisor_fail(advisor_result)

    ctx_block = f"[CRUX_CONTEXT]\n{crux_context}\n" if crux_context else ""

    return f"""
你是 CRUX 主控脑，底层模型是 DeepSeek。

要求：
1. 回答用户问题
2. 参考 GPT_ADVISOR_RESULT，但不要盲目复制
3. 如果 GPT 建议错误，以你的判断为准
4. 输出工程可落地的方案
5. 代码要能直接嵌入项目

{ctx_block}
{advisor_block}

[USER_QUERY]
{user_query}

请给出最终回答。
""".strip()


def _format_advisor_ok(result: AdvisorResult) -> str:
    """格式化成功的 Advisor 结果。"""
    return f"""
[GPT_ADVISOR_RESULT]
source: {result.source}
latency_ms: {result.latency_ms}

{result.content}
""".strip()


def _format_advisor_fail(result: AdvisorResult) -> str:
    """格式化失败的 Advisor 结果。"""
    return f"""
[GPT_ADVISOR_UNAVAILABLE]
status: {result.status}
error: {result.error or "未知错误"}

GPT 顾问不可用。请你独立回答，并保持工程可执行性。
""".strip()
