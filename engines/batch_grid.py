"""批量变种生成 + 网格预览引擎

一次用不同 seed 生成多张变种（适合选最佳方案），自动拼成一张网格缩略图预览。
解决"生成 70 张图后只能逐张打开对比"的痛点。

用法:
    engine = BatchVariantEngine(client)
    result = engine.generate_variants(
        prompt="一只在雨中的猫",
        count=4,                 # 4/6/9 张
        seed=42,                 # 基准 seed，每张递增；None 则全部随机
        base_seed=None,          # 显式覆盖（同 seed=...）
        size="1024x768",
        negative_prompt="...",
        style=None,              # 风格微调，注入到每张 prompt 的不同变种方向
        on_progress=callback,    # callback(done, total, path)
    )
    # result = {
    #   "variants": [{"local_path","seed","prompt"}, ...],
    #   "grid_path": "output/images/grid_xxx.jpg",   # 拼图
    #   "count": 4,
    # }
"""
import random
from datetime import datetime
from pathlib import Path

from core.client import AgnesClient
from core.config import OUTPUT_DIR
from core.validator import validate_image_size, validate_model, validate_seed
from engines.text_to_image import TextToImageEngine

__all__ = ['BatchVariantEngine']



# 变种方向提示词后缀——给同主体加不同视觉变量，让 9 宫格有看头
# 仅当 style 未指定时循环使用，保持每张"同主体、不同味道"
_VARIANT_ANGLES = [
    "",                                    # 0号：原样，作为基准
    "golden hour warm backlight",          # 暖光逆光
    "moody low-key cinematic shadow",      # 低调电影感阴影
    "vibrant high saturation color pop",   # 高饱和色彩冲击
    "soft diffused overcast lighting",     # 柔和漫射光
    "dramatic side rim light, teal-orange",# 侧轮廓光 青橙调
    "minimalist clean composition",        # 极简构图
    "dynamic dutch angle, energetic",      # 倾斜构图 活力
    "ethereal foggy atmosphere",           # 仙气雾感
]

# 网格列数规则：count → cols
def _grid_cols(count: int) -> int:
    if count <= 1:
        return 1
    if count <= 4:
        return 2
    if count <= 6:
        return 3
    return 3  # 9 张 → 3x3


class BatchVariantEngine:
    """批量变种生成 + 网格预览"""

    def __init__(self, client: AgnesClient):
        self.client = client
        self.t2i = TextToImageEngine(client)

    def generate_variants(
        self,
        prompt: str,
        count: int = 4,
        seed: int | None = None,
        size: str = "1024x768",
        negative_prompt: str | None = None,
        model: str = "agnes-image-2.1-flash",
        style: str | list[str] | None = None,
        on_progress=None,
    ) -> dict:
        """生成 count 张变种并拼网格图。

        Args:
            prompt: 主体描述（已被 brain.enhance 增强过的也可以）
            count: 变种数量（建议 4/6/9）
            seed: 基准 seed。每张用 seed + i；None 则每张独立随机
            style: 自定义变种方向。
                   - None: 自动用 _VARIANT_ANGLES 循环
                   - str:  单一后缀，所有图都用（仅 seed 不同）
                   - list: 每张用不同后缀（长度>=count 才循环利用）
            on_progress: callback(done:int, total:int, path:str)
        """
        size = validate_image_size(size)
        validate_model(model, "image")
        count = max(1, min(9, count))  # 钳制 1-9

        # 准备每张的 seed
        if seed is not None:
            base = validate_seed(seed)
            assert base is not None  # validate_seed(None)→None; here seed is non-None
            seeds = [validate_seed(base + i) for i in range(count)]
        else:
            # 每张独立随机 seed（0 ~ 2^31-1）
            seeds = [random.randint(0, 2**31 - 1) for _ in range(count)]

        # 准备每张的风格后缀
        if style is None:
            angles = [_VARIANT_ANGLES[i % len(_VARIANT_ANGLES)] for i in range(count)]
        elif isinstance(style, str):
            angles = [style] * count
        else:  # list
            angles = [style[i % len(style)] for i in range(count)]

        variants = []
        failed = []
        for i in range(count):
            # 组装该张的 prompt：主体 + 变种方向（若有）
            v_prompt = f"{prompt}, {angles[i]}" if angles[i] else prompt
            try:
                data = self.t2i.generate(
                    prompt=v_prompt, model=model, size=size,
                    seed=seeds[i], negative_prompt=negative_prompt,
                )
                variants.append({
                    "local_path": data.get("local_path", ""),
                    "url": data.get("url", ""),
                    "seed": seeds[i],
                    "prompt": v_prompt,
                    "index": i,
                })
            except (RuntimeError, OSError) as e:
                failed.append({"index": i, "seed": seeds[i], "error": str(e)})
            if on_progress:
                on_progress(i + 1, count, variants[-1]["local_path"] if variants else "")

        # 拼网格图（至少有 1 张成功才拼）
        grid_path = ""
        if variants:
            try:
                grid_path = self._build_grid(variants)
            except (RuntimeError, OSError):
                grid_path = ""  # 拼图失败不阻塞，仍返回各图路径

        return {
            "variants": variants,
            "failed": failed,
            "grid_path": grid_path,
            "count": len(variants),
            "requested": count,
            "base_prompt": prompt,
        }

    def _build_grid(self, variants: list[dict]) -> str:
        """把变种的本地图片拼成一张网格预览图（带序号标注）。

        缩略图等比缩放到 cell 内，深色背景，左上角标序号+seed。
        返回保存路径。
        """
        from PIL import Image, ImageDraw, ImageFont

        # 缩略图单元尺寸
        cell_w, cell_h = 384, 288  # 4:3 缩略
        padding = 8
        label_h = 24
        bg = (18, 18, 24)

        cols = _grid_cols(len(variants))
        rows = (len(variants) + cols - 1) // cols

        grid_w = cols * cell_w + (cols + 1) * padding
        grid_h = rows * (cell_h + label_h) + (rows + 1) * padding

        grid = Image.new("RGB", (grid_w, grid_h), bg)
        draw = ImageDraw.Draw(grid)

        # 字体：优先系统字体，退回默认
        font = None
        for fp in ["arial.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"]:
            try:
                font = ImageFont.truetype(fp, 14)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.load_default()

        for i, v in enumerate(variants):
            path = v.get("local_path", "")
            if not path or not Path(path).exists():
                continue
            try:
                img = Image.open(path).convert("RGB")
            except (OSError, ValueError):
                continue
            # 等比缩放填入 cell
            img.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
            # 居中 paste
            cw, ch = img.size
            col = i % cols
            row = i // cols
            x = padding + col * (cell_w + padding) + (cell_w - cw) // 2
            y = padding + row * (cell_h + label_h) + (cell_h - ch) // 2
            grid.paste(img, (x, y))

            # 序号标签
            label_x = padding + col * (cell_w + padding)
            label_y = padding + row * (cell_h + label_h) + cell_h + 2
            seed = v.get("seed", "?")
            draw.text((label_x + 4, label_y), f"#{i+1} seed:{seed}",
                      fill=(180, 220, 255), font=font)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        grid_path = str(OUTPUT_DIR / "images" / f"variant_grid_{ts}.jpg")
        Path(grid_path).parent.mkdir(parents=True, exist_ok=True)
        grid.save(grid_path, "JPEG", quality=88)
        return grid_path
