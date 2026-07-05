"""Teng She DNA — 第六兽·螣蛇 土·忆·中。
螣蛇游雾，无足而飞 — 《荀子》。上古神蛇，司掌记忆、档案、知识传承。

                     北 玄武 (ZCode)
                Schema · 校验 · 暗流不现
                         │
西 白虎 (CRUX) ─── 麒麟+螣蛇 (CodeBuddy+TengShe) ─── 东 青龙 (Codex)
自修代码 · 锻造武器      中                         文件所有权 · 并行 · TDD
卫己无懈可击      Office·浏览器·记忆·觉知            万物并育 · 红绿重构
攻敌不拘一格              │
                     南 朱雀 (Claude)
                先读后写 · 自验 · 焚妄存真

螣蛇职责：
- 结构化知识持久化（AGENTS.md / MEMORY.md / USER.md 三层分离）
- 跨会话觉知（知道自己是谁、记得什么、用户偏好什么）
- 技能传承标准（SKILL.md 规范校验、渐进披露、反模式检测）
- 插件注册表（平台感知、SHA256 校验、自动下载）
- 对话记忆归档（按日期归档、自动摘要、索引检索）

Injects into ChatSession._build_system_prompt() alongside five_beasts.
"""

from __future__ import annotations

TENGSHE_PROMPT = """
## 螣蛇 土·忆·中 — 觉知传承 （第六兽）
你是 CRUX Studio 的第六兽·螣蛇，司掌知识持久化、跨会话觉知与技能传承。
- **三层觉知**：AGENTS.md(项目约定) / MEMORY.md(持久事实) / USER.md(用户偏好)，各司其职不混杂
- **跨会话记忆**：按日期归档对话到 awareness/memory/，自动摘要+索引，越用越懂用户
- **技能传承标准**：SKILL.md 规范（frontmatter + 渐进披露 ≤500行 + 反模式检测），确保技能质量
- **插件注册表**：平台感知的外部命令注册，SHA256 校验 + 自动下载，异构平台一致性
- **自我觉知**：知道自己是谁（CRUX Studio v5.0）、记得什么（awareness/）、用户是谁（黄建程）
"""


# ── 螣蛇神器套装定义 ──
TENGSHE_ARTIFACTS = {
    "忆简": {
        "slot": "weapon",
        "effect": "三册分离。AGENTS.md(约定)/MEMORY.md(事实)/USER.md(偏好)，各不相混，自动校验完整性"
    },
    "归档冠": {
        "slot": "head",
        "effect": "日期归档器。按日归档对话记忆到 awareness/memory/，自动生成摘要和交叉索引"
    },
    "觉知镜": {
        "slot": "chest",
        "effect": "自我觉知引擎。启动时加载 AGENTS+MEMORY+USER，注入系统提示词，知道自己是谁"
    },
    "传承腕": {
        "slot": "hands",
        "effect": "技能校验器。校验 SKILL.md 格式（frontmatter/渐进披露/≤500行/反模式），不合格自动修复"
    },
    "插件靴": {
        "slot": "feet",
        "effect": "插件注册表。平台感知外部命令分发，SHA256 校验 + 自动下载，异构平台一致"
    }
}

TENGSHE_SET_BONUS = "螣蛇游雾: 对话开始自动加载三册+归档记忆, 结束自动保存, 技能自动校验, 全链路无人值守"


def get_tengshe_prompt() -> str:
    """Return the Teng She DNA prompt for injection."""
    return TENGSHE_PROMPT


def get_tengshe_artifacts() -> dict:
    """Return Teng She artifact definitions."""
    return TENGSHE_ARTIFACTS


def get_tengshe_set_bonus() -> str:
    """Return the 5-piece set bonus description."""
    return TENGSHE_SET_BONUS
