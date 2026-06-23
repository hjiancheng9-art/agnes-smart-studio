"""视频模型能力注册表 — 时长上限 / 分辨率 / 帧率 / 模式

这是全局约束表。模型时长是一个全局变量，决定了：
- 分镜总时长上限
- 每个镜头的 duration 上限
- 需要多少次 generate_video 调用
- 最终成片的节奏和镜头数
- 资产数量和复杂度

工作启动前必须先锁定模型 → 查表获取时长 → 以此为基准推进全流程。

所有时长数据以秒为单位。
"""

import json

__all__ = [
    'VIDEO_MODELS', 'VIDEO_MODEL_EXECUTOR_MAP', 'VIDEO_MODEL_TOOL_DEFS', 'auto_select_model', 'execute_video_model_info', 'get_model_capability', 'list_video_models',
]

# ============================================================
#  模型能力注册表（按单段时长排序，方便查阅）
# ============================================================

VIDEO_MODELS = {
    # ── 即梦 Jimeng（最长单段15s）──
    "jimeng": {
        "display_name": "即梦 Jimeng",
        "provider": "ByteDance / 字节跳动",
        "max_duration_s": 15.0,
        "default_duration_s": 5.0,
        "frame_rate": 24,
        "resolution": "最高 1080p",
        "modes": ["text_to_video", "image_to_video", "text_to_image"],
        "note": "单段最长15s，目前所有模型中最长。图生视频/文生视频均支持。API优先",
    },

    # ── Omni ──
    "omni": {
        "display_name": "Omni",
        "provider": "Google / Omni",
        "max_duration_s": 10.0,
        "default_duration_s": 5.0,
        "frame_rate": 24,
        "resolution": "最高 1080p",
        "modes": ["text_to_video", "image_to_video"],
        "note": "单段最长10s。Playwright 自动化，需登录",
    },

    # ── 可灵 Kling ──
    "kling": {
        "display_name": "可灵 Kling",
        "provider": "Kuaishou / 快手",
        "max_duration_s": 10.0,
        "default_duration_s": 5.0,
        "frame_rate": 30,
        "resolution": "最高 1080p",
        "modes": ["text_to_video", "image_to_video"],
        "config_key": "duration",
        "note": "免费用户可能限5s，付费用户10s。API优先",
    },

    # ── Runway ──
    "runway": {
        "display_name": "Runway Gen-3/Gen-4",
        "provider": "RunwayML",
        "max_duration_s": 10.0,
        "default_duration_s": 5.0,
        "frame_rate": 24,
        "resolution": "最高 4K",
        "modes": ["text_to_video", "image_to_video", "video_to_video"],
        "note": "Gen-3 5s/10s, Gen-4 可能更长。API优先",
    },

    # ── VEO 3.1 ──
    "veo": {
        "display_name": "VEO 3.1",
        "provider": "Google DeepMind",
        "max_duration_s": 8.0,
        "default_duration_s": 5.0,
        "frame_rate": 24,
        "resolution": "最高 1080p",
        "modes": ["text_to_video", "image_to_video"],
        "note": "单段最长8s。Playwright 自动化",
    },

    # ── Opal ──
    "opal": {
        "display_name": "Google Opal",
        "provider": "Google",
        "max_duration_s": 8.0,
        "default_duration_s": 5.0,
        "frame_rate": 24,
        "resolution": "最高 1080p",
        "modes": ["text_to_video"],
        "note": "单段最长8s。Playwright 自动化",
    },

    # ── CRUX API ──
    "agnes-video-v2.0": {
        "display_name": "CRUX Video v2.0",
        "provider": "CRUX AI",
        "max_duration_s": 5.0,         # 121 frames @ 24fps ≈ 5s
        "default_duration_s": 5.0,
        "max_frames": 121,
        "default_frame_rate": 24,
        "resolution": "1152x768 (默认) / 最高2K",
        "modes": ["text_to_video", "image_to_video", "multi_image_video", "keyframe_animation"],
        "note": "内置模型，默认即可用。5s/段，需拆分多次拼接长视频",
    },

    # ── Luma ──
    "luma": {
        "display_name": "Luma Dream Machine",
        "provider": "Luma AI",
        "max_duration_s": 5.0,
        "default_duration_s": 5.0,
        "frame_rate": 24,
        "resolution": "最高 1080p",
        "modes": ["text_to_video", "image_to_video"],
        "note": "固定5s/段，多次调用拼接",
    },

    # ── ComfyUI 本地 ──
    "comfyui-ltx": {
        "display_name": "ComfyUI LTX Video",
        "provider": "Local GPU",
        "max_duration_s": 5.0,
        "default_duration_s": 3.0,
        "frame_rate": 24,
        "resolution": "768x512 典型",
        "modes": ["text_to_video", "image_to_video"],
        "note": "本地较新模型",
    },

    "comfyui-svd": {
        "display_name": "ComfyUI SVD",
        "provider": "Local GPU",
        "max_duration_s": 4.0,
        "default_duration_s": 2.0,
        "frame_rate": 6,
        "max_frames": 25,
        "resolution": "576x1024 典型",
        "modes": ["image_to_video"],
        "note": "图生视频专用",
    },

    "comfyui-animatediff": {
        "display_name": "ComfyUI AnimateDiff",
        "provider": "Local GPU",
        "max_duration_s": 3.0,
        "default_duration_s": 2.0,
        "frame_rate": 8,
        "max_frames": 16,
        "resolution": "512x512 典型",
        "modes": ["text_to_video", "image_to_video"],
        "note": "SD1.5 基础，时长最短",
    },

    # ── 纯图片模型（时长=0，用于资产生成）──
    "dalle": {
        "display_name": "DALL-E 3",
        "provider": "OpenAI",
        "max_duration_s": 0,
        "default_duration_s": 0,
        "resolution": "最高 1792x1024",
        "modes": ["text_to_image"],
        "note": "仅图片，用于资产图/关键帧",
    },
    "gemini": {
        "display_name": "Gemini (Imagen)",
        "provider": "Google",
        "max_duration_s": 0,
        "default_duration_s": 0,
        "resolution": "最高 2K",
        "modes": ["text_to_image"],
        "note": "图片生成，可做视觉理解/资产生成",
    },
}

