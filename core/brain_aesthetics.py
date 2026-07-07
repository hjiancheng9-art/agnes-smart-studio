"""Brain aesthetics module — extracted from brain.py."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from core.brain_data import (
    BEAUTY_NEGATIVE_REPAIR_MAP,
    BEAUTY_PORTRAIT_MAP,
    BEAUTY_SWEET_SPOT_TEMPLATES,
    ENTITY_NEGATIVE_REPAIR_MAP,
    ENTITY_SWEET_SPOT_TEMPLATES,
    ENTITY_TYPE_MAP,
    NEGATIVE_REPAIR_MAP,
    SWEET_SPOT_TEMPLATES,
    SWEET_SPOT_VIDEO_TEMPLATES,
)

if TYPE_CHECKING:
    pass


class SmartBrainMixin:
    """Mixin for SmartBrain methods.

    Intended to be mixed into core.brain.SmartBrain.
    Uses self._ask_brain(), self.client, etc. from the parent class.
    """

    # ── type stubs: provided by SmartBrain or other Mixins ──
    _infer_beauty_type: Callable[..., Any]
    _infer_entity_type: Callable[..., Any]
    _match_beauty_sweet_spot: Callable[..., Any]

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
            entity_type, _ = self._infer_entity_type(prompt)  # pyright: ignore[reportCallIssue]
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
            beauty_type = self._infer_beauty_type(prompt)  # pyright: ignore[reportCallIssue]
            if beauty_type:
                beauty_tpl = self._match_beauty_sweet_spot(beauty_type, mode)
                if beauty_tpl:
                    return beauty_tpl

        # 3. 回退到原有场景甜点区匹配
        # 关键词匹配规则
        person_keywords = [
            "人",
            "女",
            "男",
            "girl",
            "boy",
            "woman",
            "man",
            "lady",
            "美女",
            "帅哥",
            "portrait",
            "face",
            "人物",
            "少女",
            "少年",
            "lady",
            "miss",
            "mr",
            "角色",
            "character",
        ]
        full_body_keywords = [
            "全身",
            "站",
            "走",
            "跑",
            "跳",
            "standing",
            "walking",
            "running",
            "full body",
            "跳舞",
            "dancing",
            "姿势",
            "pose",
        ]
        action_keywords = [
            "打",
            "战",
            "打斗",
            "fight",
            "battle",
            "action",
            "追逐",
            "chase",
            "武术",
            "martial",
            "鞭",
            "whip",
            "sword",
            "挥",
            "attack",
            "kick",
            "punch",
        ]
        animal_keywords = [
            "猫",
            "狗",
            "鸟",
            "鱼",
            "虎",
            "龙",
            "马",
            "动物",
            "cat",
            "dog",
            "bird",
            "fish",
            "tiger",
            "dragon",
            "horse",
            "animal",
            "lion",
            "wolf",
            "bear",
            "rabbit",
            "snake",
        ]
        landscape_keywords = [
            "山",
            "海",
            "湖",
            "天空",
            "日落",
            "城市",
            "风景",
            "mountain",
            "ocean",
            "sea",
            "lake",
            "sky",
            "sunset",
            "city",
            "landscape",
            "forest",
            "沙漠",
            "desert",
        ]
        food_keywords = [
            "美食",
            "蛋糕",
            "甜品",
            "食物",
            "菜",
            "汤",
            "咖啡",
            "food",
            "cake",
            "dessert",
            "soup",
            "coffee",
            "tea",
            "meal",
        ]
        anime_keywords = ["动漫", "二次元", "anime", "manga", "2.5d", "赛璐", "日系", "卡通人物"]

        # 按优先级匹配
        if mode == "video":
            templates = SWEET_SPOT_VIDEO_TEMPLATES
            if any(k in p for k in action_keywords):
                result = templates["action_video"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }
            if any(k in p for k in person_keywords):
                if any(k in p for k in full_body_keywords):
                    result = templates["action_video"]
                    return {
                        "name": result["name"],
                        "suffix": result["suffix"],
                        "negative": result["negative"],
                        "entity_type": None,
                        "surface_policy": None,
                    }
                result = templates["portrait_video"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }
            result = templates["camera_pan"]
            return {
                "name": result["name"],
                "suffix": result["suffix"],
                "negative": result["negative"],
                "entity_type": None,
                "surface_policy": None,
            }
        else:
            if any(k in p for k in anime_keywords):
                result = SWEET_SPOT_TEMPLATES["anime"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }
            if any(k in p for k in action_keywords):
                result = SWEET_SPOT_TEMPLATES["action"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }
            if any(k in p for k in full_body_keywords):
                result = SWEET_SPOT_TEMPLATES["full_body"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }
            if any(k in p for k in person_keywords):
                result = SWEET_SPOT_TEMPLATES["portrait"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }
            if any(k in p for k in animal_keywords):
                result = SWEET_SPOT_TEMPLATES["animal"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }
            if any(k in p for k in food_keywords):
                result = SWEET_SPOT_TEMPLATES["food"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }
            if any(k in p for k in landscape_keywords):
                result = SWEET_SPOT_TEMPLATES["landscape"]
                return {
                    "name": result["name"],
                    "suffix": result["suffix"],
                    "negative": result["negative"],
                    "entity_type": None,
                    "surface_policy": None,
                }

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
                risks.append(
                    {
                        "risk": f"{entity_type}_{risk_id}",
                        "symptoms": risk_info["symptoms"],
                        "advice": risk_info["repair_keywords"],
                    }
                )

        # ── 通用风险 ──
        # 人物相关 → 解剖失败 + 穿模风险
        person_kw = [
            "人",
            "女",
            "男",
            "girl",
            "boy",
            "woman",
            "man",
            "face",
            "portrait",
            "人物",
            "少女",
            "少年",
            "角色",
            "character",
            "美女",
            "帅哥",
            "模特",
            "model",
        ]
        if any(k in p for k in person_kw):
            risks.append(
                {
                    "risk": "anatomy_failure",
                    "symptoms": NEGATIVE_REPAIR_MAP["anatomy_failure"]["symptoms"],
                    "advice": NEGATIVE_REPAIR_MAP["anatomy_failure"]["repair_keywords"],
                }
            )
            risks.append(
                {
                    "risk": "penetration",
                    "symptoms": NEGATIVE_REPAIR_MAP["penetration"]["symptoms"],
                    "advice": NEGATIVE_REPAIR_MAP["penetration"]["repair_keywords"],
                }
            )
        # 动作/打斗 → 穿模风险 + 视频不稳定
        action_kw = [
            "动作",
            "fight",
            "battle",
            "action",
            "attack",
            "打",
            "战",
            "打斗",
            "追逐",
            "chase",
            "武术",
            "martial",
            "kick",
            "punch",
            "跑",
            "跳",
            "挥",
            "舞",
            "dancing",
        ]
        if any(k in p for k in action_kw):
            if not any(r["risk"] == "penetration" for r in risks):
                risks.append(
                    {
                        "risk": "penetration",
                        "symptoms": NEGATIVE_REPAIR_MAP["penetration"]["symptoms"],
                        "advice": NEGATIVE_REPAIR_MAP["penetration"]["repair_keywords"],
                    }
                )
            risks.append(
                {
                    "risk": "video_instability",
                    "symptoms": NEGATIVE_REPAIR_MAP["video_instability"]["symptoms"],
                    "advice": NEGATIVE_REPAIR_MAP["video_instability"]["repair_keywords"],
                }
            )
        # 背景/场景 → 文字漂移风险
        scene_kw = [
            "背景",
            "场景",
            "landscape",
            "background",
            "城市",
            "风景",
            "city",
            "mountain",
            "ocean",
            "sea",
            "forest",
            "天空",
            "街",
            "street",
            "building",
            "室内",
            "indoor",
            "room",
        ]
        if any(k in p for k in scene_kw):
            risks.append(
                {
                    "risk": "text_drift",
                    "symptoms": NEGATIVE_REPAIR_MAP["text_drift"]["symptoms"],
                    "advice": NEGATIVE_REPAIR_MAP["text_drift"]["repair_keywords"],
                }
            )
        # 光照关键词 → 过曝/欠曝风险
        light_kw = ["light", "光照", "阳光", "sun", "影", "shadow", "亮", "暗", "dark", "bright", "闪光", "flash"]
        if any(k in p for k in light_kw):
            risks.append(
                {
                    "risk": "too_bright",
                    "symptoms": NEGATIVE_REPAIR_MAP["too_bright"]["symptoms"],
                    "advice": NEGATIVE_REPAIR_MAP["too_bright"]["repair_keywords"],
                }
            )
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
                risks.append(
                    {
                        "risk": f"{beauty_type}_{risk_id}",
                        "symptoms": risk_info["symptoms"],
                        "advice": risk_info["repair_keywords"],
                    }
                )
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
