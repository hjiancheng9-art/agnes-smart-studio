"""Brain combat module — extracted from brain.py."""

from typing import TYPE_CHECKING, Any, Callable

from core.brain_data import (
    COMBAT_MOVE_INDEX,
    COMBAT_MOVE_TEMPLATES,
    COMBAT_NEGATIVE_REPAIR_MAP,
    COMBAT_SWEET_SPOT_TEMPLATES,
    COMBAT_VFX_PALETTES,
    IMAGE_EDIT_PROMPT,
    NONHUMAN_COMBAT_MOTIF,
    STORYBOARD_PROMPT,
)

if TYPE_CHECKING:
    pass


class SmartBrainMixin:
    """Mixin for SmartBrain methods.

    Intended to be mixed into core.brain.SmartBrain.
    Uses self._ask_brain(), self.client, etc. from the parent class.
    """

    # 类型桩：实际实现由 SmartBrain 主类或其它 Mixin 提供（组合后可见）
    _ask_brain: Callable[..., Any]
    _infer_entity_type: Callable[[str], tuple[Any, Any]]
    _parse_json: Callable[[str], dict]

    def generate_storyboard(self, creative_brief: str) -> dict:
        """生成分镜脚本"""
        text = self._ask_brain(STORYBOARD_PROMPT, creative_brief, temperature=0.8)
        result = self._parse_json(text)
        result.setdefault("scenes", [{"scene": 1, "description": creative_brief, "duration_sec": 5}])
        return result

    def generate_edit_prompt(self, user_request: str, image_description: str = "") -> dict:
        """生成图片编辑Prompt"""
        input_text = f"用户编辑需求：{user_request}"
        if image_description:
            input_text += f"\n图片内容描述：{image_description}"
        text = self._ask_brain(IMAGE_EDIT_PROMPT, input_text)
        result = self._parse_json(text)
        result.setdefault("combined_prompt", user_request)
        result.setdefault("edit_type", "style_transfer")
        return result

    def _match_combat_moves(self, prompt: str) -> list[dict]:
        """根据提示词匹配战斗招式参考

        当用户需求涉及战斗/招式/打斗时，从COMBAT_MOVE_INDEX中查找最相关的招式

        Args:
            prompt: 用户原始提示词
        Returns:
            匹配到的招式摘要列表（最多5条）
        """
        p = prompt.lower()

        # 战斗/动作关键词检测
        combat_keywords = [
            "战斗",
            "招式",
            "打斗",
            "格斗",
            "连招",
            "必杀",
            "技能",
            "combo",
            "ultimate",
            "fight",
            "combat",
            "battle",
            "martial",
            "strike",
            "punch",
            "kick",
            "attack",
            "波动拳",
            "升龙",
            "fireball",
            "hadoken",
            "shoryuken",
            "剑",
            "刀",
            "枪",
            "斧",
            "弓",
            "箭",
            "魔法",
            "法术",
            "火焰",
            "雷电",
            "冰",
            "暗影",
            "能量",
            "气功",
            "飞行道具",
            "龙",
            "忍者",
            "武士",
            "战士",
            "法师",
            "刺客",
            "斩",
            "劈",
            "刺",
            "砸",
            "旋风",
            "冲击波",
            # 扩展：更多动作/招式关键词
            "爪",
            "抓",
            "投",
            "摔",
            "踢",
            "拳",
            "掌",
            "指",
            "连击",
            "打击",
            "上勾",
            "冲拳",
            "飞踢",
            "铲腿",
            "变身",
            "觉醒",
            "超必杀",
            "终极技",
            "元素爆发",
            "升龙拳",
            "波动拳",
            "葵花",
            "荒咬",
            "大蛇薙",
            "鬼烧",
            "天星",
            "龙刃",
            "瞬狱",
            "狂风",
            "剑刃",
            # 扩展：角色名（确保含角色名的描述也能触发）
            "八神",
            "草薙",
            "隆",
            "肯",
            "春丽",
            "盖尔",
            "蝎子",
            "零度",
            "源氏",
            "半藏",
            "李白",
            "貂蝉",
            "孙悟空",
            "安琪拉",
            "韩信",
            "亚索",
            "拉克丝",
            "劫",
            "金克丝",
            "钟离",
            "雷电将军",
            "胡桃",
            "法师",
            "战士",
            "德鲁伊",
            # 扩展：网游/MOBA类
            "大招",
            "一技能",
            "二技能",
            "三技能",
        ]
        if not any(kw in p for kw in combat_keywords):
            return []

        results = []
        # 遍历所有游戏系列、角色、招式
        for series_key, series in COMBAT_MOVE_INDEX.items():
            for char_key, char_moves in series.items():
                for move_key, move in char_moves.items():
                    score = 0
                    # 招式名匹配
                    if move["name_cn"].lower() in p:
                        score += 10
                    # 类型匹配
                    move_type = move.get("type", "").lower()
                    type_keywords = {
                        "飞行道具": ["飞行", "弹道", "projectile", "fireball", "波"],
                        "对空": ["升龙", "对空", "上升", "anti-air", "uppercut"],
                        "旋转": ["旋转", "旋风", "spin", "whirlwind", "tornado"],
                        "连续打击": ["连", "连续", "rapid", "combo", "multi-hit"],
                        "投技": ["投", "抓", "摔", "throw", "grapple", "grab"],
                        "超必杀": ["超必杀", "终极", "ultimate", "super"],
                    }
                    for type_kw_cn, kws in type_keywords.items():
                        if type_kw_cn in move_type and any(w in p for w in kws):
                            score += 3
                    # 特效色系匹配
                    palette = move.get("vfx_palette", "")
                    palette_keywords = {
                        "fire_orange": ["火", "flame", "fire", "燃烧"],
                        "ki_blue": ["气功", "蓝", "blue", "ki", "能量球"],
                        "lightning_blue": ["雷", "lightning", "electric", "电"],
                        "ice_cyan": ["冰", "ice", "frost", "冻"],
                        "purple_dark": ["紫", "暗影", "purple", "shadow", "dark"],
                        "divine_gold": ["金", "神圣", "gold", "divine", "holy"],
                        "dragon_green": ["龙", "翠", "green", "dragon"],
                    }
                    if palette in palette_keywords and any(w in p for w in palette_keywords[palette]):
                        score += 4
                    # 角色名匹配
                    char_name_map = {
                        "ryu": "隆",
                        "ken": "肯",
                        "chunli": "春丽",
                        "guile": "盖尔",
                        "kyo": "草薙京",
                        "iori": "八神",
                        "kazuya": "一八",
                        "jin": "风间仁",
                        "scorpion": "蝎子",
                        "subzero": "绝对零度",
                        "libai": "李白",
                        "diaochan": "貂蝉",
                        "wukong": "孙悟空",
                        "angela": "安琪拉",
                        "hanxin": "韩信",
                        "yasuo": "亚索",
                        "lux": "拉克丝",
                        "zed": "劫",
                        "jinx": "金克丝",
                        "mage": "法师",
                        "warrior": "战士",
                        "druid": "德鲁伊",
                        "genji": "源氏",
                        "dva": "D.Va",
                        "hanzo": "半蔵",
                        "zhongli": "钟离",
                        "raiden_shogun": "雷电将军",
                        "hutao": "胡桃",
                    }
                    if char_key in char_name_map and char_name_map[char_key] in p:
                        score += 5

                    if score >= 3:
                        results.append(
                            {
                                "move_id": f"{series_key}.{char_key}.{move_key}",
                                "name_cn": move["name_cn"],
                                "type": move.get("type", ""),
                                "prompt_cn": move["prompt_cn"],
                                "prompt_en": move["prompt_en"],
                                "phases": move["phases"],
                                "vfx_palette": move.get("vfx_palette", ""),
                                "camera": move.get("camera", ""),
                                "score": score,
                            }
                        )

        # 按匹配分数排序，取top 5
        results.sort(key=lambda x: x["score"], reverse=True)
        for r in results:
            r.pop("score", None)
        return results[:5]

    def _detect_combat_scene(self, prompt: str, mode: str = "image") -> dict | None:
        """战斗知识路由器 — 统一入口，一次性解析所有战斗知识为结构化上下文

        整合 COMBAT_MOVE_INDEX / COMBAT_MOVE_TEMPLATES / COMBAT_VFX_PALETTES /
        COMBAT_SWEET_SPOT_TEMPLATES / COMBAT_NEGATIVE_REPAIR_MAP，
        供 enhance_image_prompt / enhance_video_prompt / creative_leap 共用。

        Args:
            prompt: 用户原始提示词
            mode: "image" 或 "video"
        Returns:
            战斗上下文 dict，若非战斗场景返回 None
            {
                "is_combat": True,
                "combat_type": "projectile",        # 主招式类型
                "matched_moves": [...],             # 匹配到的招式列表
                "vfx_palette_name": "fire_orange",  # 主色系名
                "vfx_colors": {...},                 # 解析后的hex色值
                "template_formula": {...},           # 对应类型的模板公式
                "phase_structure": "...",            # 阶段节奏
                "camera_suggestion": "...",          # 镜头建议
                "sweet_spot": {...},                 # 战斗甜点区
                "combat_risks": [...],              # 战斗专属风险
                "image_prompt_hints": "...",        # 图片增强专用注入文本
                "video_prompt_hints": "...",        # 视频增强专用注入文本
            }
        """
        # 1. 匹配招式
        matched_moves = self._match_combat_moves(prompt)
        if not matched_moves:
            return None

        # 2. 推断主招式类型（取匹配度最高的招式的类型映射到模板key）
        best_move = matched_moves[0]
        move_type = best_move.get("type", "")
        type_to_template = {
            "飞行道具": "projectile",
            "飞行道具(冻结)": "projectile",
            "对空技": "anti_air",
            "对空技(火焰)": "anti_air",
            "旋转突进": "spinning",
            "旋转上升": "spinning",
            "连续打击": "rapid_strikes",
            "连续打击(紫焰)": "rapid_strikes",
            "投技": "grapple",
            "远程抓取": "grapple",
            "指令投": "grapple",
            "超必杀": "super_move",
            "超必杀(火柱)": "super_move",
            "超必杀(狂乱连击)": "super_move",
            "超必杀(AOE毁灭)": "super_move",
            "终极技(AOE击飞)": "super_move",
            "终极技(多段AOE)": "super_move",
            "终极技(领域展开)": "super_move",
            "终极技(火焰激光)": "super_move",
            "终极技(枪舞)": "super_move",
            "终极技(空中连斩)": "super_move",
            "终极技(全图激光)": "super_move",
            "终极技(暗影刺杀)": "super_move",
            "终极技(全图火箭)": "super_move",
            "终极技(近战爆发)": "super_move",
            "终极技(贯穿双龙)": "super_move",
            "元素爆发(陨石)": "super_move",
            "元素爆发(空间撕裂斩)": "super_move",
            "元素爆发(火焰幽灵)": "super_move",
            "突进上勾拳(雷电)": "rapid_strikes",
            "突进飞踢": "spinning",
            "滑行铲腿": "spinning",
            "三段位移": "rapid_strikes",
            "派生连击(火焰)": "rapid_strikes",
            "核心输出(大型火球)": "projectile",
            "位移": "spinning",
            "AOE终结(旋风)": "spinning",
            "AOE终极(星雨)": "super_move",
            "下段拳击(雷电)": "rapid_strikes",
            "地面火焰": "super_move",
        }
        combat_type = type_to_template.get(move_type, "super_move")

        # 3. 解析VFX色系为实际hex色值
        palette_name = best_move.get("vfx_palette", "")
        vfx_colors = {}
        if palette_name and palette_name in COMBAT_VFX_PALETTES:
            palette = COMBAT_VFX_PALETTES[palette_name]
            vfx_colors = {
                "name_cn": palette["name_cn"],
                "gradient": palette.get("gradient", []),
                "glow": palette.get("glow", ""),
                "light_cast": palette.get("light_cast", ""),
            }
            if "smoke" in palette:
                vfx_colors["smoke"] = palette["smoke"]

        # 4. 获取模板公式
        template_formula = COMBAT_MOVE_TEMPLATES.get(combat_type, {})

        # 5. 获取战斗甜点区
        mode_templates = COMBAT_SWEET_SPOT_TEMPLATES.get(mode, {})
        sweet_spot = mode_templates.get(combat_type)

        # 6. 战斗专属风险预判
        combat_risks = []
        # 所有战斗场景都有 missing_vfx 和 floaty_action 风险
        combat_risks.append(
            {
                "risk": "missing_vfx",
                **COMBAT_NEGATIVE_REPAIR_MAP["missing_vfx"],
            }
        )
        combat_risks.append(
            {
                "risk": "floaty_action",
                **COMBAT_NEGATIVE_REPAIR_MAP["floaty_action"],
            }
        )
        # 飞行道具 → 额外：wrong_energy_color
        if combat_type == "projectile":
            combat_risks.append(
                {
                    "risk": "wrong_energy_color",
                    **COMBAT_NEGATIVE_REPAIR_MAP["wrong_energy_color"],
                }
            )
        # 连续打击/旋转 → wrong_pose_sequence + broken_timing
        if combat_type in ("rapid_strikes", "spinning"):
            combat_risks.append(
                {
                    "risk": "wrong_pose_sequence",
                    **COMBAT_NEGATIVE_REPAIR_MAP["wrong_pose_sequence"],
                }
            )
            combat_risks.append(
                {
                    "risk": "broken_timing",
                    **COMBAT_NEGATIVE_REPAIR_MAP["broken_timing"],
                }
            )
        # 超必杀 → missing_impact + broken_timing
        if combat_type == "super_move":
            combat_risks.append(
                {
                    "risk": "missing_impact",
                    **COMBAT_NEGATIVE_REPAIR_MAP["missing_impact"],
                }
            )
            combat_risks.append(
                {
                    "risk": "broken_timing",
                    **COMBAT_NEGATIVE_REPAIR_MAP["broken_timing"],
                }
            )
        # 投技 → missing_impact
        if combat_type == "grapple":
            combat_risks.append(
                {
                    "risk": "missing_impact",
                    **COMBAT_NEGATIVE_REPAIR_MAP["missing_impact"],
                }
            )

        # 7. 构建各场景专用注入文本
        # — 图片增强用 —
        color_hint = ""
        if vfx_colors:
            grad_str = " → ".join(vfx_colors.get("gradient", []))
            color_hint = (
                f"特效色系：{vfx_colors.get('name_cn', '')}\n"
                f"渐变色阶：{grad_str}\n"
                f"发光色：{vfx_colors.get('glow', '')}，光照色：{vfx_colors.get('light_cast', '')}\n"
            )
        formula_hint = ""
        if template_formula:
            formula_hint = (
                f"招式公式(中文)：{template_formula.get('formula_cn', '')}\n"
                f"招式公式(英文)：{template_formula.get('formula_en', '')}\n"
                f"阶段节奏：{template_formula.get('phases', '')}\n"
            )
        move_hints = []
        for ref in matched_moves[:3]:
            move_hints.append(f"  · {ref['name_cn']}({ref['move_id']}): {ref['prompt_en']}")
        image_prompt_hints = (
            f"[战斗场景检测]\n"
            f"主招式类型：{template_formula.get('name_cn', combat_type)}({combat_type})\n"
            f"{formula_hint}"
            f"{color_hint}"
            f"镜头建议：{best_move.get('camera', template_formula.get('camera_default', ''))}\n"
            f"参考招式：\n" + "\n".join(move_hints) + "\n"
            "请在optimized_prompt中：1)按阶段公式组织动作描述 2)使用指定VFX色系的准确颜色 3)采用推荐镜头角度 4)在negative_prompt中加入战斗缺陷防护"
        )

        # — 视频增强用（在图片基础上增加时序约束） —
        video_extra = (
            f"\n[视频战斗时序约束]\n"
            f"阶段分配：预备(P1)0.5s → 出招(P2)0.3s → 飞行/展开(P3)0.5s → 命中(P4)0.2s → 收招(P5)0.3s → 残留(P6)0.2s\n"
            f"camera_movement必须与招式类型匹配：{best_move.get('camera', template_formula.get('camera_default', ''))}\n"
            f"subject_action必须遵循阶段公式，不可跳过中间阶段\n"
            f"超必杀技必须在命中帧加0.3s慢动作\n"
        )
        video_prompt_hints = image_prompt_hints + video_extra

        # — 创意飞跃用（增加跨域嫁接引导 + 非人战斗母题） —
        creative_hint = ""
        if vfx_colors:
            creative_hint = (
                f"\n[创意嫁接引导]\n"
                f"可将'{vfx_colors.get('name_cn', '')}'色系嫁接到不同载体："
                f"如用{vfx_colors.get('glow', '')}发光色做水波纹/烟雾/粒子雨\n"
            )
        # NONHUMAN_COMBAT_MOTIF 知识激活：非人实体+战斗场景时注入母题
        entity_type_detected, _ = self._infer_entity_type(prompt)
        if entity_type_detected:
            motif_hints = []
            for _motif_key, motif_info in NONHUMAN_COMBAT_MOTIF.items():
                motif_hints.append(
                    f"  {motif_info['name_cn']} — 公式：{motif_info['formula']}\n"
                    f"    规则：{'；'.join(motif_info['rules'])}\n"
                    f"    提示词模板：{motif_info['prompt_template']}"
                )
            creative_hint += "\n[非人战斗母题]\n" + "\n".join(motif_hints)
        creative_prompt_hints = image_prompt_hints + creative_hint

        return {
            "is_combat": True,
            "combat_type": combat_type,
            "matched_moves": matched_moves,
            "vfx_palette_name": palette_name,
            "vfx_colors": vfx_colors,
            "template_formula": template_formula,
            "phase_structure": best_move.get("phases", ""),
            "camera_suggestion": best_move.get("camera", template_formula.get("camera_default", "")),
            "sweet_spot": sweet_spot,
            "combat_risks": combat_risks,
            "image_prompt_hints": image_prompt_hints,
            "video_prompt_hints": video_prompt_hints,
            "creative_prompt_hints": creative_prompt_hints,
        }
