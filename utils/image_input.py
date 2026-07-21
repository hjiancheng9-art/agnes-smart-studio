"""图片输入工具 - 支持URL/本地文件/Base64/剪贴板"""

import logging

logger = logging.getLogger(__name__)
import base64
from pathlib import Path

__all__ = ["clipboard_to_data_uri", "file_to_data_uri", "load_image_as_url_or_data"]


def load_image_as_url_or_data(source: str) -> str:
    """将图片输入转换为URL或Base64 data URI

    支持:
    - URL (http/https): 直接返回
    - 本地文件路径: 转为 base64 data URI
    - Base64字符串: 补全 data URI 前缀
    """
    # 去掉首尾引号（用户可能粘贴带引号的路径）
    source = source.strip().strip('"').strip("'")

    if source.startswith(("http://", "https://")):
        return source

    if source.startswith("data:image/"):
        return source

    # 尝试作为本地文件路径
    path = Path(source)
    if path.exists() and path.is_file():
        return file_to_data_uri(path)

    # 尝试作为纯Base64
    try:
        decoded = base64.b64decode(source[:100])
        if decoded[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"RIFF"):
            return f"data:image/png;base64,{source}"
    except (ValueError, TypeError, UnicodeDecodeError):
        logger.debug("silent except", exc_info=True)

    raise ValueError(f"无法识别的图片输入: {source[:50]}...")


def file_to_data_uri(path: Path) -> str:
    """将本地图片文件转为 Base64 data URI"""
    suffix = path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime = mime_map.get(suffix, "image/png")

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime};base64,{b64}"


def clipboard_to_data_uri() -> str | None:
    """从剪贴板粘贴图片（如果可用）"""
    try:
        from PIL import ImageGrab

        img = ImageGrab.grabclipboard()
        if img is None:
            return None
        # grabclipboard 可能返回 Image（位图）或 list[str]（文件路径列表）
        if isinstance(img, list):
            if not img:
                return None
            # 取第一个文件转 data URI
            return file_to_data_uri(Path(img[0]))
        # 非 list → 视为 PIL Image，用鸭子类型（save 方法）验证
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except (ImportError, OSError, ValueError):
        return None
