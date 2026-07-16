"""图像编辑引擎 — Pillow + ffmpeg 封装（引擎级图像后处理）

对称于 video_editor / audio_tools：视频/音频都有完整后期，图像此前只有"生成"。
提供 6 个工具：
- image_resize: 等比缩放 / 指定尺寸（不失真，可选填充背景）
- image_crop:   自由裁剪 / 比例裁剪（正方/16:9/9:16/4:3/自定义）
- image_watermark: 加文字水印（支持位置/字号/颜色/透明度）
- image_color:  调色滤镜（亮度/对比度/饱和度 + 预设：复古/黑白/冷调/暖调/高饱和）
- image_convert: 格式批量转换（png/jpg/webp）+ 可控质量压缩
- image_compose: 多图排版（横向/纵向拼接 + 网格）

所有工具输出到 output/images/ 目录。
返回 JSON 字符串，与 video_editor/audio_tools 协议一致。
"""

import json
import subprocess
from pathlib import Path

__all__ = [
    "IMAGE_EXECUTOR_MAP",
    "IMAGE_OUT",
    "IMAGE_TOOL_DEFS",
    "OUTPUT_ROOT",
    "execute_image_color",
    "execute_image_compose",
    "execute_image_convert",
    "execute_image_crop",
    "execute_image_resize",
    "execute_image_watermark",
]

OUTPUT_ROOT = Path(__file__).parent.parent / "output"
IMAGE_OUT = OUTPUT_ROOT / "images"
IMAGE_OUT.mkdir(parents=True, exist_ok=True)


