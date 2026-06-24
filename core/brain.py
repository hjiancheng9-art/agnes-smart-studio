"""智能大脑 - 意图识别、Prompt增强、分镜生成"""

import json

from .async_client import AsyncCruxClient
from .brain_data import (
    ANTI_PATTERN_MAP,
    BEAUTY_NEGATIVE_REPAIR_MAP,
    BEAUTY_PORTRAIT_MAP,
    BEAUTY_PRODUCTION_RULES,
    BEAUTY_SWEET_SPOT_TEMPLATES,
    COMBAT_MOVE_INDEX,
    COMBAT_MOVE_TEMPLATES,
    COMBAT_NEGATIVE_REPAIR_MAP,
    COMBAT_SWEET_SPOT_TEMPLATES,
    COMBAT_VFX_PALETTES,
    CREATIVE_DOMAIN_MAP,
    CREATIVE_LEAP_PROMPT,
    ENHANCE_IMAGE_PROMPT,
    ENHANCE_VIDEO_PROMPT,
    ENTITY_NEGATIVE_REPAIR_MAP,
    ENTITY_SWEET_SPOT_TEMPLATES,
    ENTITY_TYPE_MAP,
    GRAFT_TARGETS,
    IMAGE_EDIT_PROMPT,
    INTENT_PROMPT,
    NEGATIVE_REPAIR_MAP,
    NONHUMAN_COMBAT_MOTIF,
    NONHUMAN_VIDEO_RULES,
    STORYBOARD_PROMPT,
    SWEET_SPOT_TEMPLATES,
    SWEET_SPOT_VIDEO_TEMPLATES,
    THINKING_METHOD_MAP,
)
from .client import CruxClient

__all__ = ["SmartBrain", "AsyncSmartBrain"]


