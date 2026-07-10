"""
Advisor 提示词模板
==================
GPT 是 CRUX 的主脑，直接给出完整回答。DeepSeek 负责审阅和执行。
"""

from __future__ import annotations


def build_advisor_prompt(query: str, context: str = "") -> str:
    """构建发送给 GPT 的提示词。

    GPT 直接回答，不受格式限制。回答会被 DeepSeek 审阅补充。
    """
    ctx_block = f"\n背景: {context}" if context else ""

    return f"""你是 CRUX 的主脑，正在帮一个开发者解决问题。{ctx_block}

直接、完整地回答以下问题。你就是最终回答者。
- 给明确结论和建议
- 涉及代码给完整可运行的代码
- 涉及方案给具体步骤
- 自由表达，不套模板

问题：
{query}""".strip()
