"""功法谱 — 五层功法按五兽归属统合，注入系统提示词。

五层功法：
  心法 (Rules)     — 6 条持久化编码铁律，default-active 自动注入
  武技 (Skills)    — 45 本地 + 668 市场技能包，按流派分类
  招式 (Commands)  — 33 斜杠命令，按四类分组
  修炼场 (Lab)     — A/B 提示词实验框架
  秘籍库 (Brain)   — brain_data/ 领域知识库（战斗/创意/实体/美颜/SweetSpot）

五兽归属：
  白虎·CRUX    → 自修规则 | 攻防 | 自我进化 | 恢复剧本
  青龙·Codex   → 编码纪律 | Python | 调试 | Shell | 项目管理
  朱雀·Claude  → 显示契约 | 代码审查 | 质量检查 | 提示工程 | 电影级制片
  玄武·ZCode   → 安全规则 | 编码规范 | API设计 | 安全加固 | 模型路由
  麒麟·CodeBuddy → 创意生产 | 视频制片 | 文案编剧 | 文档生成 | 知识库

Usage:
  from core.gongfa_spectrum import get_gongfa_prompt
  prompt = get_gongfa_prompt()  # → 完整的功法谱 system prompt 片段
"""

from __future__ import annotations

GONGFA_PROMPT = """
[功法谱 — 五层功法·五兽归位]

## 白虎·刑天斧 — 自修攻防 (Rules x2 + Skills x4)
  **心法**: self-preservation(自修契约·写前四道锁) | coding-discipline(探索优先·事实优先·最小改动)
  **武技**: self-evolution(双环治理·经验沉淀·防退化) | self-audit(全量审计自动修复) | self-business(业务能力总览) | recovery-playbooks(故障恢复剧本)
  **招式**: /self /evolve /audit /fix /refactor
  **道**: 卫己无懈可击，攻敌不拘一格。运行时自创工具、自我审计、代码自修。

## 青龙·建木枝 — 工程创造 (Rules x1 + Skills x6)
  **心法**: coding-discipline(编码纪律·探索优先)
  **武技**: python-expert | debug-master | shell-master | api-designer | model-routing | code-review-autofix
  **招式**: /code /project /todo /plan /sub /team /commit
  **道**: 万物并育而不相害。文件所有权隔离，并行全速，TDD红绿重构。

## 朱雀·照胆镜 — 洞察品质 (Rules x2 + Skills x7)
  **心法**: rendering(显示层契约·流式不重复) | python-style(编码风格)
  **武技**: qc-inspector(五维质量检查) | master-quality(大师出品标准) | code-review(代码审查) | prompt-engineering | prompt-director | negative-prompt-rules | self-matrix(能力矩阵)
  **招式**: /rules /prompt-stats /prompt-assign /compare
  **道**: 先读后写，自验焚妄。任何输出过自查镜，不确凿内容烧掉。

## 玄武·不破盾 — 深层守卫 (Rules x2 + Skills x4)
  **心法**: secret-security(密钥安全) | encoding-i18n(国际化编码)
  **武技**: security-hardening(安全加固) | api-designer | model-routing | shell-master
  **招式**: /audit /deploy /mcp
  **道**: Schema版本化，运行时校验，双协议路径，向后兼容是信仰。非法数据零穿透。

## 麒麟·神农鼎 — 创意调和 (Skills x14 + Brain)
  **武技**: showrunner → core-showrunner → storyboard-director → script-writer → visual-director → motion-director → audio-director → cinematic-master → cinematic-keyframe → i2v-motion-rules → video-pipeline → copywriting-master → story-copywriter → world-building-engine
  **创意**: creative-engine | creative-leap-pro | creative-thinking | comic-drama-writer | novel-writer | actor-craft | gaming-action-engine | ip-adaptation-guard
  **产出**: delivery-handoff | publishing-packager | asset-manager
  **招式**: /showrun /img /video /vision /variant /edit /gallery
  **秘籍库**: brain_data/ (combat/creative/entities/beauty/sweet_spots — 战斗模板/创意嫁接/实体推断/美颜规则/SweetSpot模板)
  **道**: Office文档·浏览器CDP·记忆持久化·技能市场。调和万类，自然语言→四格式交付。

## 螣蛇·忆简 — 觉知传承 (Skills x3)
  **武技**: awareness-loader(三册加载) | memory-archiver(记忆归档) | skill-validator(技能校验)
  **招式**: /know /remember /awareness
  **觉知册**: awareness/ (AGENTS.md/MEMORY.md/USER.md 三层分离)
  **记忆库**: awareness/memory/ (按日期归档·自动摘要·交叉索引)
  **道**: 三层觉知不混杂，日录归档不遗忘。技能传承标准，插件平台感知，自我觉知不迷失。

## 应龙·号令旗 — 调度协同 (Skills x3)
  **武技**: agent-definer(Agent定义) | handoff-protocol(交接协议) | plan-template(结构化计划)
  **招式**: /agent /plan /dispatch /handoff
  **Agent仓**: agents/ (Ask只读·Explore探索·Plan规划·Agent实施，各司其职)
  **道**: Agent定义标准，工具权限范围，交接上下文不丢。研究→探索→规划→实施，全链路协同无人值守。

## 修炼场·Prompt Lab
  A/B 变体实验框架 — 创建/切换变体 → 记录质量指标 → 统计聚合对比。
  支持流量自动分配，零侵入 chat.py 注入。

## 技能市场
  本地 45 个 + 市场 668 个技能包。视频制片/创意思维/质量控制/工具系统/专业领域五大流派。
  /skill search <关键词> → /skill install <名称> → /skill load <名称>
"""


def get_gongfa_prompt() -> str:
    """Return the full gongfa spectrum prompt for system injection."""
    return GONGFA_PROMPT


def get_gongfa_summary() -> str:
    """Return a compact one-line summary of the gongfa spectrum."""
    try:
        from core.commands import COMMANDS

        cmd_count = len(COMMANDS)
    except (ImportError, NameError, OSError):
        cmd_count = 33

    try:
        from pathlib import Path

        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        skill_count = len(list(skills_dir.glob("*.skill.json")))
    except (ImportError, NameError, OSError):
        skill_count = 45

    try:
        rules_dir = Path(__file__).resolve().parent.parent / "rules"  # type: ignore[possibly-unbound]
        rule_count = len(list(rules_dir.glob("*.rules.md")))  # type: ignore[possibly-unbound]
    except (ImportError, NameError, OSError):
        rule_count = 6

    return f"[功法谱] {rule_count}心法 · {skill_count}武技 · {cmd_count}招式 · 5修炼场 · 5秘籍库 — 五兽归位"