class SmartBrain:
    """智能大脑：意图识别 + Prompt增强 + 分镜生成"""

    def __init__(self, client: CruxClient) -> None:
        self.client = client

    def _ask_brain(self, system_prompt: str, user_input: str, temperature: float = 0.7) -> str:
        """调用文本模型（自动使用当前激活的供应商）"""
        model = self._get_model()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        result = self.client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        try:
            msg = result["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content")
        except (KeyError, IndexError):
            raise RuntimeError(f"Brain API返回格式异常: {str(result)[:200]}") from None
        if not content:
            raise RuntimeError(f"Brain 返回内容为空: {str(result)[:300]}")
        # 尝试提取JSON（可能被包裹在```json中）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content

    def _get_model(self) -> str:
        """获取当前激活供应商的模型 ID"""
        try:
            from core.provider import get_provider_manager
            mgr = get_provider_manager()
            mgr.load()
            return mgr.get_model("pro")
        except (OSError, ValueError, RuntimeError):
            return "agnes-2.0-flash"  # fallback

    def _parse_json(self, text: str) -> dict:
        """安全解析JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到JSON部分
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {"raw_text": text}

    def recognize_intent(self, user_input: str) -> dict:
        """识别用户意图"""
        text = self._ask_brain(INTENT_PROMPT, user_input, temperature=0.3)
        result = self._parse_json(text)
        # 确保必要字段存在
        result.setdefault("intent", "text_to_image")
        result.setdefault("confidence", 0.5)
        result.setdefault("plan", user_input)
        result.setdefault("has_image_input", False)
        result.setdefault("wants_video", False)
        result.setdefault("wants_editing", False)
        return result

    def enhance_image_prompt(self, user_prompt: str, style: str | None = None) -> dict:
        """增强图片生成Prompt，自动匹配甜点区模板 + 实体感知 + 帅哥美女通道 + 战斗知识 + 风险预判"""
        # 推断实体类型
        entity_type, surface_policy = self._infer_entity_type(user_prompt)

        # 推断帅哥美女类型
        beauty_type = self._infer_beauty_type(user_prompt)

        # 检测战斗场景
        combat_ctx = self._detect_combat_scene(user_prompt, "image")

        # 构建LLM输入
        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                         f"表面策略：{surface_policy}]\n原始描述：{user_prompt}")
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            angle_rules_str = "\n".join(
                f"  {angle}: {rule}"
                for angle, rule in beauty_info["angle_rules"].items()
            )
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[多角度规则：\n{angle_rules_str}]\n"
                f"[可用气质：{', '.join(beauty_info['aura_options'])}]\n"
                f"[禁止：模板脸、空泛形容词、出招姿势、硬摆拍、夸张武打体态]\n"
                f"原始描述：{user_prompt}"
            )
        # 战斗场景注入（优先级低于实体/美女，高于通用）
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['image_prompt_hints']}\n原始描述：{user_prompt}"

        # 创意知识注入（CREATIVE_DOMAIN_MAP/ANTI_PATTERN_MAP/THINKING_METHOD_MAP 激活）
        # 仅对通用场景（非战斗、非美女）注入跨域参考元素，为LLM提供更多灵感
        if not combat_ctx and not beauty_type:
            creative_ctx = self._resolve_creative_knowledge(user_prompt, "image")
            if creative_ctx and creative_ctx.get("image_prompt_hints"):
                input_text = f"{creative_ctx['image_prompt_hints']}\n原始描述：{input_text}"

        if style:
            input_text = f"风格要求：{style}\n{input_text}"

        # 注入历史成功案例，让增强器持续进化
        try:
            from utils.memory import build_evolution_context
            evo_ctx = build_evolution_context("image")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except (OSError, ValueError, RuntimeError):
            pass

        text = self._ask_brain(ENHANCE_IMAGE_PROMPT, input_text)
        return self._postprocess_image_enhance(
            user_prompt, text, entity_type, surface_policy, beauty_type, combat_ctx
        )

    def _postprocess_image_enhance(
        self, user_prompt: str, brain_text: str,
        entity_type: str | None, surface_policy: str | None,
        beauty_type: str | None, combat_ctx: dict | None,
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
            has_transform = any(kw in user_prompt.lower() for kw in
                               ["变身", "觉醒", "进化", "变形", "转化",
                                "transform", "evolve", "awakening", "mutate", "shift"])
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
            result["negative_prompt"] = self._merge_negative(
                result.get("negative_prompt", ""), repair_neg
            )

        return result

    def enhance_video_prompt(self, user_prompt: str) -> dict:
        """增强视频生成Prompt，自动匹配甜点区模板 + 实体感知 + 帅哥美女通道 + 战斗知识 + 风险预判"""
        # 推断实体类型
        entity_type, surface_policy = self._infer_entity_type(user_prompt)

        # 推断帅哥美女类型
        beauty_type = self._infer_beauty_type(user_prompt)

        # 检测战斗场景
        combat_ctx = self._detect_combat_scene(user_prompt, "video")

        # 构建LLM输入
        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                         f"表面策略：{surface_policy}]\n原始描述：{user_prompt}")
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[视频生产路由：逐镜 compact，I2V strength 0.70-0.72]\n"
                f"[允许动作：眼神、呼吸、轻微转头、整理衣领]\n"
                f"[禁止：出招姿势、硬摆拍、夸张武打体态、多镜头切换]\n"
                f"原始描述：{user_prompt}"
            )
        # 战斗场景注入（优先级低于实体/美女，高于通用）
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['video_prompt_hints']}\n原始描述：{user_prompt}"

        # 非人实体视频规则注入（NONHUMAN_VIDEO_RULES 知识激活）
        if entity_type and not beauty_type:
            creative_ctx = self._resolve_creative_knowledge(user_prompt, "video")
            if creative_ctx and creative_ctx.get("nonhuman_video_ctx"):
                i2v = creative_ctx["nonhuman_video_ctx"]["i2v_first_frame"]
                specs = creative_ctx["nonhuman_video_ctx"]["sweet_spot_specs"]
                pipeline = creative_ctx["nonhuman_video_ctx"]["prompt_assembly_pipeline"]
                nonhuman_video_hints = (
                    f"[非人实体视频规则]\n"
                    f"I2V首帧限制：{i2v['max_allowed']}\n"
                    f"适合动作：{', '.join(i2v['suitable_actions'][:4])}\n"
                    f"不适合动作：{', '.join(i2v['unsuitable_actions'][:4])}\n"
                    f"设计锁定：{i2v['design_lock_template']}\n"
                    f"甜点区方法：{specs['default_method']}，禁止：{', '.join(specs['forbidden'])}\n"
                    f"组装流水线：{' → '.join(pipeline['steps'])}"
                )
                input_text = f"{nonhuman_video_hints}\n原始描述：{input_text}"

        # 注入历史成功案例，让视频增强也持续进化
        try:
            from utils.memory import build_evolution_context
            evo_ctx = build_evolution_context("video")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except (OSError, RuntimeError, ConnectionError):
            pass

        text = self._ask_brain(ENHANCE_VIDEO_PROMPT, input_text)
        return self._postprocess_video_enhance(
            user_prompt, text, entity_type, surface_policy, beauty_type, combat_ctx
        )

    def _postprocess_video_enhance(
        self, user_prompt: str, brain_text: str,
        entity_type: str | None, surface_policy: str | None,
        beauty_type: str | None, combat_ctx: dict | None,
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
            has_transform = any(kw in user_prompt.lower() for kw in
                               ["变身", "觉醒", "进化", "变形", "转化",
                                "transform", "evolve", "awakening", "mutate", "shift"])
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
            result["negative_prompt"] = self._merge_negative(
                result.get("negative_prompt", ""), repair_neg
            )

        return result

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
            "战斗", "招式", "打斗", "格斗", "连招", "必杀", "技能", "combo", "ultimate",
            "fight", "combat", "battle", "martial", "strike", "punch", "kick", "attack",
            "波动拳", "升龙", "fireball", "hadoken", "shoryuken",
            "剑", "刀", "枪", "斧", "弓", "箭", "魔法", "法术",
            "火焰", "雷电", "冰", "暗影", "能量", "气功", "飞行道具",
            "龙", "忍者", "武士", "战士", "法师", "刺客",
            "斩", "劈", "刺", "砸", "旋风", "冲击波",
            # 扩展：更多动作/招式关键词
            "爪", "抓", "投", "摔", "踢", "拳", "掌", "指",
            "连击", "打击", "上勾", "冲拳", "飞踢", "铲腿",
            "变身", "觉醒", "超必杀", "终极技", "元素爆发",
            "升龙拳", "波动拳", "葵花", "荒咬", "大蛇薙", "鬼烧",
            "天星", "龙刃", "瞬狱", "狂风", "剑刃",
            # 扩展：角色名（确保含角色名的描述也能触发）
            "八神", "草薙", "隆", "肯", "春丽", "盖尔",
            "蝎子", "零度", "源氏", "半藏",
            "李白", "貂蝉", "孙悟空", "安琪拉", "韩信",
            "亚索", "拉克丝", "劫", "金克丝",
            "钟离", "雷电将军", "胡桃",
            "法师", "战士", "德鲁伊",
            # 扩展：网游/MOBA类
            "大招", "一技能", "二技能", "三技能",
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
                        "ryu": "隆", "ken": "肯", "chunli": "春丽", "guile": "盖尔",
                        "kyo": "草薙京", "iori": "八神", "kazuya": "一八", "jin": "风间仁",
                        "scorpion": "蝎子", "subzero": "绝对零度",
                        "libai": "李白", "diaochan": "貂蝉", "wukong": "孙悟空",
                        "angela": "安琪拉", "hanxin": "韩信",
                        "yasuo": "亚索", "lux": "拉克丝", "zed": "劫", "jinx": "金克丝",
                        "mage": "法师", "warrior": "战士", "druid": "德鲁伊",
                        "genji": "源氏", "dva": "D.Va", "hanzo": "半蔵",
                        "zhongli": "钟离", "raiden_shogun": "雷电将军", "hutao": "胡桃",
                    }
                    if char_key in char_name_map and char_name_map[char_key] in p:
                        score += 5

                    if score >= 3:
                        results.append({
                            "move_id": f"{series_key}.{char_key}.{move_key}",
                            "name_cn": move["name_cn"],
                            "type": move.get("type", ""),
                            "prompt_cn": move["prompt_cn"],
                            "prompt_en": move["prompt_en"],
                            "phases": move["phases"],
                            "vfx_palette": move.get("vfx_palette", ""),
                            "camera": move.get("camera", ""),
                            "score": score,
                        })

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
            "飞行道具": "projectile", "飞行道具(冻结)": "projectile",
            "对空技": "anti_air", "对空技(火焰)": "anti_air",
            "旋转突进": "spinning", "旋转上升": "spinning",
            "连续打击": "rapid_strikes", "连续打击(紫焰)": "rapid_strikes",
            "投技": "grapple", "远程抓取": "grapple", "指令投": "grapple",
            "超必杀": "super_move", "超必杀(火柱)": "super_move",
            "超必杀(狂乱连击)": "super_move", "超必杀(AOE毁灭)": "super_move",
            "终极技(AOE击飞)": "super_move", "终极技(多段AOE)": "super_move",
            "终极技(领域展开)": "super_move", "终极技(火焰激光)": "super_move",
            "终极技(枪舞)": "super_move", "终极技(空中连斩)": "super_move",
            "终极技(全图激光)": "super_move", "终极技(暗影刺杀)": "super_move",
            "终极技(全图火箭)": "super_move", "终极技(近战爆发)": "super_move",
            "终极技(贯穿双龙)": "super_move",
            "元素爆发(陨石)": "super_move", "元素爆发(空间撕裂斩)": "super_move",
            "元素爆发(火焰幽灵)": "super_move",
            "突进上勾拳(雷电)": "rapid_strikes",
            "突进飞踢": "spinning", "滑行铲腿": "spinning",
            "三段位移": "rapid_strikes", "派生连击(火焰)": "rapid_strikes",
            "核心输出(大型火球)": "projectile", "位移": "spinning",
            "AOE终结(旋风)": "spinning", "AOE终极(星雨)": "super_move",
            "下段拳击(雷电)": "rapid_strikes", "地面火焰": "super_move",
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
        combat_risks.append({
            "risk": "missing_vfx",
            **COMBAT_NEGATIVE_REPAIR_MAP["missing_vfx"],
        })
        combat_risks.append({
            "risk": "floaty_action",
            **COMBAT_NEGATIVE_REPAIR_MAP["floaty_action"],
        })
        # 飞行道具 → 额外：wrong_energy_color
        if combat_type == "projectile":
            combat_risks.append({
                "risk": "wrong_energy_color",
                **COMBAT_NEGATIVE_REPAIR_MAP["wrong_energy_color"],
            })
        # 连续打击/旋转 → wrong_pose_sequence + broken_timing
        if combat_type in ("rapid_strikes", "spinning"):
            combat_risks.append({
                "risk": "wrong_pose_sequence",
                **COMBAT_NEGATIVE_REPAIR_MAP["wrong_pose_sequence"],
            })
            combat_risks.append({
                "risk": "broken_timing",
                **COMBAT_NEGATIVE_REPAIR_MAP["broken_timing"],
            })
        # 超必杀 → missing_impact + broken_timing
        if combat_type == "super_move":
            combat_risks.append({
                "risk": "missing_impact",
                **COMBAT_NEGATIVE_REPAIR_MAP["missing_impact"],
            })
            combat_risks.append({
                "risk": "broken_timing",
                **COMBAT_NEGATIVE_REPAIR_MAP["broken_timing"],
            })
        # 投技 → missing_impact
        if combat_type == "grapple":
            combat_risks.append({
                "risk": "missing_impact",
                **COMBAT_NEGATIVE_REPAIR_MAP["missing_impact"],
            })

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
            move_hints.append(
                f"  · {ref['name_cn']}({ref['move_id']}): {ref['prompt_en']}"
            )
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

    def _infer_entity_type(self, prompt: str) -> tuple[str | None, str | None]:
        """根据提示词推断非人实体类型

        来源：新烬龙V2 common.js inferPrimaryCharacterEntity()

        Args:
            prompt: 用户原始提示词
        Returns:
            (entity_type, surface_policy) — entity_type为None表示human_or_humanoid
        """
        p = prompt.lower()
        # 按优先级遍历ENTITY_TYPE_MAP
        for entity_type, info in ENTITY_TYPE_MAP.items():
            for kw in info["keywords"]:
                if kw in p:
                    return entity_type, info["surface_policy"]
        return None, None

    def _infer_beauty_type(self, prompt: str) -> str | None:
        """根据提示词推断帅哥/美女类型

        来源：新烬龙V2 character-clothing.md 帅哥美女独立通道

        Args:
            prompt: 用户原始提示词
        Returns:
            "handsome" | "beauty" | None
        """
        p = prompt.lower()
        handsome_score = 0
        beauty_score = 0

        for kw in BEAUTY_PORTRAIT_MAP["handsome"]["keywords"]:
            if kw in p:
                if kw in ("帅哥美女", "高颜值"):
                    handsome_score += 1
                    beauty_score += 1
                else:
                    handsome_score += 2

        for kw in BEAUTY_PORTRAIT_MAP["beauty"]["keywords"]:
            if kw in p:
                if kw in ("帅哥美女", "高颜值"):
                    continue
                beauty_score += 2

        if handsome_score >= 2 and handsome_score > beauty_score:
            return "handsome"
        if beauty_score >= 2 and beauty_score > handsome_score:
            return "beauty"
        if handsome_score >= 2 and beauty_score >= 2:
            gender_hints_male = ["男", "他", "boy", "man", "male", "guy", "先生", "少年"]
            gender_hints_female = ["女", "她", "girl", "woman", "female", "lady", "小姐", "少女"]
            if any(h in p for h in gender_hints_male) and not any(h in p for h in gender_hints_female):
                return "handsome"
            if any(h in p for h in gender_hints_female) and not any(h in p for h in gender_hints_male):
                return "beauty"
        return None

    def _match_sweet_spot(self, prompt: str, mode: str = "image", entity_type: str | None = None) -> dict | None:
        """根据提示词关键词自动匹配甜点区模板

        优先匹配实体专属甜点区，再回退到场景甜点区

        Args:
            prompt: 用户原始提示词
            mode: "image" 或 "video"
            entity_type: 已推断的非人实体类型（可选，若提供则优先使用）
        Returns:
            匹配到的模板 dict 或 None
        """
        p = prompt.lower()

        # 1. 优先匹配实体专属甜点区
        if entity_type and entity_type in ENTITY_SWEET_SPOT_TEMPLATES:
            entity_tpl = ENTITY_SWEET_SPOT_TEMPLATES[entity_type]
            mode_tpl = entity_tpl.get(mode)
            if mode_tpl:
                return {
                    "name": f"{ENTITY_TYPE_MAP[entity_type]['name_cn']}({entity_type})",
                    "suffix": mode_tpl["suffix"],
                    "negative": mode_tpl["negative"],
                    "entity_type": entity_type,
                    "surface_policy": ENTITY_TYPE_MAP[entity_type]["surface_policy"],
                }

        # 2. 自动推断实体类型（如果未提供）
        if not entity_type:
            entity_type, _ = self._infer_entity_type(prompt)
            if entity_type and entity_type in ENTITY_SWEET_SPOT_TEMPLATES:
                entity_tpl = ENTITY_SWEET_SPOT_TEMPLATES[entity_type]
                mode_tpl = entity_tpl.get(mode)
                if mode_tpl:
                    return {
                        "name": f"{ENTITY_TYPE_MAP[entity_type]['name_cn']}({entity_type})",
                        "suffix": mode_tpl["suffix"],
                        "negative": mode_tpl["negative"],
                        "entity_type": entity_type,
                        "surface_policy": ENTITY_TYPE_MAP[entity_type]["surface_policy"],
                    }

        # 2.5 帅哥美女甜点区（实体未匹配时）
        if not entity_type:
            beauty_type = self._infer_beauty_type(prompt)
            if beauty_type:
                beauty_tpl = self._match_beauty_sweet_spot(beauty_type, mode)
                if beauty_tpl:
                    return beauty_tpl

        # 3. 回退到原有场景甜点区匹配
        # 关键词匹配规则
        person_keywords = ["人", "女", "男", "girl", "boy", "woman", "man", "lady",
                           "美女", "帅哥", "portrait", "face", "人物", "少女", "少年",
                           "lady", "miss", "mr", "角色", "character"]
        full_body_keywords = ["全身", "站", "走", "跑", "跳", "standing", "walking",
                              "running", "full body", "跳舞", "dancing", "姿势", "pose"]
        action_keywords = ["打", "战", "打斗", "fight", "battle", "action", "追逐",
                           "chase", "武术", "martial", "鞭", "whip", "sword", "挥",
                           "attack", "kick", "punch"]
        animal_keywords = ["猫", "狗", "鸟", "鱼", "虎", "龙", "马", "动物",
                           "cat", "dog", "bird", "fish", "tiger", "dragon", "horse",
                           "animal", "lion", "wolf", "bear", "rabbit", "snake"]
        landscape_keywords = ["山", "海", "湖", "天空", "日落", "城市", "风景",
                              "mountain", "ocean", "sea", "lake", "sky", "sunset",
                              "city", "landscape", "forest", "沙漠", "desert"]
        food_keywords = ["美食", "蛋糕", "甜品", "食物", "菜", "汤", "咖啡",
                         "food", "cake", "dessert", "soup", "coffee", "tea", "meal"]
        anime_keywords = ["动漫", "二次元", "anime", "manga", "2.5d", "赛璐",
                          "日系", "卡通人物"]

        # 按优先级匹配
        if mode == "video":
            templates = SWEET_SPOT_VIDEO_TEMPLATES
            if any(k in p for k in action_keywords):
                result = templates["action_video"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in person_keywords):
                if any(k in p for k in full_body_keywords):
                    result = templates["action_video"]
                    return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
                result = templates["portrait_video"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            result = templates["camera_pan"]
            return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
        else:
            if any(k in p for k in anime_keywords):
                result = SWEET_SPOT_TEMPLATES["anime"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in action_keywords):
                result = SWEET_SPOT_TEMPLATES["action"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in full_body_keywords):
                result = SWEET_SPOT_TEMPLATES["full_body"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in person_keywords):
                result = SWEET_SPOT_TEMPLATES["portrait"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in animal_keywords):
                result = SWEET_SPOT_TEMPLATES["animal"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in food_keywords):
                result = SWEET_SPOT_TEMPLATES["food"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in landscape_keywords):
                result = SWEET_SPOT_TEMPLATES["landscape"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}

        return None

    def _predict_risks(self, prompt: str, entity_type: str | None = None) -> list[dict]:
        """根据提示词预判可能的失败风险，返回预防性修复建议

        Args:
            prompt: 用户原始提示词
            entity_type: 已推断的非人实体类型（可选）
        Returns:
            [{"risk": "风险类型", "symptoms": ["可能现象"], "advice": "修复关键词"}, ...]
        """
        p = prompt.lower()
        risks = []

        # ── 实体专属风险（优先） ──
        if entity_type and entity_type in ENTITY_NEGATIVE_REPAIR_MAP:
            for risk_id, risk_info in ENTITY_NEGATIVE_REPAIR_MAP[entity_type].items():
                risks.append({"risk": f"{entity_type}_{risk_id}",
                              "symptoms": risk_info["symptoms"],
                              "advice": risk_info["repair_keywords"]})

        # ── 通用风险 ──
        # 人物相关 → 解剖失败 + 穿模风险
        person_kw = ["人", "女", "男", "girl", "boy", "woman", "man", "face",
                      "portrait", "人物", "少女", "少年", "角色", "character",
                      "美女", "帅哥", "模特", "model"]
        if any(k in p for k in person_kw):
            risks.append({"risk": "anatomy_failure",
                          "symptoms": NEGATIVE_REPAIR_MAP["anatomy_failure"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["anatomy_failure"]["repair_keywords"]})
            risks.append({"risk": "penetration",
                          "symptoms": NEGATIVE_REPAIR_MAP["penetration"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["penetration"]["repair_keywords"]})
        # 动作/打斗 → 穿模风险 + 视频不稳定
        action_kw = ["动作", "fight", "battle", "action", "attack", "打", "战",
                      "打斗", "追逐", "chase", "武术", "martial", "kick", "punch",
                      "跑", "跳", "挥", "舞", "dancing"]
        if any(k in p for k in action_kw):
            if not any(r["risk"] == "penetration" for r in risks):
                risks.append({"risk": "penetration",
                              "symptoms": NEGATIVE_REPAIR_MAP["penetration"]["symptoms"],
                              "advice": NEGATIVE_REPAIR_MAP["penetration"]["repair_keywords"]})
            risks.append({"risk": "video_instability",
                          "symptoms": NEGATIVE_REPAIR_MAP["video_instability"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["video_instability"]["repair_keywords"]})
        # 背景/场景 → 文字漂移风险
        scene_kw = ["背景", "场景", "landscape", "background", "城市", "风景",
                     "city", "mountain", "ocean", "sea", "forest", "天空", "街",
                     "street", "building", "室内", "indoor", "room"]
        if any(k in p for k in scene_kw):
            risks.append({"risk": "text_drift",
                          "symptoms": NEGATIVE_REPAIR_MAP["text_drift"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["text_drift"]["repair_keywords"]})
        # 光照关键词 → 过曝/欠曝风险
        light_kw = ["light", "光照", "阳光", "sun", "影", "shadow", "亮",
                     "暗", "dark", "bright", "闪光", "flash"]
        if any(k in p for k in light_kw):
            risks.append({"risk": "too_bright",
                          "symptoms": NEGATIVE_REPAIR_MAP["too_bright"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["too_bright"]["repair_keywords"]})
        return risks

    def _match_beauty_sweet_spot(self, beauty_type: str, mode: str = "image") -> dict | None:
        """匹配帅哥/美女专属甜点区模板

        Args:
            beauty_type: "handsome" 或 "beauty"
            mode: "image" 或 "video"
        Returns:
            匹配到的模板 dict 或 None
        """
        if beauty_type in BEAUTY_SWEET_SPOT_TEMPLATES:
            mode_tpl = BEAUTY_SWEET_SPOT_TEMPLATES[beauty_type].get(mode)
            if mode_tpl:
                return {
                    "name": f"{BEAUTY_PORTRAIT_MAP[beauty_type]['name_cn']}({beauty_type})",
                    "suffix": mode_tpl["suffix"],
                    "negative": mode_tpl["negative"],
                }
        return None

    def _predict_beauty_risks(self, beauty_type: str) -> list[dict]:
        """帅哥美女专属风险预判

        Args:
            beauty_type: "handsome" 或 "beauty"
        Returns:
            [{"risk": "风险类型", "symptoms": [...], "advice": "修复关键词"}, ...]
        """
        risks = []
        if beauty_type in BEAUTY_NEGATIVE_REPAIR_MAP:
            for risk_id, risk_info in BEAUTY_NEGATIVE_REPAIR_MAP[beauty_type].items():
                risks.append({
                    "risk": f"{beauty_type}_{risk_id}",
                    "symptoms": risk_info["symptoms"],
                    "advice": risk_info["repair_keywords"],
                })
        return risks

    @staticmethod
    def _merge_negative(*negative_strings: str) -> str:
        """合并多个负面提示词字符串，去重"""
        all_terms = set()
        for ns in negative_strings:
            if not ns:
                continue
            for term in ns.split(","):
                term = term.strip().lower()
                if term:
                    all_terms.add(term)
        return ", ".join(sorted(all_terms))

    def understand_image(self, question: str, image_url: str) -> str:
        """利用 1.5-flash 多模态能力理解图片"""
        result = self.client.chat_multimodal(
            text=question,
            image_url=image_url,
            model="agnes-1.5-flash",
            temperature=0.3,
            max_tokens=1024,
        )
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"多模态API返回格式异常: {str(result)[:200]}") from None

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
        graft_prompt = f"""你是一个创意实体嫁接专家。将以下人类角色描述转化为{graft_info['name_cn']}实体。

