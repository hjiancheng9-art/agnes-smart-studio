"""ComfyFlow Compiler — 意图解析器 (自然语言 → TaskSpec + 生产意图分类)"""

from __future__ import annotations
import re
from typing import Dict, List, Optional

from .models import TaskSpec


# 风格关键词映射
STYLE_KEYWORDS: Dict[str, List[str]] = {
    "cinematic": ["电影", "电影感", "cinematic", "胶片", "film", "大片", "史诗"],
    "realistic": ["写实", "真实", "现实", "realistic", "photorealistic", "照片", "摄影"],
    "anime": ["动漫", "二次元", "anime", "漫画", "manga", "日系", "赛璐璐"],
    "cyberpunk": ["赛博", "cyberpunk", "霓虹", "未来", "科幻", "机械"],
    "fantasy": ["奇幻", "魔法", "魔幻", "fantasy", "龙", "精灵", "城堡"],
    "watercolor": ["水彩", "水彩画", "水墨", "watercolor"],
    "oil_painting": ["油画", "oil painting", "古典"],
    "sketch": ["素描", "速写", "sketch", "线稿"],
    "3d": ["3d", "3D", "渲染", "c4d", "blender", "octane"],
    "pixel": ["像素", "pixel art", "像素风"],
    "chinese_style": ["中国风", "国风", "水墨", "工笔", "古风"],
    "retro": ["复古", "retro", "vintage", "怀旧", "80s", "90s"],
    "minimalist": ["极简", "minimal", "简约", "留白"],
}

# 任务类型关键词
TASK_KEYWORDS: Dict[str, List[str]] = {
    "txt2img": ["生成", "画", "画一张", "做一张", "创作", "创建图像", "create"],
    "img2img": ["重绘", "改图", "换风格", "以图生图", "参考", "仿照", "重画"],
    "controlnet": ["姿态", "姿势", "骨架", "openpose", "深度", "depth", "边缘", "canny", "scribble"],
    "video": ["视频", "动图", "镜头", "动画", "video", "动画短片", "短视频"],
    "upscale": ["放大", "高清化", "超分", "upscale", "提升分辨率"],
    "character": ["角色一致", "人物一致", "换脸", "同一个人", "角色保持"],
}

# =============================================================================
# 生产意图分类器（2026 真实工作流范式）
# =============================================================================

PRODUCTION_INTENTS: Dict[str, Dict] = {
    "flux_generation": {
        "keywords": ["flux", "用flux", "flux出图", "高质量", "新一代"],
        "task_type": "txt2img",
        "priority": 5,
    },
    "ltx_video": {
        "keywords": ["ltx", "ltx视频", "ltx生成", "ltx2"],
        "task_type": "video",
        "priority": 6,
    },
    "wan_video": {
        "keywords": ["wan", "wan视频", "wan生成", "wan2"],
        "task_type": "video",
        "priority": 6,
    },
    "action_transfer": {
        "keywords": ["动作迁移", "动作参考", "动作模仿", "motion transfer", "跳舞", "舞蹈迁移", "舞蹈", "跟随动作"],
        "task_type": "video",
        "priority": 4,
    },
    "character_replace": {
        "keywords": ["角色替换", "换装", "换衣服", "换个衣服", "服装替换", "角色一致", "人物替换", "换造型", "变装"],
        "task_type": "img2img",
        "priority": 4,
    },
    "face_swap": {
        "keywords": ["换脸", "reactor", "faceid", "instantid", "pulid", "人脸替换", "换张脸"],
        "task_type": "img2img",
        "priority": 4,
    },
    "video_lipsync": {
        "keywords": ["对口型", "数字人", "口型同步", "lipsync", "说话", "讲话", "虚拟人"],
        "task_type": "video",
        "priority": 5,
    },
    "image_edit": {
        "keywords": ["编辑", "修改", "替换", "填充", "扩图", "remove", "擦除", "inpaint", "拓展"],
        "task_type": "img2img",
        "priority": 3,
    },
    "flux_to_ltx": {
        "keywords": ["flux转视频", "图片转视频", "图像动画化", "图像变视频", "img2video"],
        "task_type": "video",
        "priority": 5,
    },
}

# 宽高比关键词
ASPECT_RATIO_MAP: Dict[str, List[str]] = {
    "1:1": ["1:1", "方形", "正方形"],
    "3:2": ["3:2"],
    "4:3": ["4:3"],
    "16:9": ["16:9", "横屏", "宽屏", "横版"],
    "9:16": ["9:16", "竖屏", "竖版", "手机", "抖音", "短视频"],
    "2:3": ["2:3"],
    "3:4": ["3:4"],
    "21:9": ["21:9", "超宽"],
}

