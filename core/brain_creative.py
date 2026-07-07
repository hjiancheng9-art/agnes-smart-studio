"""Brain creative module — extracted from brain.py."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from core.brain_data import (
    ANTI_PATTERN_MAP,
    CREATIVE_DOMAIN_MAP,
    CREATIVE_LEAP_PROMPT,
    ENTITY_TYPE_MAP,
    NONHUMAN_COMBAT_MOTIF,
    NONHUMAN_VIDEO_RULES,
    THINKING_METHOD_MAP,
)

if TYPE_CHECKING:
    pass


class SmartBrainMixin:
    """Mixin for SmartBrain methods.

    Intended to be mixed into core.brain.SmartBrain.
    Uses self._ask_brain(), self.client, etc. from the parent class.
    """

    # ── type stubs: provided by SmartBrain or other Mixins ──
    _ask_brain: Callable[..., Any]
    _detect_combat_scene: Callable[..., Any]
    _infer_entity_type: Callable[..., Any]
    _match_combat_moves: Callable[..., Any]
    _match_sweet_spot: Callable[..., Any]
    _merge_negative: Callable[..., Any]
    _parse_json: Callable[..., Any]
    _resolve_creative_knowledge: Callable[..., Any]
    _select_creative_methods: Callable[..., Any]

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
            matched_anti_patterns.append(
                {
                    "key": ap_key,
                    "name_cn": ap_info["name_cn"],
                    "core_operation": ap_info["core_operation"],
                    "example": ap_info["example"],
                    "visual_impact": ap_info["visual_impact"],
                    "prompt_formula": ap_info["prompt_formula"],
                    "relevance": 2 if any(kw in p for kw in anti_pattern_keywords.get(ap_key, [])) else 0,
                }
            )
        matched_anti_patterns.sort(key=lambda x: x["relevance"], reverse=True)

        # ── 3. 从 THINKING_METHOD_MAP 解析思维技法 ──
        matched_methods = self._select_creative_methods(prompt)  # pyright: ignore[reportCallIssue]
        resolved_methods = []
        for method_id in matched_methods:
            if method_id == "cross_domain_graft" and "action" in CREATIVE_DOMAIN_MAP:
                # 跨域嫁接 — 从 CREATIVE_DOMAIN_MAP 取四域
                resolved_methods.append(
                    {
                        "id": "cross_domain_graft",
                        "name_cn": "跨域嫁接",
                        "domains": {
                            "action": [
                                f"{v.get('name_cn', k)}"
                                for k, v in CREATIVE_DOMAIN_MAP["action"].items()
                                if isinstance(v, dict)
                            ],
                            "carrier": [
                                f"{v.get('name_cn', k)}"
                                for k, v in CREATIVE_DOMAIN_MAP["carrier"].items()
                                if isinstance(v, dict)
                            ],
                            "physics": [
                                f"{v.get('name_cn', k)}: {', '.join(v.get('break_options', []))}"
                                for k, v in CREATIVE_DOMAIN_MAP["physics"].items()
                                if isinstance(v, dict)
                            ],
                            "visual": [
                                v if isinstance(v, str) else v.get("name_cn", "")
                                for v in CREATIVE_DOMAIN_MAP["visual"].values()
                            ],
                        },
                        "formula": "创意概念 = 动作域(A) × 载体域(B) × 物理域(C) × 视觉域(V)",
                    }
                )
            elif method_id == "anti_pattern":
                resolved_methods.append(
                    {
                        "id": "anti_pattern",
                        "name_cn": "反模式破坏",
                        "available_patterns": [
                            {
                                "key": ap["key"],
                                "name_cn": ap["name_cn"],
                                "formula": ap["prompt_formula"],
                                "impact": ap["visual_impact"],
                            }
                            for ap in matched_anti_patterns[:3]
                        ],
                    }
                )
            elif method_id == "SCAMPER" and "SCAMPER" in THINKING_METHOD_MAP:
                ops = THINKING_METHOD_MAP["SCAMPER"]["operations"]
                resolved_methods.append(
                    {
                        "id": "SCAMPER",
                        "name_cn": THINKING_METHOD_MAP["SCAMPER"]["name_cn"],
                        "operations": {
                            k: {"name_cn": v["name_cn"], "prompt_op": v["prompt_op"]} for k, v in ops.items()
                        },
                    }
                )
            elif method_id == "TRIZ" and "TRIZ" in THINKING_METHOD_MAP:
                resolved_methods.append(
                    {
                        "id": "TRIZ",
                        "name_cn": THINKING_METHOD_MAP["TRIZ"]["name_cn"],
                        "principles": THINKING_METHOD_MAP["TRIZ"]["principles"],
                    }
                )
            elif method_id == "first_principles" and "FIRST_PRINCIPLES" in THINKING_METHOD_MAP:
                resolved_methods.append(
                    {
                        "id": "first_principles",
                        "name_cn": THINKING_METHOD_MAP["FIRST_PRINCIPLES"]["name_cn"],
                        "decomposition": THINKING_METHOD_MAP["FIRST_PRINCIPLES"]["decomposition"],
                    }
                )
            elif method_id == "latent_nav" and "AI_LATENT_NAV" in THINKING_METHOD_MAP:
                resolved_methods.append(
                    {
                        "id": "latent_nav",
                        "name_cn": THINKING_METHOD_MAP["AI_LATENT_NAV"]["name_cn"],
                        "distance_types": THINKING_METHOD_MAP["AI_LATENT_NAV"]["distance_types"],
                        "corridor_example": THINKING_METHOD_MAP["AI_LATENT_NAV"]["corridor_example"],
                    }
                )
            elif method_id == "style_hijack" and "AI_STYLE_HIJACK" in THINKING_METHOD_MAP:
                resolved_methods.append(
                    {
                        "id": "style_hijack",
                        "name_cn": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["name_cn"],
                        "principle": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["principle"],
                        "top_pair": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["top_pair"],
                    }
                )
            elif method_id == "glitch" and "AI_GLITCH" in THINKING_METHOD_MAP:
                resolved_methods.append(
                    {
                        "id": "glitch",
                        "name_cn": THINKING_METHOD_MAP["AI_GLITCH"]["name_cn"],
                        "types": THINKING_METHOD_MAP["AI_GLITCH"]["types"],
                    }
                )

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
                method_hints.append(f"【跨域嫁接】公式：{m['formula']}\n可用域元素：\n" + "\n".join(domain_lines))
            elif mid == "anti_pattern":
                pattern_lines = []
                for pat in m["available_patterns"]:
                    pattern_lines.append(f'  {pat["name_cn"]}: 公式"{pat["formula"]}" 冲击度{pat["impact"]}')
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
                method_hints.append(
                    f"【{m['name_cn']}】距离类型：\n" + "\n".join(dt_lines) + f"\n  走廊示例: {m['corridor_example']}"
                )
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
            methods = self._select_creative_methods(user_prompt)  # pyright: ignore[reportCallIssue]

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
        creative_ctx = self._resolve_creative_knowledge(user_prompt, "image")  # pyright: ignore[reportArgumentType]
        if creative_ctx and creative_ctx.get("creative_prompt_hints"):
            context += creative_ctx["creative_prompt_hints"] + "\n"

        text = self._ask_brain(CREATIVE_LEAP_PROMPT, context, temperature=0.8)
        result = self._parse_json(text)
        result.setdefault("original_concept", user_prompt)
        result.setdefault("creative_leaps", [])
        result.setdefault(
            "guardrail_check",
            {
                "story_function_readable": True,
                "conflict_visible": True,
                "emotional_turn_clear": True,
                "visual_payoff_worth": True,
            },
        )

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