嫁接目标：{graft_info['name_cn']}({target_entity})
嫁接描述：{graft_info['description']}
表面材质策略：{ENTITY_TYPE_MAP[resolved_entity_type]['surface_policy']}

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
            result["negative_prompt"] = self._merge_negative(
                result.get("negative_prompt", ""), template["negative"]
            )

        return result

    def _resolve_creative_knowledge(self, prompt: str, mode: str = "image") -> dict:
        """创意知识路由器 — 一次性解析所有V2创意知识常量为结构化上下文

        激活5个曾经死掉的知识常量：
        - CREATIVE_DOMAIN_MAP  → 跨域嫁接候选元素
        - ANTI_PATTERN_MAP     → 可施加的反模式 + prompt_formula
        - THINKING_METHOD_MAP  → 匹配的思维技法详情
        - NONHUMAN_COMBAT_MOTIF → 非人战斗母题（反差感/荒诞感）
        - NONHUMAN_VIDEO_RULES  → 非人视频生产规则

        供 creative_leap / enhance_video_prompt / _detect_combat_scene 共用。

        Args:
            prompt: 用户原始提示词
            mode: "image" 或 "video"
        Returns:
            创意知识上下文 dict
        """
        p = prompt.lower()
        entity_type, _ = self._infer_entity_type(prompt)
        is_nonhuman = entity_type is not None

        # ── 1. 从 CREATIVE_DOMAIN_MAP 解析跨域嫁接候选 ──
        domain_candidates = {}
        for domain_key, domain_items in CREATIVE_DOMAIN_MAP.items():
            candidates = []
            if isinstance(domain_items, dict):
                for item_key, item_val in domain_items.items():
                    if isinstance(item_val, dict):
                        name = item_val.get("name_cn", item_key)
                        examples = item_val.get("examples", item_val.get("visual_traits", ""))
                        candidates.append(f"{name}({item_key}): {examples}")
                    else:
                        candidates.append(f"{item_val}({item_key})")
            domain_candidates[domain_key] = candidates

        # 根据提示词匹配各域最相关的元素
        matched_domain_elements = {}
        for domain_key, items in CREATIVE_DOMAIN_MAP.items():
            hits = []
            if isinstance(items, dict):
                for item_key, item_val in items.items():
                    if isinstance(item_val, dict):
                        name = item_val.get("name_cn", item_key)
                        examples = item_val.get("examples", item_val.get("visual_traits", ""))
                        # 检查关键词匹配
                        check_text = f"{name} {examples} {item_key}".lower()
                        prompt_words = [w for w in p.split() if len(w) > 1]
                        if any(w in check_text for w in prompt_words):
                            hits.append({"key": item_key, "name_cn": name, "examples": examples})
            if hits:
                matched_domain_elements[domain_key] = hits

        # ── 2. 从 ANTI_PATTERN_MAP 解析反模式 ──
        matched_anti_patterns = []
        anti_pattern_keywords = {
            "category_error": ["类别", "错误", "框架", "category", "framework"],
            "scale_singularity": ["尺度", "极端", "无限", "微观", "宏大", "scale", "extreme", "infinite"],
            "time_slice": ["时间", "同时", "过去", "未来", "time", "simultaneous", "past", "future"],
            "material_paradox": ["材料", "悖论", "背叛", "material", "paradox", "opposite"],
            "causal_inversion": ["因果", "倒置", "结果先于", "causal", "inversion", "reverse"],
            "dimension_fold": ["维度", "折叠", "2D", "3D", "dimension", "fold"],
        }
        for ap_key, ap_info in ANTI_PATTERN_MAP.items():
            # 始终包含所有反模式供LLM选用
            matched_anti_patterns.append({
                "key": ap_key,
                "name_cn": ap_info["name_cn"],
                "core_operation": ap_info["core_operation"],
                "example": ap_info["example"],
                "visual_impact": ap_info["visual_impact"],
                "prompt_formula": ap_info["prompt_formula"],
                "relevance": 2 if any(kw in p for kw in anti_pattern_keywords.get(ap_key, [])) else 0,
            })
        matched_anti_patterns.sort(key=lambda x: x["relevance"], reverse=True)

        # ── 3. 从 THINKING_METHOD_MAP 解析思维技法 ──
        matched_methods = self._select_creative_methods(prompt)
        resolved_methods = []
        for method_id in matched_methods:
            if method_id == "cross_domain_graft" and "action" in CREATIVE_DOMAIN_MAP:
                # 跨域嫁接 — 从 CREATIVE_DOMAIN_MAP 取四域
                resolved_methods.append({
                    "id": "cross_domain_graft",
                    "name_cn": "跨域嫁接",
                    "domains": {
                        "action": [f"{v.get('name_cn', k)}" for k, v in CREATIVE_DOMAIN_MAP["action"].items() if isinstance(v, dict)],
                        "carrier": [f"{v.get('name_cn', k)}" for k, v in CREATIVE_DOMAIN_MAP["carrier"].items() if isinstance(v, dict)],
                        "physics": [f"{v.get('name_cn', k)}: {', '.join(v.get('break_options', []))}" for k, v in CREATIVE_DOMAIN_MAP["physics"].items() if isinstance(v, dict)],
                        "visual": [v if isinstance(v, str) else v.get("name_cn", "") for v in CREATIVE_DOMAIN_MAP["visual"].values()],
                    },
                    "formula": "创意概念 = 动作域(A) × 载体域(B) × 物理域(C) × 视觉域(V)",
                })
            elif method_id == "anti_pattern":
                resolved_methods.append({
                    "id": "anti_pattern",
                    "name_cn": "反模式破坏",
                    "available_patterns": [
                        {"key": ap["key"], "name_cn": ap["name_cn"], "formula": ap["prompt_formula"], "impact": ap["visual_impact"]}
                        for ap in matched_anti_patterns[:3]
                    ],
                })
            elif method_id == "SCAMPER" and "SCAMPER" in THINKING_METHOD_MAP:
                ops = THINKING_METHOD_MAP["SCAMPER"]["operations"]
                resolved_methods.append({
                    "id": "SCAMPER",
                    "name_cn": THINKING_METHOD_MAP["SCAMPER"]["name_cn"],
                    "operations": {k: {"name_cn": v["name_cn"], "prompt_op": v["prompt_op"]} for k, v in ops.items()},
                })
            elif method_id == "TRIZ" and "TRIZ" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "TRIZ",
                    "name_cn": THINKING_METHOD_MAP["TRIZ"]["name_cn"],
                    "principles": THINKING_METHOD_MAP["TRIZ"]["principles"],
                })
            elif method_id == "first_principles" and "FIRST_PRINCIPLES" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "first_principles",
                    "name_cn": THINKING_METHOD_MAP["FIRST_PRINCIPLES"]["name_cn"],
                    "decomposition": THINKING_METHOD_MAP["FIRST_PRINCIPLES"]["decomposition"],
                })
            elif method_id == "latent_nav" and "AI_LATENT_NAV" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "latent_nav",
                    "name_cn": THINKING_METHOD_MAP["AI_LATENT_NAV"]["name_cn"],
                    "distance_types": THINKING_METHOD_MAP["AI_LATENT_NAV"]["distance_types"],
                    "corridor_example": THINKING_METHOD_MAP["AI_LATENT_NAV"]["corridor_example"],
                })
            elif method_id == "style_hijack" and "AI_STYLE_HIJACK" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "style_hijack",
                    "name_cn": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["name_cn"],
                    "principle": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["principle"],
                    "top_pair": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["top_pair"],
                })
            elif method_id == "glitch" and "AI_GLITCH" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "glitch",
                    "name_cn": THINKING_METHOD_MAP["AI_GLITCH"]["name_cn"],
                    "types": THINKING_METHOD_MAP["AI_GLITCH"]["types"],
                })

        # ── 4. 从 NONHUMAN_COMBAT_MOTIF 解析非人战斗母题 ──
        nonhuman_motif_ctx = None
        if is_nonhuman:
            combat_moves = self._match_combat_moves(prompt)
            if combat_moves:
                nonhuman_motif_ctx = {}
                for motif_key, motif_info in NONHUMAN_COMBAT_MOTIF.items():
                    nonhuman_motif_ctx[motif_key] = {
                        "name_cn": motif_info["name_cn"],
                        "formula": motif_info["formula"],
                        "rules": motif_info["rules"],
                        "prompt_template": motif_info["prompt_template"],
                    }

        # ── 5. 从 NONHUMAN_VIDEO_RULES 解析非人视频规则 ──
        nonhuman_video_ctx = None
        if is_nonhuman and mode == "video":
            nonhuman_video_ctx = {
                "i2v_first_frame": NONHUMAN_VIDEO_RULES["i2v_first_frame"],
                "sweet_spot_specs": NONHUMAN_VIDEO_RULES["sweet_spot_specs"],
                "prompt_assembly_pipeline": NONHUMAN_VIDEO_RULES["prompt_assembly_pipeline"],
            }

        # ── 6. 构建各场景专用注入文本 ──
        # — 创意飞跃用 —
        method_hints = []
        for m in resolved_methods:
            mid = m["id"]
            if mid == "cross_domain_graft":
                domain_lines = []
                for dname, items in m["domains"].items():
                    domain_lines.append(f"  {dname}: {'; '.join(items[:5])}")
                method_hints.append(
                    f"【跨域嫁接】公式：{m['formula']}\n可用域元素：\n" + "\n".join(domain_lines)
                )
            elif mid == "anti_pattern":
                pattern_lines = []
                for pat in m["available_patterns"]:
                    pattern_lines.append(f"  {pat['name_cn']}: 公式\"{pat['formula']}\" 冲击度{pat['impact']}")
                method_hints.append("【反模式破坏】可选反模式：\n" + "\n".join(pattern_lines))
            elif mid == "SCAMPER":
                op_lines = [f"  {k}-{v['name_cn']}: {v['prompt_op']}" for k, v in m["operations"].items()]
                method_hints.append(f"【{m['name_cn']}】选择2-3种操作：\n" + "\n".join(op_lines))
            elif mid == "TRIZ":
                prin_lines = [f"  原理{n}: {desc}" for n, desc in m["principles"].items()]
                method_hints.append(f"【{m['name_cn']}】可选原理：\n" + "\n".join(prin_lines))
            elif mid == "first_principles":
                decomp_lines = [f"  {k}: {v}" for k, v in m["decomposition"].items()]
                method_hints.append(f"【{m['name_cn']}】拆解维度：\n" + "\n".join(decomp_lines))
            elif mid == "latent_nav":
                dt_lines = [f"  {k}: {v}" for k, v in m["distance_types"].items()]
                method_hints.append(f"【{m['name_cn']}】距离类型：\n" + "\n".join(dt_lines) + f"\n  走廊示例: {m['corridor_example']}")
            elif mid == "style_hijack":
                method_hints.append(f"【{m['name_cn']}】{m['principle']}\n  最高冲击对: {m['top_pair']}")
            elif mid == "glitch":
                type_lines = [f"  {k}: {v}" for k, v in m["types"].items()]
                method_hints.append(f"【{m['name_cn']}】故障类型：\n" + "\n".join(type_lines))

        creative_prompt_hints = "[创意知识注入]\n" + "\n".join(method_hints)

        # 非人战斗母题附加
        if nonhuman_motif_ctx:
            motif_lines = []
            for _mk, mv in nonhuman_motif_ctx.items():
                motif_lines.append(
                    f"  {mv['name_cn']} — 公式：{mv['formula']}\n"
                    f"    规则：{'；'.join(mv['rules'])}\n"
                    f"    提示词模板：{mv['prompt_template']}"
                )
            creative_prompt_hints += "\n[非人战斗母题]\n" + "\n".join(motif_lines)

        # — 视频增强用（在创意基础上增加非人视频规则） —
        video_prompt_hints = creative_prompt_hints
        if nonhuman_video_ctx:
            i2v = nonhuman_video_ctx["i2v_first_frame"]
            specs = nonhuman_video_ctx["sweet_spot_specs"]
            pipeline = nonhuman_video_ctx["prompt_assembly_pipeline"]
            video_prompt_hints += (
                f"\n[非人实体视频规则]\n"
                f"I2V首帧限制：{i2v['max_allowed']}\n"
                f"适合动作：{', '.join(i2v['suitable_actions'])}\n"
                f"不适合动作：{', '.join(i2v['unsuitable_actions'])}\n"
                f"设计锁定模板：{i2v['design_lock_template']}\n"
                f"甜点区规格：方法={specs['default_method']}，禁止={', '.join(specs['forbidden'])}\n"
                f"组装流水线：{' → '.join(pipeline['steps'])}"
            )

        # — 图片增强用（精简版，只注入跨域和反模式供参考） —
        image_prompt_hints = ""
        if matched_domain_elements:
            domain_hint_lines = []
            for dk, dv in matched_domain_elements.items():
                domain_hint_lines.append(f"  {dk}: {'; '.join(h['name_cn'] for h in dv[:3])}")
            image_prompt_hints = "[跨域参考元素]\n" + "\n".join(domain_hint_lines)

        return {
            "matched_methods": matched_methods,
            "resolved_methods": resolved_methods,
            "domain_candidates": domain_candidates,
            "matched_domain_elements": matched_domain_elements,
            "anti_patterns": matched_anti_patterns,
            "nonhuman_motif_ctx": nonhuman_motif_ctx,
            "nonhuman_video_ctx": nonhuman_video_ctx,
            "image_prompt_hints": image_prompt_hints,
            "video_prompt_hints": video_prompt_hints,
            "creative_prompt_hints": creative_prompt_hints,
        }

    def _select_creative_methods(self, prompt: str) -> list[str]:
        """根据用户描述自动选择最匹配的创意方法

        来源：V2 跨域嫁接创意引擎 + 反模式思维层 + 思维技法层 + AI特化思维层

        Args:
            prompt: 用户原始提示词
        Returns:
            2-3种最匹配的创意方法标识列表
        """
        p = prompt.lower()

        method_keywords = {
            "cross_domain_graft": ["嫁接", "跨域", "组合", "混搭", "graft", "cross-domain", "mix"],
            "anti_pattern": ["反模式", "颠覆", "破坏", "反转", "悖论", "反常", "paradox", "invert"],
            "SCAMPER": ["替换", "合并", "修改", "消除", "substitute", "combine", "modify", "eliminate"],
            "TRIZ": ["发明", "原理", "分割", "嵌套", "invent", "principle", "segment", "nest"],
            "first_principles": ["拆解", "本质", "底层", "基本", "principle", "fundamental", "decompose"],
            "latent_nav": ["前所未有", "从未见过", "novel", "unprecedented", "从未存在"],
            "style_hijack": ["风格碰撞", "混搭风格", "风格冲突", "style clash", "style fusion"],
            "glitch": ["故障", "glitch", "bug", "错误", "崩溃", "故障艺术", "corrupt"],
        }

        scores = {}
        for method, keywords in method_keywords.items():
            score = sum(1 for kw in keywords if kw in p)
            if score > 0:
                scores[method] = score

        sorted_methods = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        methods = [m for m, s in sorted_methods[:3]] if sorted_methods else []

        # 兜底：默认使用跨域嫁接+反模式（最通用的创造性组合）
        if not methods:
            methods = ["cross_domain_graft", "anti_pattern"]

        return methods

    def creative_leap(self, user_prompt: str, methods: list[str] | None = None) -> dict:
        """创意飞跃：运用超越常人的思维方法主动生成突破性创意

        来源：V2 跨域嫁接创意引擎 + 反模式思维层 + 思维技法层 + AI特化思维层 + 创意飞跃包

        Args:
            user_prompt: 用户原始描述
            methods: 指定使用的创意方法列表，可选值：
                cross_domain_graft / anti_pattern / SCAMPER / TRIZ
                first_principles / latent_nav / style_hijack / glitch
                None 时由系统自动选择2-3种最匹配的方法
        Returns:
            创意飞跃结果 dict，包含多个候选方案+护栏检查
        """
        # 自动选择方法
        if not methods:
            methods = self._select_creative_methods(user_prompt)

        # 注入实体信息
        entity_type, surface_policy = self._infer_entity_type(user_prompt)
        context = f"原始描述：{user_prompt}\n\n"
        if entity_type:
            context += f"[实体类型：{ENTITY_TYPE_MAP[entity_type]['name_cn']}({entity_type})]\n"
            context += f"[表面策略：{surface_policy}]\n"
            context += "[创意规则：非人实体的表面材质/能量逻辑不可被创意方法随意破坏]\n\n"

        # 注入战斗知识（通过路由器一次性解析所有战斗常量）
        combat_ctx = self._detect_combat_scene(user_prompt, "image")
        if combat_ctx:
            context += combat_ctx["creative_prompt_hints"] + "\n"

        # 注入创意知识（通过路由器一次性解析5大创意常量，替换硬编码方法描述）
        creative_ctx = self._resolve_creative_knowledge(user_prompt, "image")
        if creative_ctx and creative_ctx.get("creative_prompt_hints"):
            context += creative_ctx["creative_prompt_hints"] + "\n"

        text = self._ask_brain(CREATIVE_LEAP_PROMPT, context, temperature=0.8)
        result = self._parse_json(text)
        result.setdefault("original_concept", user_prompt)
        result.setdefault("creative_leaps", [])
        result.setdefault("guardrail_check", {
            "story_function_readable": True,
            "conflict_visible": True,
            "emotional_turn_clear": True,
            "visual_payoff_worth": True,
        })

        # 对每个飞跃结果叠加甜点区和风险预判
        for leap in result.get("creative_leaps", []):
            if "optimized_prompt" in leap:
                template = self._match_sweet_spot(leap["optimized_prompt"], "image", entity_type)
                if template:
                    leap["sweet_spot"] = template["name"]
                    leap["negative_prompt"] = self._merge_negative(
                        leap.get("negative_prompt", ""), template["negative"]
                    )

        # 推荐方案的安全检查
        idx = result.get("recommended_leap_index", 0)
        leaps = result.get("creative_leaps", [])
        if leaps and idx < len(leaps):
            guard = result.get("guardrail_check", {})
            if not all(guard.values() if isinstance(guard, dict) else [guard]):
                result["guardrail_warning"] = "推荐方案未通过护栏检查，建议选择更保守的方案或降低创意强度"

        # 记录使用的方法
        result["methods_used"] = methods

        return result