# 质量模式关键词
QUALITY_KEYWORDS: Dict[str, List[str]] = {
    "fast": ["快", "快速", "草稿", "预览", "实验"],
    "balanced": ["均衡", "平衡", "普通", "一般"],
    "high": ["高清", "高质量", "高品质", "精细", "精致", "细腻"],
    "cinematic": ["电影级", "顶级", "极致", "专业", "大师", "旗舰"],
}


def classify_production_intent(text: str) -> str:
    """分类生产意图 — 返回 production_intent 字符串"""
    text_lower = text.lower()

    best_intent = ""
    best_priority = 0
    best_match_count = 0

    for intent_name, config in PRODUCTION_INTENTS.items():
        match_count = sum(1 for kw in config["keywords"] if kw in text_lower)
        if match_count > 0:
            # 综合评分：匹配数 * 优先级
            score = match_count * config["priority"]
            if score > best_priority or (score == best_priority and match_count > best_match_count):
                best_priority = score
                best_match_count = match_count
                best_intent = intent_name

    return best_intent


def parse_intent(text: str) -> TaskSpec:
    """将自然语言解析为结构化 TaskSpec"""
    text_lower = text.lower()
    task = TaskSpec(task_type="txt2img", subject="")

    # 0. 生产意图分类（优先于传统方式）
    intent = classify_production_intent(text)
    task.production_intent = intent
    if intent:
        # 用生产意图的任务类型覆盖
        task.task_type = PRODUCTION_INTENTS[intent]["task_type"]

    # 1. 识别任务类型（如果生产意图没覆盖）
    if not intent:
        for task_type, keywords in TASK_KEYWORDS.items():
            if any(k in text_lower for k in keywords):
                task.task_type = task_type
                break

    # 2. 提取主体
    subject = text
    leading_patterns = [
        r'^(给[我]?画|生成|画|做|创建)(一[张个段幅只条])?',
        r'^(重绘|改图|换|模仿|仿照)(这[张个幅])?',
        r'^(按照|根据|以)(这[张个])?',
    ]
    for pat in leading_patterns:
        subject = re.sub(pat, '', subject)
    subject = re.sub(r'(生成|做|创建)(了|的|一[张个])?', '', subject)
    subject = re.sub(r'[,，]\s*[\d]+[:\d]+', '', subject)
    subject = re.sub(r'[\d]+[:\d]+\s*', '', subject)
    subject = re.sub(r'[，。！？、；：""''（）\(\)\[\]【】\s]', '', subject)
    subject = subject.strip()
    # 在风格词和核心名词之间加空格（改后更好看）
    for sw, noun in [("赛博朋克", "猫"), ("赛博朋克", "狗"), ("赛博朋克", "龙"),
                      ("二次元", "少女"), ("二次元", "男孩")]:
        if sw + noun in subject:
            subject = subject.replace(sw + noun, sw + " " + noun)
    task.subject = subject if len(subject) > 2 else text[:60]

    # 3. 识别风格
    for category, keywords in STYLE_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            task.style.append(category)
    if not task.style:
        task.style = ["realistic"]

    # 4. 识别氛围
    mood_keywords = {
        "温暖": ["温暖", "暖色", "夕阳", "黄昏", "阳光"],
        "冷峻": ["冷", "冷酷", "冷色", "蓝调", "阴天", "雨"],
        "黑暗": ["黑暗", "暗黑", "暗", "黑夜", "夜晚"],
        "明亮": ["明亮", "亮", "白天", "晴"],
        "梦幻": ["梦幻", "仙境", "迷幻"],
        "恐怖": ["恐怖", "惊悚", "诡异"],
    }
    for mood, keywords in mood_keywords.items():
        if any(k in text_lower for k in keywords):
            task.mood = mood
            break

    # 5. 识别宽高比
    for ratio, keywords in ASPECT_RATIO_MAP.items():
        if any(k in text_lower for k in keywords):
            task.aspect_ratio = ratio
            break

    # 6. 识别质量模式
    for mode, keywords in QUALITY_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            task.quality_mode = mode
            break

    # 7. 识别特殊需求
    task.needs_upscale = any(k in text_lower for k in ["放大", "高清化", "超分", "upscale", "4k"])
    task.needs_controlnet = any(k in text_lower for k in TASK_KEYWORDS["controlnet"])
    task.needs_video = any(k in text_lower for k in TASK_KEYWORDS["video"])
    if task.needs_controlnet:
        task.task_type = "controlnet"
    if task.needs_video and not intent:
        task.task_type = "video"

    return task
