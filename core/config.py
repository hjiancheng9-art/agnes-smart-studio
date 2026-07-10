"""配置管理 - 模型列表、分辨率预设、Prompt模板库、用户偏好持久化"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

# ── 全局配置目录（对标 codex 的 ~/.codex、claude 的 ~/.claude）──
# 让 crux 在任意 CWD 都能读到 API Key，不再强依赖当前目录的 .env。
# 加载优先级（高 → 低）：
#   1. 已存在的环境变量（CI/容器/临时切换用）
#   2. 当前目录 .env（项目级覆盖，override=True）
#   3. ~/.crux/auth.json（跨项目基准，仅补缺）
#   4. ~/.agnes/auth.json（遗留兼容，仅当 ~/.crux/auth.json 不存在时读取）
CRUX_HOME = Path(os.path.expanduser("~")) / ".crux"
AGNES_HOME = Path(os.path.expanduser("~")) / ".agnes"  # 遗留兼容路径

AUTH_FILE = CRUX_HOME / "auth.json"

# auth.json 字段名 → 环境变量名 映射
# CRUX_* 优先，回退 AGNES_*（兼容旧配置）
_AUTH_FIELD_TO_ENV = {
    "CRUX_API_KEY": "CRUX_API_KEY",
    "CRUX_BASE_URL": "CRUX_BASE_URL",
}
_AUTH_FIELD_TO_ENV_LEGACY = {
    "AGNES_API_KEY": "AGNES_API_KEY",
    "AGNES_BASE_URL": "AGNES_BASE_URL",
}


def _get_env(keys: list[str]) -> str | None:
    """按优先级检查多个环境变量名，返回第一个非空值。"""
    for k in keys:
        val = os.environ.get(k)
        if val:
            return val
    return None


def _load_global_auth() -> None:
    """读 ~/.crux/auth.json（回退 ~/.agnes/auth.json），补缺环境变量。

    在 load_dotenv 之后调用，优先级：环境变量 > 项目 .env > 全局 auth。
    任何 IO/JSON 错误都静默——全局 auth 是便利项，不是必需项，缺失时
    回退到原有的「环境变量 + CWD/.env」行为。
    """
    auth_file = AUTH_FILE
    if not auth_file.exists():
        # 遗留兼容：尝试旧路径
        legacy = AGNES_HOME / "auth.json"
        if legacy.exists():
            auth_file = legacy
        else:
            return

    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        # 先尝试 CRUX 字段，再回退 AGNES 字段
        for field, env_key in _AUTH_FIELD_TO_ENV.items():
            val = data.get(field) or data.get(_AUTH_FIELD_TO_ENV_LEGACY.get(field, ""))
            if val and not _get_env([env_key, _AUTH_FIELD_TO_ENV_LEGACY.get(env_key, "")]):
                os.environ.setdefault(env_key, str(val))
    except (OSError, json.JSONDecodeError, TypeError):
        pass


def save_global_auth(api_key: str, base_url: str | None = None) -> Path:
    """把 API Key 写入 ~/.crux/auth.json。

    写入后任意目录敲 crux 都能用。返回写入路径。已存在文件会被合并
    （保留未传入的字段，base_url 传 None 时不覆盖原有 base_url）。
    """
    CRUX_HOME.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if AUTH_FILE.exists():
        try:
            existing = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                data = existing
        except (OSError, json.JSONDecodeError):
            pass
    data["CRUX_API_KEY"] = api_key
    if base_url is not None:
        data["CRUX_BASE_URL"] = base_url
    AUTH_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return AUTH_FILE


load_dotenv(override=True)
_load_global_auth()

__all__ = [
    "CRUX_VISION_BASE_URL",
    "AGNES_VISION_BASE_URL",
    "CRUX_HOME",
    "AGNES_HOME",
    "AUTH_FILE",
    "IMAGE_SIZES",
    "MODELS",
    "OUTPUT_DIR",
    "PROMPT_TEMPLATES",
    "SETTINGS",
    "Settings",
    "VALID_NUM_FRAMES",
    "VIDEO_ASPECT_RATIOS",
    "VIDEO_DURATION_MAP",
    "save_global_auth",
]

# ── 常量 ──────────────────────────────────────────────────

from core.agnes_models import CRUX_IMAGE, CRUX_IMAGE_EDIT, CRUX_TEXT, CRUX_VIDEO

MODELS = {
    "text_pro": {
        "id": CRUX_TEXT,
        "name": "CRUX 2.0 Flash",
        "type": "text",
        "multimodal": True,
        "thinking": True,
        "tools": True,
    },
    "image_hd": {
        "id": CRUX_IMAGE,
        "name": "CRUX Image 2.1 Flash",
        "type": "image",
        "supports_img2img": True,
        "high_density": True,
    },
    "image_edit": {
        "id": CRUX_IMAGE_EDIT,
        "name": "CRUX Image 2.0 Flash",
        "type": "image",
        "supports_img2img": True,
        "supports_multi_image": True,
        "requires_tags_for_i2i": True,
    },
    "video": {
        "id": CRUX_VIDEO,
        "name": "CRUX Video V2.0",
        "type": "video",
        "modes": ["ti2vid", "keyframes"],
    },
}

# 视觉模型常量 — 始终指向 CRUX 多模态模型，与主对话供应商解耦
# 用途：ChatSession 的 vision_client 专用，/vision 命令 + send_stream 图片路由
CRUX_VISION_BASE_URL = "https://apihub.agnes-ai.com/v1"


def get_crux_vision_model() -> str:
    """Get the best available vision model — prefers CRUX (most accurate), Zhipu as fallback."""
    try:
        import os

        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        # Prefer CRUX vision models (best counting/OCR/detail)
        crux = mgr.providers.get("crux", {})
        crux_key = crux.get("api_key") or os.getenv("CRUX_API_KEY") or os.getenv("AGNES_API_KEY")
        if crux_key:
            return crux.get("models", {}).get("pro") or CRUX_TEXT
        # Fallback to Zhipu vision models (free)
        zhipu = mgr.providers.get("zhipu", {})
        zhipu_v = zhipu.get("vision_models", {})
        if zhipu_v:
            return zhipu_v.get("pro") or zhipu_v.get("light") or next(iter(zhipu_v.values()))
        # Search all providers for vision models
        for _pid, p in mgr.providers.items():
            vm = p.get("vision_models", {})
            if vm:
                return vm.get("light") or vm.get("pro") or next(iter(vm.values()))
        return "GLM-4V-Flash"
    except (KeyError, json.JSONDecodeError, OSError, ValueError) as e:
        logger = logging.getLogger("crux.config")
        logger.debug("Vision model resolution failed (%s: %s), falling back to GLM-4V-Flash", type(e).__name__, e)
        return "GLM-4V-Flash"


AGNES_VISION_BASE_URL = CRUX_VISION_BASE_URL

# 视频分辨率预设 (比例名 -> (width, height))
VIDEO_ASPECT_RATIOS = {
    "16:9 横屏": (1280, 720),
    "9:16 竖屏": (720, 1280),
    "1:1 正方形": (1024, 1024),
    "4:3 横图": (1024, 768),
    "3:4 竖图": (768, 1024),
}

# 图片尺寸预设
IMAGE_SIZES = {
    "1:1": "1024x1024",
    "3:4": "768x1024",
    "4:3": "1024x768",
    "9:16": "576x1024",
    "16:9": "1024x576",
    "9:21": "448x1024",
    "21:9": "1024x448",
    "2:3": "684x1024",
    "3:2": "1024x684",
}

# 合法的 num_frames 值 (8n+1 且 <=441)
VALID_NUM_FRAMES = [81, 121, 161, 201, 241, 281, 321, 361, 401, 441]

# 视频时长参考 (num_frames / fps)
VIDEO_DURATION_MAP = {
    81: {"24fps": "3.4s", "30fps": "2.7s", "12fps": "6.8s"},
    121: {"24fps": "5.0s", "30fps": "4.0s", "12fps": "10.1s"},
    161: {"24fps": "6.7s", "30fps": "5.4s", "12fps": "13.4s"},
    241: {"24fps": "10.0s", "30fps": "8.0s", "12fps": "20.1s"},
    441: {"24fps": "18.4s", "30fps": "14.7s", "12fps": "36.8s"},
}

# Prompt 模板库
PROMPT_TEMPLATES = {
    "赛博朋克": {
        "image": "cyberpunk cityscape, neon lights, rain-soaked streets, holographic billboards, dark atmosphere, cinematic realism, volumetric lighting",
        "video": "A sweeping drone shot through a cyberpunk city at night, neon reflections on wet streets, holographic signs flickering",
        "negative": "blurry, low quality, cartoon, anime",
    },
    "日系动漫": {
        "image": "anime style, cherry blossoms, soft pastel colors, studio ghibli inspired, warm lighting, detailed background",
        "video": "A gentle pan across an anime-style landscape with cherry blossoms falling softly in the wind",
        "negative": "realistic, photographic, 3d render",
    },
    "水彩画风": {
        "image": "watercolor painting style, soft washes, delicate brush strokes, paper texture visible, muted colors, artistic",
        "video": "A watercolor scene coming to life, paint spreading across the canvas with gentle movements",
        "negative": "sharp edges, digital, photorealistic",
    },
    "电影质感": {
        "image": "cinematic shot, dramatic lighting, shallow depth of field, anamorphic lens flare, film grain, 35mm film look",
        "video": "A cinematic tracking shot with dramatic lighting, shallow depth of field, anamorphic lens flare",
        "negative": "amateur, phone camera, shaky",
    },
    "电商主图": {
        "image": "product photography, studio lighting, white background, high detail, professional, clean composition",
        "video": "A smooth product reveal with studio lighting, rotating view, clean white background",
        "negative": "cluttered, low quality, watermark",
    },
    "自然风光": {
        "image": "breathtaking landscape, golden hour, dramatic clouds, vast horizon, national geographic style, ultra detailed",
        "video": "A sweeping aerial shot over breathtaking landscape at golden hour, clouds drifting slowly",
        "negative": "urban, city, artificial",
    },
    "人物肖像": {
        "image": "professional portrait, soft Rembrandt lighting, detailed face, bokeh background, 85mm lens",
        "video": "A cinematic portrait with subtle head movement, soft lighting, shallow depth of field",
        "negative": "deformed, extra limbs, cartoon",
    },
    "奇幻魔法": {
        "image": "fantasy magic scene, ethereal glow, floating particles, mystical atmosphere, enchanted forest, volumetric light",
        "video": "A magical scene with swirling particles and glowing runes, ethereal light emanating from the center",
        "negative": "modern, technology, realistic",
    },
}

# 输出目录（基于脚本所在目录，不受 CWD 影响）
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
(OUTPUT_DIR / "images").mkdir(exist_ok=True)
(OUTPUT_DIR / "videos").mkdir(exist_ok=True)


# ── 设置 ──────────────────────────────────────────────────


@dataclass
class Settings:
    api_key: str = ""
    base_url: str = "https://apihub.agnes-ai.com/v1"
    default_image_model: str = "agnes-image-2.1-flash"
    default_video_model: str = "agnes-video-v2.0"
    default_text_model: str = "agnes-2.0-flash"
    default_video_width: int = 1152
    default_video_height: int = 768
    default_num_frames: int = 121
    default_frame_rate: int = 24
    default_image_size: str = "1024x768"
    video_poll_interval: float = 5.0
    video_max_wait: float = 300.0
    max_retries: int = 3
    # #2 反思引擎配置
    reflection_enabled: bool = True
    reflection_interval: int = 5

    def __post_init__(self):
        # 环境变量优先于 settings.json（安全：防止 API key 硬编码泄露）
        env_key = _get_env(["CRUX_API_KEY", "AGNES_API_KEY"])
        if env_key:
            self.api_key = env_key
        elif not self.api_key:
            self.api_key = ""
        if self.base_url == "https://apihub.agnes-ai.com/v1":
            env_url = _get_env(["CRUX_BASE_URL", "AGNES_BASE_URL"])
            if env_url:
                self.base_url = env_url

    def save(self, path: str = "settings.json"):
        data = asdict(self)
        # 不将 api_key 持久化到磁盘，防止泄露
        data.pop("api_key", None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str = "settings.json") -> "Settings":
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # 合并策略：JSON 值为 None 时回退到环境变量默认值
            # 注意：0、0.0、空字符串 "" 和 False 都是合法值，不视为未设置
            merged = {}
            for k in cls.__dataclass_fields__:
                json_val = data.get(k)
                default_val = cls.__dataclass_fields__[k].default
                if json_val is not None:
                    merged[k] = json_val
                else:
                    merged[k] = default_val
            return cls(**merged)
        return cls()


SETTINGS = Settings.load()