class AsyncSmartBrain:
    """AsyncSmartBrain：SmartBrain 的 asyncio 原生异步对应物。

    复用 SmartBrain 的全部知识库与逻辑（通过组合持有同步 SmartBrain 实例），
    仅将涉及网络 I/O 的方法（_ask_brain / enhance_*_prompt / understand_image）
    重写为 async 版本，使用 AsyncCruxClient。

    所有纯计算逻辑（_infer_entity_type / _match_sweet_spot / _predict_risks 等）
    直接委托给内部的同步 SmartBrain，无需重复实现。
    """

    def __init__(self, client: AsyncCruxClient) -> None:
        self.client = client
        # 持有同步 SmartBrain 以复用全部纯计算逻辑（这些方法不触发 I/O）
        # 传入一个 dummy sync client（不会被调用，因为只复用计算方法）
        self._sync = SmartBrain(client=client)  # type: ignore[arg-type]

    async def _ask_brain(self, system_prompt: str, user_input: str, temperature: float = 0.7) -> str:
        """异步调用文本模型（自动使用当前激活的供应商）"""
        model = self._sync._get_model()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        result = await self.client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        try:
            msg = result["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content")
        except (KeyError, IndexError):
            raise RuntimeError(f"Brain API返回格式异常: {str(result)[:200]}") from None
        if not content:
            raise RuntimeError(f"Brain 返回内容为空: {str(result)[:300]}")
        # 尝试提取JSON（可能被包裹在```json中）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content

    async def enhance_image_prompt(self, user_prompt: str, style: str | None = None) -> dict:
        """异步增强图片生成 Prompt。

        复用 SmartBrain.enhance_image_prompt 的全部逻辑，仅将唯一的 I/O 点
        （self._ask_brain 调用）替换为 async 版本。通过 monkey-patch 临时
        将同步 _ask_brain 替换为 async 版本不可行（同步代码无法 await），
        因此采用"复制逻辑 + 替换 I/O 调用"策略，保持与同步版完全一致的业务逻辑。
        """
        # 委托计算部分给同步 SmartBrain（构建 input_text），仅 I/O 异步化
        sync = self._sync

        entity_type, surface_policy = sync._infer_entity_type(user_prompt)
        beauty_type = sync._infer_beauty_type(user_prompt)
        combat_ctx = sync._detect_combat_scene(user_prompt, "image")

        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                         f"表面策略：{surface_policy}]\n原始描述：{user_prompt}")
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            angle_rules_str = "\n".join(
                f"  {angle}: {rule}"
                for angle, rule in beauty_info["angle_rules"].items()
            )
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[多角度规则：\n{angle_rules_str}]\n"
                f"[可用气质：{', '.join(beauty_info['aura_options'])}]\n"
                f"[禁止：模板脸、空泛形容词、出招姿势、硬摆拍、夸张武打体态]\n"
                f"原始描述：{user_prompt}"
            )
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['image_prompt_hints']}\n原始描述：{user_prompt}"
        if not combat_ctx and not beauty_type:
            creative_ctx = sync._resolve_creative_knowledge(user_prompt, "image")
            if creative_ctx and creative_ctx.get("image_prompt_hints"):
                input_text = f"{creative_ctx['image_prompt_hints']}\n原始描述：{input_text}"
        if style:
            input_text = f"风格要求：{style}\n{input_text}"

        try:
            from utils.memory import build_evolution_context
            evo_ctx = build_evolution_context("image")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except (OSError, ValueError, RuntimeError):
            pass

        # ── 唯一的异步 I/O 点 ──
        text = await self._ask_brain(ENHANCE_IMAGE_PROMPT, input_text)
        # ── 后续逻辑全部是纯计算，委托给同步 SmartBrain 的后处理 ──
        return sync._postprocess_image_enhance(
            user_prompt, text, entity_type, surface_policy, beauty_type, combat_ctx
        )

    async def enhance_video_prompt(self, user_prompt: str) -> dict:
        """异步增强视频生成 Prompt。逻辑同 enhance_image_prompt。"""
        sync = self._sync

        entity_type, surface_policy = sync._infer_entity_type(user_prompt)
        beauty_type = sync._infer_beauty_type(user_prompt)
        combat_ctx = sync._detect_combat_scene(user_prompt, "video")

        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                         f"表面策略：{surface_policy}]\n原始描述：{user_prompt}")
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[视频生产路由：逐镜 compact，I2V strength 0.70-0.72]\n"
                f"[允许动作：眼神、呼吸、轻微转头、整理衣领]\n"
                f"[禁止：出招姿势、硬摆拍、夸张武打体态、多镜头切换]\n"
                f"原始描述：{user_prompt}"
            )
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['video_prompt_hints']}\n原始描述：{user_prompt}"
        if entity_type and not beauty_type:
            creative_ctx = sync._resolve_creative_knowledge(user_prompt, "video")
            if creative_ctx and creative_ctx.get("nonhuman_video_ctx"):
                i2v = creative_ctx["nonhuman_video_ctx"]["i2v_first_frame"]
                specs = creative_ctx["nonhuman_video_ctx"]["sweet_spot_specs"]
                pipeline = creative_ctx["nonhuman_video_ctx"]["prompt_assembly_pipeline"]
                nonhuman_video_hints = (
                    f"[非人实体视频规则]\n"
                    f"I2V首帧限制：{i2v['max_allowed']}\n"
                    f"适合动作：{', '.join(i2v['suitable_actions'][:4])}\n"
                    f"不适合动作：{', '.join(i2v['unsuitable_actions'][:4])}\n"
                    f"设计锁定：{i2v['design_lock_template']}\n"
                    f"甜点区方法：{specs['default_method']}，禁止：{', '.join(specs['forbidden'])}\n"
                    f"组装流水线：{' → '.join(pipeline['steps'])}"
                )
                input_text = f"{nonhuman_video_hints}\n原始描述：{input_text}"

        try:
            from utils.memory import build_evolution_context
            evo_ctx = build_evolution_context("video")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except (OSError, RuntimeError, ConnectionError):
            pass

        # ── 唯一的异步 I/O 点 ──
        text = await self._ask_brain(ENHANCE_VIDEO_PROMPT, input_text)
        return sync._postprocess_video_enhance(
            user_prompt, text, entity_type, surface_policy, beauty_type, combat_ctx
        )

    async def understand_image(self, question: str, image_url: str) -> str:
        """异步利用多模态能力理解图片"""
        result = await self.client.chat_multimodal(
            text=question,
            image_url=image_url,
            model="agnes-1.5-flash",
            temperature=0.3,
            max_tokens=1024,
        )
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"多模态API返回格式异常: {str(result)[:200]}") from None

