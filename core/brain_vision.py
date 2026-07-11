"""Brain vision module — extracted from brain.py."""

from collections.abc import Callable
from typing import Any

from core.brain_data import (
    BEAUTY_PORTRAIT_MAP,
    BEAUTY_PRODUCTION_RULES,
    ENTITY_TYPE_MAP,
    GRAFT_TARGETS,
)


class SmartBrainMixin:
    """Mixin for SmartBrain methods.

    Intended to be mixed into core.brain.SmartBrain.
    Uses self._ask_brain(), self.client, etc. from the parent class.
    """

    # ── type stubs: provided by SmartBrain or other Mixins ──
    _ask_brain: Callable[..., Any]
    _match_beauty_sweet_spot: Callable[..., Any]
    _match_sweet_spot: Callable[..., Any]
    _merge_negative: Callable[..., Any]
    _parse_json: Callable[..., Any]
    _predict_beauty_risks: Callable[..., Any]
    _predict_risks: Callable[..., Any]

    def _postprocess_image_enhance(
        self,
        user_prompt: str,
        brain_text: str,
        entity_type: str | None,
        surface_policy: str | None,
        beauty_type: str | None,
        combat_ctx: dict | None,
    ) -> dict:
        """enhance_image_prompt 的纯计算后处理阶段（无 I/O）。

        接收 LLM 返回的原始文本，完成 JSON 解析、甜点区叠加、风险预判等。
        同步版与异步版共用此方法，保证业务逻辑一致性。
        """
        result = self._parse_json(brain_text)
        result.setdefault("optimized_prompt", user_prompt)
        result.setdefault("negative_prompt", "")

        # 自动匹配甜点区（优先：实体专属 > 战斗专属 > 帅哥美女 > 场景模板）
        template = self._match_sweet_spot(user_prompt, "image", entity_type)
        if template:
            # 叠加模板的负面提示词（去重合并）
            base_neg = result.get("negative_prompt", "")
            template_neg = template["negative"]
            result["negative_prompt"] = self._merge_negative(base_neg, template_neg)

            # 始终检查并追加模板 suffix 中缺失的质量关键词
            existing = result["optimized_prompt"].lower()
            suffix_terms = template["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] = result["optimized_prompt"] + ", " + ", ".join(missing[:5])

            result["sweet_spot"] = template["name"]

        # 战斗甜点区叠加（战斗场景时，覆盖通用场景模板的不足）
        if combat_ctx and combat_ctx.get("sweet_spot"):
            combat_tpl = combat_ctx["sweet_spot"]
            base_neg = result.get("negative_prompt", "")
            result["negative_prompt"] = self._merge_negative(base_neg, combat_tpl["negative"])
            existing = result["optimized_prompt"].lower()
            suffix_terms = combat_tpl["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] += ", " + ", ".join(missing[:5])
            result["combat_sweet_spot"] = combat_tpl["name"]
            result["combat_type"] = combat_ctx["combat_type"]
            # 注入VFX色系信息
            if combat_ctx.get("vfx_colors"):
                result["vfx_palette"] = combat_ctx["vfx_colors"]

        # 帅哥美女甜点区叠加（实体未匹配时）
        if beauty_type and not entity_type:
            beauty_tpl = self._match_beauty_sweet_spot(beauty_type, "image")
            if beauty_tpl:
                base_neg = result.get("negative_prompt", "")
                result["negative_prompt"] = self._merge_negative(base_neg, beauty_tpl["negative"])
                existing = result["optimized_prompt"].lower()
                suffix_terms = beauty_tpl["suffix"].split(", ")
                missing = [t for t in suffix_terms if t.lower() not in existing]
                if missing:
                    result["optimized_prompt"] += ", " + ", ".join(missing[:5])
                if "sweet_spot" not in result:
                    result["sweet_spot"] = beauty_tpl["name"]

        # 注入实体类型和表面策略信息
        if entity_type:
            result["entity_type"] = entity_type
            result["surface_policy"] = surface_policy

            # 形态演化控制（非人实体）
            has_transform = any(
                kw in user_prompt.lower()
                for kw in [
                    "变身",
                    "觉醒",
                    "进化",
                    "变形",
                    "转化",
                    "transform",
                    "evolve",
                    "awakening",
                    "mutate",
                    "shift",
                ]
            )
            result["form_evolution"] = {
                "base_form": "基础可读轮廓，保持实体类型核心身份信号",
                "transformed_form": "变身/觉醒形态" if has_transform else "无变身需求",
                "continuity_locks": ["身份核心", "轮廓关系", "材质/能量逻辑", "识别标记"],
                "forbidden_changes": ["随机物种/材质替换", "无动机形态变化", "丢失身份核心", "装饰性突变"],
            }

        # 注入帅哥美女通道信息
        if beauty_type and not entity_type:
            result["beauty_type"] = beauty_type
            result["beauty_name_cn"] = BEAUTY_PORTRAIT_MAP[beauty_type]["name_cn"]
            result["beauty_aura_options"] = BEAUTY_PORTRAIT_MAP[beauty_type]["aura_options"]
            result["beauty_focus_points"] = BEAUTY_PORTRAIT_MAP[beauty_type]["focus_points"]

        # 风险预判（传入实体类型）
        risk_warnings = self._predict_risks(user_prompt, entity_type)
        # 帅哥美女专属风险
        if beauty_type:
            beauty_risks = self._predict_beauty_risks(beauty_type)
            risk_warnings.extend(beauty_risks)
        # 战斗专属风险
        if combat_ctx and combat_ctx.get("combat_risks"):
            risk_warnings.extend(combat_ctx["combat_risks"])
        if risk_warnings:
            result["risk_warnings"] = risk_warnings
            # 将风险修复关键词合并到负面提示词中
            all_repair = []
            for rw in risk_warnings:
                all_repair.append(rw["advice"])
            repair_neg = ", ".join(all_repair)
            result["negative_prompt"] = self._merge_negative(result.get("negative_prompt", ""), repair_neg)

        return result

    def _postprocess_video_enhance(
        self,
        user_prompt: str,
        brain_text: str,
        entity_type: str | None,
        surface_policy: str | None,
        beauty_type: str | None,
        combat_ctx: dict | None,
    ) -> dict:
        """enhance_video_prompt 的纯计算后处理阶段（无 I/O）。

        同步版与异步版共用此方法，保证业务逻辑一致性。
        """
        result = self._parse_json(brain_text)
        result.setdefault("optimized_prompt", user_prompt)
        result.setdefault("negative_prompt", "")
        result.setdefault("recommended_duration", "5")
        result.setdefault("recommended_fps", 24)

        # 自动匹配视频甜点区（优先：实体专属 > 战斗专属 > 帅哥美女 > 场景模板）
        template = self._match_sweet_spot(user_prompt, "video", entity_type)
        if template:
            base_neg = result.get("negative_prompt", "")
            template_neg = template["negative"]
            result["negative_prompt"] = self._merge_negative(base_neg, template_neg)

            # 始终检查并追加模板 suffix 中缺失的质量关键词
            existing = result["optimized_prompt"].lower()
            suffix_terms = template["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] = result["optimized_prompt"] + ", " + ", ".join(missing[:5])

            result["sweet_spot"] = template["name"]

        # 战斗甜点区叠加
        if combat_ctx and combat_ctx.get("sweet_spot"):
            combat_tpl = combat_ctx["sweet_spot"]
            base_neg = result.get("negative_prompt", "")
            result["negative_prompt"] = self._merge_negative(base_neg, combat_tpl["negative"])
            existing = result["optimized_prompt"].lower()
            suffix_terms = combat_tpl["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] += ", " + ", ".join(missing[:5])
            result["combat_sweet_spot"] = combat_tpl["name"]
            result["combat_type"] = combat_ctx["combat_type"]
            if combat_ctx.get("vfx_colors"):
                result["vfx_palette"] = combat_ctx["vfx_colors"]

        # 帅哥美女视频甜点区叠加（实体未匹配时）
        if beauty_type and not entity_type:
            beauty_tpl = self._match_beauty_sweet_spot(beauty_type, "video")
            if beauty_tpl:
                base_neg = result.get("negative_prompt", "")
                result["negative_prompt"] = self._merge_negative(base_neg, beauty_tpl["negative"])
                existing = result["optimized_prompt"].lower()
                suffix_terms = beauty_tpl["suffix"].split(", ")
                missing = [t for t in suffix_terms if t.lower() not in existing]
                if missing:
                    result["optimized_prompt"] += ", " + ", ".join(missing[:5])
                if "sweet_spot" not in result:
                    result["sweet_spot"] = beauty_tpl["name"]

        # 注入实体类型和表面策略信息
        if entity_type:
            result["entity_type"] = entity_type
            result["surface_policy"] = surface_policy

            # 形态演化控制（非人实体）
            has_transform = any(
                kw in user_prompt.lower()
                for kw in [
                    "变身",
                    "觉醒",
                    "进化",
                    "变形",
                    "转化",
                    "transform",
                    "evolve",
                    "awakening",
                    "mutate",
                    "shift",
                ]
            )
            result["form_evolution"] = {
                "base_form": "基础可读轮廓，保持实体类型核心身份信号",
                "transformed_form": "变身/觉醒形态" if has_transform else "无变身需求",
                "continuity_locks": ["身份核心", "轮廓关系", "材质/能量逻辑", "识别标记"],
                "forbidden_changes": ["随机物种/材质替换", "无动机形态变化", "丢失身份核心", "装饰性突变"],
            }

        # 注入帅哥美女视频通道信息
        if beauty_type and not entity_type:
            result["beauty_type"] = beauty_type
            result["beauty_name_cn"] = BEAUTY_PORTRAIT_MAP[beauty_type]["name_cn"]
            result["production_route"] = BEAUTY_PRODUCTION_RULES["video"]["default_route"]
            result["i2v_strength_recommendation"] = BEAUTY_PRODUCTION_RULES["video"]["i2v_strength"]

        # 风险预判（传入实体类型）
        risk_warnings = self._predict_risks(user_prompt, entity_type)
        # 帅哥美女专属风险
        if beauty_type:
            beauty_risks = self._predict_beauty_risks(beauty_type)
            risk_warnings.extend(beauty_risks)
        # 战斗专属风险
        if combat_ctx and combat_ctx.get("combat_risks"):
            risk_warnings.extend(combat_ctx["combat_risks"])
        if risk_warnings:
            result["risk_warnings"] = risk_warnings
            all_repair = []
            for rw in risk_warnings:
                all_repair.append(rw["advice"])
            repair_neg = ", ".join(all_repair)
            result["negative_prompt"] = self._merge_negative(result.get("negative_prompt", ""), repair_neg)

        return result

    def entity_graft(self, user_prompt: str, target_entity: str = "auto") -> dict:
        """实体嫁接：将人类角色描述转化为非人实体

        来源：新烬龙V2 creative-leap.md Entity Grafting + thinking-engine.js

        护栏：嫁接不能是装饰性的——新形态必须改善钩子、主题、动作可读性或视觉回报

        Args:
            user_prompt: 用户原始描述
            target_entity: 嫁接目标类型，可选：
                mechanical_body/energy_form/digital_avatar/mythical_beast/
                symbiotic_organism/shadow_entity/liquid_metal/crystalline_being/auto
                "auto" 时由系统根据内容自动选择最匹配的嫁接目标
        Returns:
            嫁接结果 dict，包含新实体描述、连续性锁、护栏检查
        """
        # 自动选择嫁接目标
        if target_entity == "auto":
            p = user_prompt.lower()
            if any(kw in p for kw in ["机械", "机器", "metal", "mech", "cyborg"]):
                target_entity = "mechanical_body"
            elif any(kw in p for kw in ["能量", "光", "energy", "light", "flame"]):
                target_entity = "energy_form"
            elif any(kw in p for kw in ["全息", "数字", "虚拟", "hologram", "digital", "virtual"]):
                target_entity = "digital_avatar"
            elif any(kw in p for kw in ["神话", "龙", "兽", "beast", "dragon", "myth"]):
                target_entity = "mythical_beast"
            elif any(kw in p for kw in ["共生", "拟人", "symbiotic", "anthro"]):
                target_entity = "symbiotic_organism"
            elif any(kw in p for kw in ["暗影", "影", "shadow", "dark"]):
                target_entity = "shadow_entity"
            elif any(kw in p for kw in ["液态", "流体", "liquid", "flow"]):
                target_entity = "liquid_metal"
            elif any(kw in p for kw in ["晶体", "水晶", "crystal", "crystalline"]):
                target_entity = "crystalline_being"
            else:
                target_entity = "shadow_entity"  # 默认嫁接为暗影实体（最通用的非人化）

        graft_info = GRAFT_TARGETS.get(target_entity, GRAFT_TARGETS["shadow_entity"])
        resolved_entity_type = graft_info["target_entity"]

        # 构建嫁接提示词
        graft_prompt = f"""你是一个创意实体嫁接专家。将以下人类角色描述转化为{graft_info["name_cn"]}实体。

嫁接目标：{graft_info["name_cn"]}({target_entity})
嫁接描述：{graft_info["description"]}
表面材质策略：{ENTITY_TYPE_MAP[resolved_entity_type]["surface_policy"]}

原始描述：{user_prompt}

输出JSON（不要markdown代码块，直接输出JSON）：
{{
    "grafted_prompt": "嫁接后的英文提示词描述（50-100词，保持故事功能可读）",
    "entity_type": "{resolved_entity_type}",
    "surface_material": "表面材质描述（皮毛/金属/能量/全息等）",
    "identity_core": "保留的身份核心特征（至少3个）",
    "continuity_locks": ["连续性约束1", "连续性约束2", "连续性约束3"],
    "forbidden_changes": ["禁止变异1", "禁止变异2"],
    "story_function": "嫁接后的故事功能说明",
    "visual_payoff": "视觉回报说明",
    "graft_safety": "safe|risky|decorative（仅safe可自动使用）"
}}

嫁接规则：
1. 保持故事功能可读性——目标、冲突、压力、转折、回报必须保持清晰
2. 新形态必须改善钩子、主题、动作可读性或视觉回报
3. 禁止装饰性嫁接（仅改变外观但不改善故事表达）
4. 保留原始角色的身份核心信号（如眼神语言、轮廓节奏、核心符号）
5. 新表面材质必须与实体类型逻辑一致
"""

        text = self._ask_brain(graft_prompt, user_prompt, temperature=0.7)
        result = self._parse_json(text)
        result.setdefault("grafted_prompt", user_prompt)
        result.setdefault("entity_type", resolved_entity_type)
        result.setdefault("graft_target", target_entity)
        result.setdefault("graft_name_cn", graft_info["name_cn"])
        result.setdefault("surface_policy", ENTITY_TYPE_MAP[resolved_entity_type]["surface_policy"])
        result.setdefault("story_function", "")
        result.setdefault("visual_payoff", "")
        result.setdefault("graft_safety", "safe")

        # 护栏检查：如果嫁接安全性为decorative，添加警告
        if result.get("graft_safety") == "decorative":
            result["graft_warning"] = "⚠ 嫁接被判为装饰性（不影响故事表达），建议回退到原形态"
        elif result.get("graft_safety") == "risky":
            result["graft_warning"] = "⚠ 嫁接有连续性风险，需人工确认"

        # 使用实体专属甜点区增强嫁接结果
        template = self._match_sweet_spot(result["grafted_prompt"], "image", resolved_entity_type)
        if template:
            result["sweet_spot"] = template["name"]
            result.setdefault("negative_prompt", "")
            result["negative_prompt"] = self._merge_negative(result.get("negative_prompt", ""), template["negative"])

        return result
