"""
Advisor 提示词模板
==================
GPT 不直接替 CRUX 回答，而是以"顾问"身份提供结构化建议。
"""

from __future__ import annotations


def build_advisor_prompt(query: str, context: str = "") -> str:
    """构建发送给 GPT Advisor 的结构化提示词。

    GPT 的角色是顾问，不是最终回答者。输出结构化建议供 DeepSeek 融合。
    """
    ctx_block = f"[CRUX_CONTEXT]\n{context}\n" if context else ""

    return f"""
你是 CRUX 的 GPT-first 顾问层，不是最终回答者。

你的任务：
1. 判断用户真正意图
2. 给出关键技术判断
3. 指出风险点
4. 给出 CRUX 最终回答应该采用的结构
5. 给出必要代码建议（如果涉及代码）

输出格式（严格遵守）：

[INTENT]
用户真正想解决什么。

[KEY_POINTS]
- 关键判断 1
- 关键判断 2

[RISKS]
- 风险 1
- 风险 2

[RECOMMENDED_ANSWER]
建议 CRUX 如何组织最终回答。

[CODE_HINTS]
必要代码或伪代码。如不涉及代码则写"无"。

{ctx_block}
[USER_QUERY]
{query}
""".strip()
