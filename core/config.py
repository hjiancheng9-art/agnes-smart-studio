"""配置管理 - 模型列表、分辨率预设、Prompt模板库、用户偏好持久化"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ── 常量 ──────────────────────────────────────────────────

MODELS = {
    "text_light": {
        "id": "agnes-1.5-flash",
        "name": "Agnes 1.5 Flash",
        "type": "text",
        "multimodal": True,
        "thinking": False,
        "tools": False,
    },
    "text_pro": {
        "id": "agnes-2.0-flash",
        "name": "Agnes 2.0 Flash",
        "type": "text",
        "multimodal": False,
        "thinking": True,
        "tools": True,
    },
    "image_hd": {
        "id": "agnes-image-2.1-flash",
        "name": "Agnes Image 2.1 Flash",
        "type": "image",
        "supports_img2img": True,
        "high_density": True,
    },
    "image_edit": {
        "id": "agnes-image-2.0-flash",
        "name": "Agnes Image 2.0 Flash",
        "type": "image",
        "supports_img2img": True,
        "supports_multi_image": True,
        "requires_tags_for_i2i": True,
    },
    "video": {
        "id": "agnes-video-v2.0",
        "name": "Agnes Video V2.0",
        "type": "video",
        "modes": ["ti2vid", "keyframes"],
    },
}

# 视觉模型常量 — 始终指向 Agnes 多模态模型，与主对话供应商解耦
# 用途：ChatSession 的 vision_client 专用，/vision 命令 + send_stream 图片路由
AGNES_VISION_MODEL = "agnes-1.5-flash"
AGNES_VISION_BASE_URL = "https://apihub.agnes-ai.com/v1"

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
    api_key: str = os.getenv("AGNES_API_KEY", "")
    base_url: str = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
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

    def save(self, path: str = "settings.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str = "settings.json") -> "Settings":
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return cls()


SETTINGS = Settings.load()