def _run(cmd: list, timeout: int = 120, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run 安全封装（委托给 run_subprocess）"""
    from core.mcp_servers._mcp_utils import run_subprocess as _rs

    return _rs(cmd, timeout=timeout, **kwargs)


def _check_pillow() -> str | None:
    """检查 Pillow 是否可用，返回错误文本或 None"""
    try:
        from PIL import Image  # noqa: F401

        return None
    except ImportError:
        return "Pillow 不可用，请安装: pip install Pillow"


def _check_image(path: str) -> str | None:
    """检查图片文件是否存在且可打开"""
    if not path:
        return "未提供图片路径"
    if not Path(path).exists():
        return f"图片不存在: {path}"
    return None


def _safe_output_path(prefix: str, ext: str = ".png") -> str:
    """生成唯一输出路径"""
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    i = 0
    while True:
        suffix = f"_{i}" if i else ""
        p = IMAGE_OUT / f"{prefix}_{ts}{suffix}{ext}"
        if not p.exists():
            return str(p)
        i += 1


def _fmt_size(n: int) -> str:
    """字节数 → 可读字符串"""
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / 1024 / 1024:.2f}MB"


# ============================================================
#  工具1: image_resize — 等比缩放 / 指定尺寸
# ============================================================


def execute_image_resize(
    image_path: str,
    width: int = 0,
    height: int = 0,
    fit: str = "contain",
    bg_color: str = "#000000",
    project_name: str = "",
) -> str:
    """缩放图片。

    Args:
        image_path: 图片路径
        width: 目标宽度（0=按 height 等比）
        height: 目标高度（0=按 width 等比）
        fit: contain=等比缩放填充背景 / cover=裁剪填满 / stretch=拉伸
        bg_color: contain 模式的填充背景色
        project_name: 输出命名
    """
    err = _check_pillow() or _check_image(image_path)
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)
    if width <= 0 and height <= 0:
        return json.dumps({"error": "width 和 height 至少给一个", "success": False}, ensure_ascii=False)

    from PIL import Image

    try:
        with Image.open(image_path) as f:
            img = f.convert("RGB")
        ow, oh = img.size
        tw = width if width > 0 else ow
        th = height if height > 0 else oh

        if fit == "stretch":
            out = img.resize((tw, th), Image.Resampling.LANCZOS)
        elif fit == "cover":
            # 等比放大后居中裁剪
            scale = max(tw / ow, th / oh)
            nw, nh = int(ow * scale), int(oh * scale)
            tmp = img.resize((nw, nh), Image.Resampling.LANCZOS)
            left = (nw - tw) // 2
            top = (nh - th) // 2
            out = tmp.crop((left, top, left + tw, top + th))
        else:  # contain
            scale = min(tw / ow, th / oh)
            nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
            tmp = img.resize((nw, nh), Image.Resampling.LANCZOS)
            # 解析背景色
            try:
                from PIL import ImageColor

                bg = ImageColor.getrgb(bg_color)
            except (ValueError, TypeError):
                bg = (0, 0, 0)
            out = Image.new("RGB", (tw, th), bg)
            out.paste(tmp, ((tw - nw) // 2, (th - nh) // 2))

        prefix = project_name or "resize"
        out_path = _safe_output_path(prefix, ".png")
        out.save(out_path, "PNG")
        size = Path(out_path).stat().st_size
        return json.dumps(
            {
                "success": True,
                "output_path": out_path,
                "original_size": f"{ow}x{oh}",
                "new_size": f"{out.size[0]}x{out.size[1]}",
                "fit": fit,
                "file_size": _fmt_size(size),
                "message": f"已缩放 {ow}x{oh} → {out.size[0]}x{out.size[1]} ({fit})",
            },
            ensure_ascii=False,
        )
    except (OSError, ValueError, TypeError) as e:
        return json.dumps({"error": f"缩放失败: {e}", "success": False}, ensure_ascii=False)


# ============================================================
#  工具2: image_crop — 裁剪
# ============================================================


def execute_image_crop(
    image_path: str,
    ratio: str = "free",
    x: int = 0,
    y: int = 0,
    width: int = 0,
    height: int = 0,
    project_name: str = "",
) -> str:
    """裁剪图片。

    Args:
        image_path: 图片路径
        ratio: 预设比例 1:1/16:9/9:16/4:3/3:4 或 free（用 x/y/width/height）
        x,y,width,height: free 模式的裁剪框（像素）
        project_name: 输出命名
    """
    err = _check_pillow() or _check_image(image_path)
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    from PIL import Image

    try:
        with Image.open(image_path) as f:
            img = f.convert("RGB")
        ow, oh = img.size

        if ratio != "free":
            # 解析比例
            try:
                rw, rh = ratio.split(":")
                rw, rh = int(rw), int(rh)
            except (ValueError, AttributeError):
                return json.dumps({"error": f"无效比例: {ratio}，如 1:1/16:9"}, ensure_ascii=False)
            # 居中裁剪到该比例（取最大可行区域）
            target_ratio = rw / rh
            src_ratio = ow / oh
            if src_ratio > target_ratio:
                # 原图更宽，裁左右
                new_w = int(oh * target_ratio)
                left = (ow - new_w) // 2
                box = (left, 0, left + new_w, oh)
            else:
                new_h = int(ow / target_ratio)
                top = (oh - new_h) // 2
                box = (0, top, ow, top + new_h)
        else:
            w = width if width > 0 else ow - x
            h = height if height > 0 else oh - y
            x2, y2 = min(x + w, ow), min(y + h, oh)
            if x2 <= x or y2 <= y:
                return json.dumps({"error": "裁剪区域无效", "success": False}, ensure_ascii=False)
            box = (x, y, x2, y2)

        out = img.crop(box)
        prefix = project_name or "crop"
        out_path = _safe_output_path(prefix, ".png")
        out.save(out_path, "PNG")
        size = Path(out_path).stat().st_size
        return json.dumps(
            {
                "success": True,
                "output_path": out_path,
                "original_size": f"{ow}x{oh}",
                "cropped_size": f"{out.size[0]}x{out.size[1]}",
                "crop_box": list(box),
                "ratio": ratio,
                "file_size": _fmt_size(size),
                "message": f"已裁剪 {ow}x{oh} → {out.size[0]}x{out.size[1]} ({ratio})",
            },
            ensure_ascii=False,
        )
    except (OSError, ValueError, TypeError) as e:
        return json.dumps({"error": f"裁剪失败: {e}", "success": False}, ensure_ascii=False)


# ============================================================
#  工具3: image_watermark — 文字水印
# ============================================================


def execute_image_watermark(
    image_path: str,
    text: str,
    position: str = "bottom-right",
    font_size: int = 0,
    color: str = "#FFFFFF",
    opacity: int = 80,
    project_name: str = "",
) -> str:
    """添加文字水印。

    Args:
        image_path: 图片路径
        text: 水印文字
        position: 位置 top/bottom-left/center/right 或 center
        font_size: 字号（0=按图片宽度自适应，约 3%）
        color: 文字颜色 hex
        opacity: 不透明度 0-255（默认80，半透明）
        project_name: 输出命名
    """
    err = _check_pillow() or _check_image(image_path)
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)
    if not text:
        return json.dumps({"error": "水印文字不能为空", "success": False}, ensure_ascii=False)

    from PIL import Image, ImageDraw, ImageFont

    try:
        with Image.open(image_path) as f:
            img = f.convert("RGBA")
        ow, oh = img.size

        # 字体：优先中文字体，自适应字号
        if font_size <= 0:
            font_size = max(16, int(ow * 0.03))
        font = None
        for fp in [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "arial.ttf",
            "DejaVuSans.ttf",
        ]:
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.load_default()

        # 透明层画文字
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            from PIL import ImageColor

            rgb = ImageColor.getrgb(color)
        except (ValueError, TypeError):
            rgb = (255, 255, 255)
        fill = (rgb[0], rgb[1], rgb[2], max(0, min(255, opacity)))

        # 计算文字尺寸
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = max(8, int(ow * 0.02))

        pos = position.lower()
        if "center" in pos and "left" not in pos and "right" not in pos:
            x, y = (ow - tw) // 2, (oh - th) // 2
        else:
            x = margin if "left" in pos else (ow - tw - margin if "right" in pos else (ow - tw) // 2)
            y = margin if "top" in pos else (oh - th - margin if "bottom" in pos else (oh - th) // 2)

        # 加描边提升可读性
        draw.text((x, y), text, font=font, fill=fill, stroke_width=2, stroke_fill=(0, 0, 0, opacity // 2))

        out = Image.alpha_composite(img, overlay).convert("RGB")
        prefix = project_name or "watermark"
        out_path = _safe_output_path(prefix, ".png")
        out.save(out_path, "PNG")
        size = Path(out_path).stat().st_size
        return json.dumps(
            {
                "success": True,
                "output_path": out_path,
                "watermark_text": text,
                "position": position,
                "font_size": font_size,
                "file_size": _fmt_size(size),
                "message": f'已加水印 "{text}" @ {position}',
            },
            ensure_ascii=False,
        )
    except (OSError, ValueError, TypeError) as e:
        return json.dumps({"error": f"加水印失败: {e}", "success": False}, ensure_ascii=False)


# ============================================================
#  工具4: image_color — 调色滤镜
# ============================================================

# 预设滤镜参数（亮度/对比度/饱和度，1.0=原值）
_COLOR_PRESETS = {
    "vintage": (1.05, 0.90, 0.70),  # 复古：降饱和降对比
    "mono": (1.0, 1.10, 0.0),  # 黑白：饱和度归零
    "cool": (1.0, 1.05, 1.10),  # 冷调：提饱和
    "warm": (1.05, 1.0, 1.0),  # 暖调：提亮度
    "vivid": (1.0, 1.15, 1.40),  # 高饱和冲击
    "soft": (1.10, 0.85, 0.95),  # 柔和梦幻
}


def execute_image_color(
    image_path: str,
    preset: str = "",
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    project_name: str = "",
) -> str:
    """调整图像色彩。

    Args:
        image_path: 图片路径
        preset: 预设 vintage/mono/cool/warm/vivid/soft（覆盖下面的手动值）
        brightness: 亮度 0-2（1=不变）
        contrast: 对比度 0-2
        saturation: 饱和度 0-2
        project_name: 输出命名
    """
    err = _check_pillow() or _check_image(image_path)
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    from PIL import Image, ImageEnhance

    # 预设覆盖手动值
    applied = {"brightness": brightness, "contrast": contrast, "saturation": saturation}
    if preset:
        if preset not in _COLOR_PRESETS:
            avail = "/".join(_COLOR_PRESETS.keys())
            return json.dumps({"error": f"未知预设 {preset}，可选: {avail}"}, ensure_ascii=False)
        brightness, contrast, saturation = _COLOR_PRESETS[preset]
        applied = {"brightness": brightness, "contrast": contrast, "saturation": saturation}

    try:
        with Image.open(image_path) as f:
            img = f.convert("RGB")
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(saturation)

        prefix = project_name or (f"color_{preset}" if preset else "color")
        out_path = _safe_output_path(prefix, ".png")
        img.save(out_path, "PNG")
        size = Path(out_path).stat().st_size
        label = f"预设 {preset}" if preset else "手动调色"
        return json.dumps(
            {
                "success": True,
                "output_path": out_path,
                "preset": preset,
                "params": applied,
                "file_size": _fmt_size(size),
                "message": f"已{label} (亮{brightness:.2f}/对比{contrast:.2f}/饱和{saturation:.2f})",
            },
            ensure_ascii=False,
        )
    except (OSError, ValueError, TypeError) as e:
        return json.dumps({"error": f"调色失败: {e}", "success": False}, ensure_ascii=False)


# ============================================================
#  工具5: image_convert — 格式转换 + 压缩
# ============================================================


def execute_image_convert(image_path: str, format: str = "jpg", quality: int = 92, project_name: str = "") -> str:
    """转换图片格式并控制压缩质量。

    Args:
        image_path: 图片路径（支持 png/jpg/webp/bmp 互转）
        format: 目标格式 jpg/png/webp
        quality: 质量 1-100（jpg/webp 有效，默认92）
        project_name: 输出命名
    """
    err = _check_pillow() or _check_image(image_path)
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    fmt = format.lower().lstrip(".")
    if fmt not in ("jpg", "jpeg", "png", "webp"):
        return json.dumps({"error": f"不支持的目标格式 {format}，可选: jpg/png/webp"}, ensure_ascii=False)
    if fmt == "jpeg":
        fmt = "jpg"

    from PIL import Image

    try:
        with Image.open(image_path) as f:
            img = f.convert("RGB")
        orig_size = Path(image_path).stat().st_size
        prefix = project_name or "convert"
        ext = ".jpg" if fmt == "jpg" else f".{fmt}"
        out_path = _safe_output_path(prefix, ext)

        if fmt in ("jpg", "webp"):
            img.save(
                out_path, fmt.upper() if fmt == "jpg" else "WEBP", quality=max(1, min(100, quality)), optimize=True
            )
        else:  # png 无损
            img.save(out_path, "PNG", optimize=True)

        new_size = Path(out_path).stat().st_size
        ratio = (1 - new_size / orig_size) * 100 if orig_size else 0
        return json.dumps(
            {
                "success": True,
                "output_path": out_path,
                "format": fmt,
                "quality": quality,
                "original_size": _fmt_size(orig_size),
                "new_size": _fmt_size(new_size),
                "change": f"{ratio:+.0f}%",
                "message": f"已转 {fmt} ({quality}质量) {_fmt_size(orig_size)}→{_fmt_size(new_size)} ({ratio:+.0f}%)",
            },
            ensure_ascii=False,
        )
    except (OSError, ValueError, TypeError) as e:
        return json.dumps({"error": f"转换失败: {e}", "success": False}, ensure_ascii=False)


# ============================================================
#  工具6: image_compose — 多图排版
# ============================================================


def execute_image_compose(
    image_paths: str, layout: str = "horizontal", gap: int = 10, bg_color: str = "#FFFFFF", project_name: str = ""
) -> str:
    """多图排版拼接（横向/纵向/网格）。

    Args:
        image_paths: JSON 数组字符串，如 '["1.png","2.png"]'
        layout: horizontal/vertical/grid
        gap: 间距像素
        bg_color: 背景色
        project_name: 输出命名
    """
    err = _check_pillow()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    try:
        paths = json.loads(image_paths) if isinstance(image_paths, str) else image_paths
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": "image_paths 必须是 JSON 数组字符串"}, ensure_ascii=False)

    if not paths or len(paths) < 2:
        return json.dumps({"error": "至少需要 2 张图", "success": False}, ensure_ascii=False)

    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        return json.dumps({"error": f"图片不存在: {missing}", "success": False}, ensure_ascii=False)

    from PIL import Image, ImageColor

    try:
        imgs = []
        for p in paths:
            with Image.open(p) as f:
                imgs.append(f.convert("RGB"))
        n = len(imgs)

        # 统一高度（横向）或宽度（纵向）到最小的，避免错位
        cols = 0
        cell_w = 0
        cell_h = 0
        if layout == "horizontal":
            min_h = min(im.size[1] for im in imgs)
            imgs = [im.resize((int(im.size[0] * min_h / im.size[1]), min_h), Image.Resampling.LANCZOS) for im in imgs]
            total_w = sum(im.size[0] for im in imgs) + gap * (n - 1)
            total_h = min_h
        elif layout == "vertical":
            min_w = min(im.size[0] for im in imgs)
            imgs = [im.resize((min_w, int(im.size[1] * min_w / im.size[0])), Image.Resampling.LANCZOS) for im in imgs]
            total_w = min_w
            total_h = sum(im.size[1] for im in imgs) + gap * (n - 1)
        else:  # grid
            cols = 2 if n <= 4 else 3
            rows = (n + cols - 1) // cols
            # 统一到统一单元格尺寸（取平均）
            cell_w = min(im.size[0] for im in imgs)
            cell_h = min(im.size[1] for im in imgs)
            imgs = [im.resize((cell_w, cell_h), Image.Resampling.LANCZOS) for im in imgs]
            total_w = cols * cell_w + gap * (cols - 1)
            total_h = rows * cell_h + gap * (rows - 1)

        try:
            bg = ImageColor.getrgb(bg_color)
        except (ValueError, TypeError):
            bg = (255, 255, 255)
        canvas = Image.new("RGB", (total_w, total_h), bg)

        if layout == "horizontal":
            x = 0
            for im in imgs:
                canvas.paste(im, (x, 0))
                x += im.size[0] + gap
        elif layout == "vertical":
            y = 0
            for im in imgs:
                canvas.paste(im, (0, y))
                y += im.size[1] + gap
        else:  # grid
            for i, im in enumerate(imgs):
                col = i % cols
                row = i // cols
                x = col * (cell_w + gap)
                y = row * (cell_h + gap)
                canvas.paste(im, (x, y))

        prefix = project_name or "compose"
        out_path = _safe_output_path(prefix, ".png")
        canvas.save(out_path, "PNG")
        size = Path(out_path).stat().st_size
        return json.dumps(
            {
                "success": True,
                "output_path": out_path,
                "layout": layout,
                "image_count": n,
                "canvas_size": f"{total_w}x{total_h}",
                "file_size": _fmt_size(size),
                "message": f"已拼接 {n} 张图 ({layout}) → {total_w}x{total_h}",
            },
            ensure_ascii=False,
        )
    except (OSError, ValueError, TypeError) as e:
        return json.dumps({"error": f"拼接失败: {e}", "success": False}, ensure_ascii=False)


# ============================================================
#  工具定义（OpenAI function 格式）
# ============================================================

IMAGE_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "image_resize",
            "description": "缩放图片。支持等比缩放(contain填充背景)、裁剪填满(cover)、拉伸(stretch)。用于改尺寸/适配比例。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片路径"},
                    "width": {"type": "integer", "description": "目标宽度(0=按height等比)"},
                    "height": {"type": "integer", "description": "目标高度(0=按width等比)"},
                    "fit": {"type": "string", "description": "contain/cover/stretch，默认contain"},
                    "bg_color": {"type": "string", "description": "contain模式填充色，默认#000000"},
                    "project_name": {"type": "string", "description": "输出命名前缀"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_crop",
            "description": "裁剪图片。支持预设比例(1:1/16:9/9:16/4:3/3:4居中裁剪)或自由裁剪(指定x/y/width/height)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片路径"},
                    "ratio": {"type": "string", "description": "比例1:1/16:9/9:16/4:3/3:4，或free用坐标"},
                    "x": {"type": "integer", "description": "free模式裁剪起点x"},
                    "y": {"type": "integer", "description": "free模式裁剪起点y"},
                    "width": {"type": "integer", "description": "free模式裁剪宽度"},
                    "height": {"type": "integer", "description": "free模式裁剪高度"},
                    "project_name": {"type": "string", "description": "输出命名前缀"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_watermark",
            "description": "添加文字水印。支持位置/字号/颜色/透明度，自动描边保证可读性。用于加署名/logo文字/版权标记。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片路径"},
                    "text": {"type": "string", "description": "水印文字"},
                    "position": {
                        "type": "string",
                        "description": "top-left/top-right/bottom-left/bottom-right/center，默认bottom-right",
                    },
                    "font_size": {"type": "integer", "description": "字号(0=按图宽自适应约3%)"},
                    "color": {"type": "string", "description": "颜色hex，默认#FFFFFF"},
                    "opacity": {"type": "integer", "description": "不透明度0-255，默认80"},
                    "project_name": {"type": "string", "description": "输出命名前缀"},
                },
                "required": ["image_path", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_color",
            "description": "调整图像色彩。支持预设(vintage复古/mono黑白/cool冷调/warm暖调/vivid高饱和/soft柔和)或手动亮度/对比度/饱和度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片路径"},
                    "preset": {"type": "string", "description": "预设vintage/mono/cool/warm/vivid/soft(覆盖手动值)"},
                    "brightness": {"type": "number", "description": "亮度0-2(1=不变)"},
                    "contrast": {"type": "number", "description": "对比度0-2"},
                    "saturation": {"type": "number", "description": "饱和度0-2"},
                    "project_name": {"type": "string", "description": "输出命名前缀"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_convert",
            "description": "转换图片格式(png/jpg/webp互转)并控制压缩质量。用于减小文件体积、批量转格式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片路径"},
                    "format": {"type": "string", "description": "目标格式jpg/png/webp，默认jpg"},
                    "quality": {"type": "integer", "description": "质量1-100(jpg/webp有效)，默认92"},
                    "project_name": {"type": "string", "description": "输出命名前缀"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_compose",
            "description": "多图排版拼接(横向/纵向/网格)。用于做对比图、拼长图、套图组合。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_paths": {"type": "string", "description": 'JSON数组: ["1.png","2.png"]'},
                    "layout": {"type": "string", "description": "horizontal/vertical/grid，默认horizontal"},
                    "gap": {"type": "integer", "description": "间距像素，默认10"},
                    "bg_color": {"type": "string", "description": "背景色，默认#FFFFFF"},
                    "project_name": {"type": "string", "description": "输出命名前缀"},
                },
                "required": ["image_paths"],
            },
        },
    },
]

# ============================================================
#  执行器映射
# ============================================================

IMAGE_EXECUTOR_MAP = {
    "image_resize": lambda **kw: execute_image_resize(
        image_path=kw.get("image_path", ""),
        width=kw.get("width", 0),
        height=kw.get("height", 0),
        fit=kw.get("fit", "contain"),
        bg_color=kw.get("bg_color", "#000000"),
        project_name=kw.get("project_name", ""),
    ),
    "image_crop": lambda **kw: execute_image_crop(
        image_path=kw.get("image_path", ""),
        ratio=kw.get("ratio", "free"),
        x=kw.get("x", 0),
        y=kw.get("y", 0),
        width=kw.get("width", 0),
        height=kw.get("height", 0),
        project_name=kw.get("project_name", ""),
    ),
    "image_watermark": lambda **kw: execute_image_watermark(
        image_path=kw.get("image_path", ""),
        text=kw.get("text", ""),
        position=kw.get("position", "bottom-right"),
        font_size=kw.get("font_size", 0),
        color=kw.get("color", "#FFFFFF"),
        opacity=kw.get("opacity", 80),
        project_name=kw.get("project_name", ""),
    ),
    "image_color": lambda **kw: execute_image_color(
        image_path=kw.get("image_path", ""),
        preset=kw.get("preset", ""),
        brightness=kw.get("brightness", 1.0),
        contrast=kw.get("contrast", 1.0),
        saturation=kw.get("saturation", 1.0),
        project_name=kw.get("project_name", ""),
    ),
    "image_convert": lambda **kw: execute_image_convert(
        image_path=kw.get("image_path", ""),
        format=kw.get("format", "jpg"),
        quality=kw.get("quality", 92),
        project_name=kw.get("project_name", ""),
    ),
    "image_compose": lambda **kw: execute_image_compose(
        image_paths=kw.get("image_paths", "[]"),
        layout=kw.get("layout", "horizontal"),
        gap=kw.get("gap", 10),
        bg_color=kw.get("bg_color", "#FFFFFF"),
        project_name=kw.get("project_name", ""),
    ),
}