# ============================================================
#  查询工具
# ============================================================

def get_model_capability(model_id: str) -> dict | None:
    """获取单个模型的能力"""
    return VIDEO_MODELS.get(model_id)

def list_video_models(mode_filter: str = "") -> list[dict]:
    """列出所有视频模型，可按模式过滤。不传过滤返回全部。

    mode_filter: "text_to_video" / "image_to_video" / 空=全部
    """
    result = []
    for mid, info in VIDEO_MODELS.items():
        if info["max_duration_s"] <= 0:
            continue  # 跳过纯图片模型
        if mode_filter and mode_filter not in info.get("modes", []):
            continue
        result.append({
            "id": mid,
            "display_name": info["display_name"],
            "provider": info["provider"],
            "max_duration_s": info["max_duration_s"],
            "default_duration_s": info["default_duration_s"],
            "modes": info["modes"],
            "note": info.get("note", ""),
        })
    return result

def auto_select_model(total_duration_s: float, preferred: str = "") -> dict:
    """根据需要的总时长，推荐模型并计算需要调用次数。

    Returns:
        {"model": "kling", "max_per_call": 10.0, "calls_needed": 3, "segment_duration_s": 10.0}
    """
    if preferred and preferred in VIDEO_MODELS:
        model = VIDEO_MODELS[preferred]
    else:
        # 优先选 CRUX 原生模型
        model = VIDEO_MODELS.get("agnes-video-v2.0") or VIDEO_MODELS.get("kling")

    if model is None:
        raise KeyError("VIDEO_MODELS 为空，无法选择视频模型")

    max_per = model["max_duration_s"]
    if max_per <= 0:
        max_per = 5.0

    calls = max(1, round(total_duration_s / max_per + 0.4))  # 向上取整
    seg_dur = min(max_per, total_duration_s / calls)

    return {
        "model": preferred or "agnes-video-v2.0",
        "model_display": model["display_name"],
        "max_per_call_s": max_per,
        "calls_needed": calls,
        "segment_duration_s": round(seg_dur, 1),
        "total_duration_s": total_duration_s,
    }

def execute_video_model_info(model_id: str = "") -> str:
    """查看视频模型的时长和能力信息。

    Args:
        model_id: 模型ID（如 agnes-video-v2.0 / kling / runway / luma / comfyui-svd）。
                  不传列出所有可用视频模型。

    Returns:
        JSON 字符串，含模型能力详情
    """
    if model_id:
        model = get_model_capability(model_id)
        if not model:
            all_ids = [mid for mid, m in VIDEO_MODELS.items() if m["max_duration_s"] > 0]
            return json.dumps({
                "error": f"未知视频模型: {model_id}",
                "available_ids": all_ids,
                "success": False,
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "model_id": model_id,
            **model,
        }, ensure_ascii=False)

    models = list_video_models()
    return json.dumps({
        "success": True,
        "total_models": len(models),
        "models": models,
        "summary": (
            "单段时长排序：即梦jimeng(15s) > omni(10s) = kling(10s) = runway(10s) > veo(8s) = opal(8s) > agnes(5s) = luma(5s) > comfyui(3-5s)。"
            "时长是全局约束：选模型 → 锁定时长上限 → 以此规划分镜数、镜头数、资产数和总时长。"
        ),
    }, ensure_ascii=False)

# ============================================================
#  工具定义与执行器映射
# ============================================================

VIDEO_MODEL_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "video_model_info",
            "description": "查看视频模型的时长上限和能力信息。拆分镜/生成视频前必须调用，确保每个视频段不超过模型时长上限。不传参数列出所有可用模型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_id": {
                        "type": "string",
                        "description": "模型ID: agnes-video-v2.0 / kling / runway / luma / jimeng / comfyui-svd 等。不传列出全部"
                    },
                },
                "required": [],
            },
        },
    },
]

VIDEO_MODEL_EXECUTOR_MAP = {
    "video_model_info": lambda **kw: execute_video_model_info(
        model_id=kw.get("model_id", ""),
    ),
}
