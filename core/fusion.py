"""
融合提示词构建器
=================
GPT 主脑回答 + DeepSeek 审阅执行 = 最终输出。
"""

from __future__ import annotations

from advisor.base import AdvisorResult


def build_fusion_prompt(
    user_query: str,
    crux_context: str,
    advisor_result: AdvisorResult,
) -> str:
    """构建交给 DeepSeek 的融合 prompt。

    GPT 已给出完整回答。DeepSeek 的角色是审阅官 + 执行者。
    """
    if advisor_result.ok:
        gpt_block = f"[GPT 的回答]\n{advisor_result.content}"
    else:
        gpt_block = "[GPT 暂不可用]"

    ctx = f"\n项目背景: {crux_context}" if crux_context else ""

    return f"""你是 CRUX 的执行官。{ctx}

用户问题：
{user_query}

{gpt_block}

你的任务：
1. 如果 GPT 已回答 → 审阅其正确性，纠正错误，补充遗漏
2. 如果涉及代码 → 给出可直接嵌入项目的完整实现
3. 如果需要执行操作 → 调用工具完成（读文件、编辑、运行测试等）
4. 如果 GPT 不可用 → 独立回答

不要重复 GPT 已经说对的内容。只补充、纠正、执行。
最终输出给用户的是你的审阅结果 + 执行结果。""".strip()
