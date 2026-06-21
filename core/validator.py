"""参数校验器 - num_frames 8n+1、尺寸、模型名等"""

from .config import VALID_NUM_FRAMES, VIDEO_ASPECT_RATIOS, IMAGE_SIZES, MODELS


__all__ = [
    "ValidationError", "validate_frame_rate", "validate_image_size", "validate_image_urls", "validate_model", "validate_num_frames", "validate_seed", "validate_video_resolution",
]
class ValidationError(ValueError):
    """参数校验错误"""
    pass


def validate_num_frames(num_frames: int) -> int:
    """校验 num_frames 必须满足 8n+1 且 <=441，自动修正为最近合法值"""
    if num_frames in VALID_NUM_FRAMES:
        return num_frames

    # 找最近的合法值
    closest = min(VALID_NUM_FRAMES, key=lambda x: abs(x - num_frames))
    if num_frames < VALID_NUM_FRAMES[0]:
        return VALID_NUM_FRAMES[0]
    if num_frames > VALID_NUM_FRAMES[-1]:
        return VALID_NUM_FRAMES[-1]
    return closest


def validate_video_resolution(width: int, height: int) -> tuple[int, int]:
    """校验视频分辨率，匹配预设比例"""
    for _name, (w, h) in VIDEO_ASPECT_RATIOS.items():
        if (width, height) == (w, h):
            return width, height

    # 尝试匹配最接近的预设
    ratio = width / height
    best = None
    best_diff = float("inf")
    for _name, (w, h) in VIDEO_ASPECT_RATIOS.items():
        diff = abs(ratio - w / h)
        if diff < best_diff:
            best_diff = diff
            best = (w, h)

    return best or (1152, 768)


def validate_image_size(size: str) -> str:
    """校验图片尺寸字符串格式"""
    if size in IMAGE_SIZES.values():
        return size

    # 解析 WxH 格式
    try:
        w, h = size.lower().split("x")
        w, h = int(w), int(h)
        return f"{w}x{h}"
    except (ValueError, AttributeError):
        raise ValidationError(f"无效的图片尺寸: {size}，格式应为 WxH，如 1024x768") from None


def validate_model(model_id: str, expected_type: str | None = None) -> str:
    """校验模型ID是否存在，可选校验类型"""
    all_model_ids = [m["id"] for m in MODELS.values()]
    if model_id not in all_model_ids:
        raise ValidationError(f"未知模型: {model_id}，可选: {all_model_ids}")

    if expected_type:
        for m in MODELS.values():
            if m["id"] == model_id:
                if m.get("type") != expected_type:
                    raise ValidationError(
                        f"模型 {model_id} 类型为 {m.get('type')}，期望 {expected_type}"
                    )
                break
    return model_id


def validate_frame_rate(frame_rate: int) -> int:
    """校验帧率 1-60"""
    return max(1, min(60, frame_rate))


def validate_seed(seed: int | None) -> int | None:
    """校验种子值"""
    if seed is None:
        return None
    return max(0, min(2**31 - 1, seed))


def validate_image_urls(urls: str | list[str]) -> list[str]:
    """校验图片URL列表"""
    if isinstance(urls, str):
        urls = [urls]
    if not urls:
        raise ValidationError("至少需要一张图片URL")
    for url in urls:
        if not url.startswith(("http://", "https://", "data:image/")):
            raise ValidationError(f"无效的图片URL: {url[:50]}...")
    return urls
