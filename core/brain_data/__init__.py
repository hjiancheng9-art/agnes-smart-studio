"""Brain data knowledge base — domain-split for maintainability."""

# Negative repair map (general, small enough to live here)
NEGATIVE_REPAIR_MAP = {
    "text_drift": {
        "symptoms": ["出现文字", "出现图表", "出现infographic", "出现logo", "出现typography"],
        "repair_keywords": "pure environment, no text, no letters, no typography, no logo, no watermark, no infographic, no chart, no labels",
    },
    "cluttered": {
        "symptoms": ["画面太满", "主体太大", "构图拥挤", "裁切关键元素"],
        "repair_keywords": "clean center, negative space, fewer objects, simplified composition, breathing room, well framed",
    },
    "too_dark": {
        "symptoms": ["太暗", "欠曝", "看不清主体", "死黑区域"],
        "repair_keywords": "controlled rim light, readable midtones, balanced exposure, fill light, brighter shadows, lifted blacks",
    },
    "too_bright": {
        "symptoms": ["过曝", "太亮", "高光溢出", "高光丢失细节"],
        "repair_keywords": "highlight control, darker center, reduced exposure, controlled specular highlights, detail in highlights",
    },
    "anatomy_failure": {
        "symptoms": ["多余手指", "多余手臂", "手部畸形", "面部变形", "比例错误"],
        "repair_keywords": "perfect hand anatomy, five fingers each hand, symmetrical face, correct human proportions, natural pose, anatomically correct",
    },
    "penetration": {
        "symptoms": ["穿模", "物体穿透", "身体融合", "身体交叉重叠", "几何变形"],
        "repair_keywords": "solid objects, proper occlusion, no clipping, no mesh penetration, separate bodies, clear boundaries, distinct geometries",
    },
    "identity_drift": {
        "symptoms": ["身份漂移", "面部不一致", "角色变化", "人种变化"],
        "repair_keywords": "consistent face, identity lock, same person, consistent appearance, character continuity, same ethnicity",
    },
    "video_instability": {
        "symptoms": ["闪烁", "抖动", "帧跳跃", "鬼影", "运动不自然", "画面撕裂"],
        "repair_keywords": "stable, smooth motion, no flickering, no jitter, no ghosting, temporal consistency, natural movement, consistent frame pacing",
    },
}

# ── 实体类型推断表 ──────────────────────────────────
# 来源：新烬龙V2 asset-continuity.md + common.js inferPrimaryCharacterEntity()
# 9种非人实体：关键词 → 表面材质策略

# Re-export from domain modules
from .combat import COMBAT_MOVE_INDEX as COMBAT_MOVE_INDEX
from .combat import COMBAT_MOVE_TEMPLATES as COMBAT_MOVE_TEMPLATES
from .combat import COMBAT_NEGATIVE_REPAIR_MAP as COMBAT_NEGATIVE_REPAIR_MAP
from .combat import COMBAT_VFX_PALETTES as COMBAT_VFX_PALETTES
from .combat import NONHUMAN_COMBAT_MOTIF as NONHUMAN_COMBAT_MOTIF
from .combat import NONHUMAN_VIDEO_RULES as NONHUMAN_VIDEO_RULES
from .creative import ANTI_PATTERN_MAP as ANTI_PATTERN_MAP
from .creative import CREATIVE_DOMAIN_MAP as CREATIVE_DOMAIN_MAP
from .creative import GRAFT_TARGETS as GRAFT_TARGETS
from .creative import THINKING_METHOD_MAP as THINKING_METHOD_MAP
from .entities import BEAUTY_NEGATIVE_REPAIR_MAP as BEAUTY_NEGATIVE_REPAIR_MAP
from .entities import BEAUTY_PORTRAIT_MAP as BEAUTY_PORTRAIT_MAP
from .entities import BEAUTY_PRODUCTION_RULES as BEAUTY_PRODUCTION_RULES
from .entities import ENTITY_NEGATIVE_REPAIR_MAP as ENTITY_NEGATIVE_REPAIR_MAP
from .entities import ENTITY_TYPE_MAP as ENTITY_TYPE_MAP
from .prompts import CREATIVE_LEAP_PROMPT as CREATIVE_LEAP_PROMPT
from .prompts import ENHANCE_IMAGE_PROMPT as ENHANCE_IMAGE_PROMPT
from .prompts import ENHANCE_VIDEO_PROMPT as ENHANCE_VIDEO_PROMPT
from .prompts import IMAGE_EDIT_PROMPT as IMAGE_EDIT_PROMPT
from .prompts import INTENT_PROMPT as INTENT_PROMPT
from .prompts import STORYBOARD_PROMPT as STORYBOARD_PROMPT
from .sweet_spots import BEAUTY_SWEET_SPOT_TEMPLATES as BEAUTY_SWEET_SPOT_TEMPLATES
from .sweet_spots import COMBAT_SWEET_SPOT_TEMPLATES as COMBAT_SWEET_SPOT_TEMPLATES
from .sweet_spots import ENTITY_SWEET_SPOT_TEMPLATES as ENTITY_SWEET_SPOT_TEMPLATES
from .sweet_spots import SWEET_SPOT_TEMPLATES as SWEET_SPOT_TEMPLATES
from .sweet_spots import SWEET_SPOT_VIDEO_TEMPLATES as SWEET_SPOT_VIDEO_TEMPLATES
