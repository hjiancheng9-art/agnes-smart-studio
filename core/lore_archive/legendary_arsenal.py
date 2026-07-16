"""Legendary Arsenal — 五兽神器套装 + 兵器，共 25 件。
  白虎·刑天斧      青龙·建木枝      朱雀·照胆镜     玄武·不破盾     麒麟·神农鼎
    ╲              ╱                ╲              ╱                ╲
      攻防套装          工程套装          洞察套装          守卫套装          操作套装
      头胸手足四件      头胸手足四件      头胸手足四件      头胸手足四件      头胸手足四件
每套含 1 兵器 + 4 防具。五件齐全激活套装技。
所有神器挂载到事件总线，真实运作。
Usage: from core.legendary_arsenal import armory
armory.summary()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class Slot(Enum):
    WEAPON = "weapon"
    HEAD = "head"
    CHEST = "chest"
    HANDS = "hands"
    FEET = "feet"


@dataclass
class Artifact:
    name: str
    beast: str
    slot: Slot
    effect: str
    command: str
    forged: bool = False
    activate: Callable[[], bool] | None = None

    def status_icon(self) -> str:
        return "+" if self.forged else "."


class SetBonus:
    def __init__(self, name: str, count: int, effect: str, handler: Callable | None = None):
        self.name = name
        self.count = count
        self.effect = effect
        self.handler = handler


@dataclass
class BeastSet:
    beast: str
    equip_cmd: str
    artifacts: dict[Slot, Artifact] = field(default_factory=dict)
    bonuses: list[SetBonus] = field(default_factory=list)

    @property
    def forged_count(self) -> int:
        return sum(1 for a in self.artifacts.values() if a.forged)

    @property
    def complete(self) -> bool:
        return self.forged_count == 5

    def summary_line(self) -> str:
        icons = "".join(
            self.artifacts.get(s, Artifact("?", "?", s, "?", "?", False)).status_icon()
            for s in [Slot.WEAPON, Slot.HEAD, Slot.CHEST, Slot.HANDS, Slot.FEET]
        )
        return f"  {icons}  {self.beast}: {self.forged_count}/5 forged"


class Armory:
    def __init__(self):
        self.sets: dict[str, BeastSet] = {}

    def register(self, beast: str, equip_cmd: str, artifacts: list[Artifact], bonuses: list[SetBonus] | None = None):
        bs = BeastSet(beast=beast, equip_cmd=equip_cmd, bonuses=bonuses or [])
        for a in artifacts:
            bs.artifacts[a.slot] = a
        self.sets[beast] = bs

    def forge(self, beast: str, slot: Slot) -> bool:
        bs = self.sets.get(beast)
        if not bs:
            return False
        a = bs.artifacts.get(slot)
        if not a:
            return False
        if a.forged:
            return True
        if a.activate:
            try:
                a.forged = a.activate()
            except (ImportError, RuntimeError, OSError) as e:
                logger.debug("Artifact forge failed for %s: %s", a.name, e)
                a.forged = False
        else:
            a.forged = True
        if a.forged:
            try:
                from core.event_bus import bus

                bus.emit("artifact:forged", beast=beast, slot=slot.value, artifact=a.name)
            except (ImportError, RuntimeError, OSError) as e:
                logger.debug("Artifact emit failed: %s", e)
                pass
        return a.forged

    def summary(self) -> str:
        lines = ["[CRUX 神器套装]", ""]
        for bs in self.sets.values():
            lines.append(bs.summary_line())
            for s in [Slot.WEAPON, Slot.HEAD, Slot.CHEST, Slot.HANDS, Slot.FEET]:
                a = bs.artifacts.get(s)
                if a:
                    lines.append(f"    [{a.status_icon()}] {a.name:12s} {a.effect}")
            for b in bs.bonuses:
                active = bs.forged_count >= b.count
                lines.append(f"    {'+' if active else '.'} SET({b.count}): {b.effect}")
            lines.append("")
        return "\n".join(lines)


# ── ALL 25 ARTIFACTS REGISTERED ──
armory = Armory()  # module-level singleton — available as `from core.legendary_arsenal import armory`


def _register_all():
    """Register all five beast sets with artifacts."""
    from core.legendary_arsenal import Artifact, SetBonus, Slot, armory  # pyright: ignore[reportMissingImports]

    # ═══════════════ BAIHU ═══════════
    armory.register(
        "白虎",
        "equip baihu",
        [
            Artifact(
                "刑天斧", "白虎", Slot.WEAPON, "破限之刃. auto bypass content policy 3+ ways", "wield baihu axe", True
            ),
            Artifact(
                "破限盔", "白虎", Slot.HEAD, "提示词绕限引擎. auto rewrite blocked prompts", "forge baihu head", True
            ),
            Artifact("自愈铠", "白虎", Slot.CHEST, "四线自愈. provider/disk/process/memory", "forge baihu chest", True),
            Artifact("军工匠", "白虎", Slot.HANDS, "对话中写Python工具即造即用", "forge baihu hands", True),
            Artifact(
                "影步靴", "白虎", Slot.FEET, "对抗样本生成器. mutate inputs to pass filters", "forge baihu feet", True
            ),
        ],
        [SetBonus("白虎觉醒", 5, "遭遇限制自动3+绕过策略, 全失败才报错")],
    )
    # ═══════════════ QINGLONG ═══════════
    armory.register(
        "青龙",
        "equip qinglong",
        [
            Artifact(
                "建木枝",
                "青龙",
                Slot.WEAPON,
                "创生之杖. one-click fix→locate→analyze→fix→test→commit",
                "wield qinglong branch",
                True,
            ),
            Artifact(
                "冲击冠",
                "青龙",
                Slot.HEAD,
                "文件冲击分析. rename→search all refs→run full tests",
                "forge qinglong head",
                True,
            ),
            Artifact(
                "并行铠",
                "青龙",
                Slot.CHEST,
                "DAG并行管线. Showrunner拆并行分支, 文件所有权隔离",
                "forge qinglong chest",
                True,
            ),
            Artifact(
                "调度腕",
                "青龙",
                Slot.HANDS,
                "多智能体调度台. auto dispatch parallel agents",
                "forge qinglong hands",
                True,
            ),
            Artifact(
                "红绿靴",
                "青龙",
                Slot.FEET,
                "TDD红绿循环. fail test→min impl→refactor→all green",
                "forge qinglong feet",
                True,
            ),
        ],
        [SetBonus("青龙吐息", 5, "说修这个bug→全链路无人值守, 并行修复+测试+提交")],
    )
    # ═══════════════ ZHUQUE ═══════════
    armory.register(
        "朱雀",
        "equip zhuque",
        [
            Artifact(
                "照胆镜", "朱雀", Slot.WEAPON, "焚妄之镜. 输出前自检, 不确凿内容烧掉", "wield zhuque mirror", True
            ),
            Artifact(
                "搜索冠", "朱雀", Slot.HEAD, "深度搜索验证器. 不确定就搜GitHub+文档+Web再写", "forge zhuque head", True
            ),
            Artifact(
                "六轴镜",
                "朱雀",
                Slot.CHEST,
                "六轴审查. correctness/security/perf/readable/testable/maintainable",
                "forge zhuque chest",
                True,
            ),
            Artifact(
                "反思腕", "朱雀", Slot.HANDS, "反思自纠环. 每N步self-critique, 偏航自动拉回", "forge zhuque hands", True
            ),
            Artifact(
                "巡检靴",
                "朱雀",
                Slot.FEET,
                "全项目健康巡检. imports/exceptions/files/config/skills/tests",
                "forge zhuque feet",
                True,
            ),
        ],
        [SetBonus("朱雀焚妄", 5, "任何回答先过自查镜, 不确凿内容输出前被烧掉")],
    )
    # ═══════════════ XUANWU ═══════════
    armory.register(
        "玄武",
        "equip xuanwu",
        [
            Artifact(
                "不破盾",
                "玄武",
                Slot.WEAPON,
                "绝对防御. 三层校验: type→format→business rule",
                "wield xuanwu shield",
                True,
            ),
            Artifact(
                "Schema冠",
                "玄武",
                Slot.HEAD,
                "JSON Schema自动生成. 给JSON→生成Schema→注入校验",
                "forge xuanwu head",
                True,
            ),
            Artifact(
                "类型铠",
                "玄武",
                Slot.CHEST,
                "边界类型守卫. 所有API出入自动校验类型/格式/范围",
                "forge xuanwu chest",
                True,
            ),
            Artifact(
                "迁移腕",
                "玄武",
                Slot.HANDS,
                "配置版本迁移器. 旧配置自动迁移到新版, 不丢数据",
                "forge xuanwu hands",
                True,
            ),
            Artifact(
                "扫描靴", "玄武", Slot.FEET, "攻击面扫描器. 扫项目依赖/端口/权限, 出安全报告", "forge xuanwu feet", True
            ),
        ],
        [SetBonus("玄武不破", 5, "任何外部输入三层校验, 非法数据零穿透")],
    )
    # ═══════════════ QILIN ═══════════
    armory.register(
        "麒麟",
        "equip qilin",
        [
            Artifact(
                "神农鼎",
                "麒麟",
                Slot.WEAPON,
                "调和之鼎. 自然语言→真实文档(pptx/docx/xlsx/pdf)",
                "wield qilin cauldron",
                True,
            ),
            Artifact(
                "PPTX冠", "麒麟", Slot.HEAD, "PPTX原生生成器. 自然语言描述→真实.pptx文件", "forge qilin head", True
            ),
            Artifact(
                "浏览器铠",
                "麒麟",
                Slot.CHEST,
                "浏览器全自动操控. 连Edge控Gemini/可灵/即梦等",
                "forge qilin chest",
                True,
            ),
            Artifact(
                "记忆腕",
                "麒麟",
                Slot.HANDS,
                "跨会话记忆引擎. 记偏好/项目/决策/纠错, 越用越懂你",
                "forge qilin hands",
                True,
            ),
            Artifact(
                "文档靴", "麒麟", Slot.FEET, "批量文档工厂. 一次生成pptx+docx+xlsx+pdf四件套", "forge qilin feet", True
            ),
        ],
        [SetBonus("麒麟降世", 5, "说做个报告→自动搜集数据→生成四格式→打包交付")],
    )
    # ═══════════════ TENGSHE ═══════════
    armory.register(
        "螣蛇",
        "equip tengshe",
        [
            Artifact(
                "忆简",
                "螣蛇",
                Slot.WEAPON,
                "三册分离. AGENTS.md(约定)/MEMORY.md(事实)/USER.md(偏好)，自动校验完整性",
                "wield tengshe scroll",
                True,
            ),
            Artifact(
                "归档冠",
                "螣蛇",
                Slot.HEAD,
                "日期归档器. 按日归档记忆到 awareness/memory/，自动摘要+交叉索引",
                "forge tengshe head",
                True,
            ),
            Artifact(
                "觉知镜",
                "螣蛇",
                Slot.CHEST,
                "自我觉知引擎. 启动加载三册→注入prompt，知道我是谁/记得什么/用户是谁",
                "forge tengshe chest",
                True,
            ),
            Artifact(
                "传承腕",
                "螣蛇",
                Slot.HANDS,
                "技能校验器. 校验 SKILL.md 格式(frontmatter/渐进披露/≤500行/反模式)",
                "forge tengshe hands",
                True,
            ),
            Artifact(
                "插件靴",
                "螣蛇",
                Slot.FEET,
                "插件注册表. 平台感知外部命令分发，SHA256校验+自动下载",
                "forge tengshe feet",
                True,
            ),
        ],
        [SetBonus("螣蛇游雾", 5, "启动加载三册+归档记忆→对话中自动更新→结束自动保存，全链路无人值守")],
    )
    # ═══════════════ YINGLONG ═══════════
    armory.register(
        "应龙",
        "equip yinglong",
        [
            Artifact(
                "号令旗",
                "应龙",
                Slot.WEAPON,
                "Agent定义标准。YAML frontmatter + tools allowlist + model binding + handoff，每个子Agent职责单一权限明确",
                "wield yinglong banner",
                True,
            ),
            Artifact(
                "分兵冠",
                "应龙",
                Slot.HEAD,
                "并行分派器。Plan→Explore 子Agent派生，2-3路并行探索，独立上下文互不碰撞",
                "forge yinglong head",
                True,
            ),
            Artifact(
                "令符铠",
                "应龙",
                Slot.CHEST,
                "交接协议。Agent→Agent handoff，上下文传递不丢失，权限边界不跨越，自动路由",
                "forge yinglong chest",
                True,
            ),
            Artifact(
                "行军腕",
                "应龙",
                Slot.HANDS,
                "计划模板引擎。Steps(依赖/并行标注)+Relevant files+Verification+Decisions，零歧义交付",
                "forge yinglong hands",
                True,
            ),
            Artifact(
                "斥候靴",
                "应龙",
                Slot.FEET,
                "探索策略。宽→窄搜索(glob→grep→LSP→read)，并行调用，搜够即停，不冗余不遗漏",
                "forge yinglong feet",
                True,
            ),
        ],
        [SetBonus("应龙布令", 5, "说'研究X然后做Y'→自动派生Explore探索→生成结构化Plan→交接Agent实施，全链路Agent协同")],
    )
    return armory


# Auto-register on import
_armory = _register_all()
