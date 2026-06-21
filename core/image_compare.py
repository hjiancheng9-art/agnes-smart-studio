"""图像对比 / A-B 测试引擎 — 纯本地 + 多模态裁判

对称于 image_tools/video_editor：变种（generate_variants）会一次出多张图，
此前没有任何工具能真正"对比"它们 → 进化系统 (memory.prompt_evolution) 长期缺
高分样本。本模块补上这块关键拼图。

提供 3 种对比模式 + 1 个总入口：
- side_by_side : Pillow 拼接并排对比图（统一高度 + 标签 + 可选 winner 高亮）
- diff_heatmap : 像素级差异热力图（绝对差分 + 放大 + 伪彩色），定位改了哪里
- ai_judge     : 用视觉大模型（agnes-1.5-flash 多模态）同时看 N 张图，
                 按统一 rubric 打分并选出 winner，返回结构化 JSON
- compare_images: 总入口，按 mode 路由

所有模式均支持 2~4 张图。输出到 output/images/，返回 JSON 字符串，
与 image_tools 协议一致，可同时被 CLI / Agent 调度。
"""

import json
from datetime import datetime
from pathlib import Path

import httpx

__all__ = [
    'COMPARE_EXECUTOR_MAP', 'COMPARE_TOOL_DEFS', 'IMAGE_OUT', 'JUDGE_VISION_MODEL', 'OUTPUT_ROOT', 'compare_images_dispatch', 'execute_compare_ai_judge', 'execute_compare_diff', 'execute_compare_side_by_side',
]

OUTPUT_ROOT = Path(__file__).parent.parent / "output"
IMAGE_OUT = OUTPUT_ROOT / "images"
IMAGE_OUT.mkdir(parents=True, exist_ok=True)

# ============================================================
#  通用辅助
# ============================================================

def _check_pillow() -> str | None:
    try:
        from PIL import Image  # noqa: F401
        return None
    except ImportError:
        return "Pillow 不可用，请安装: pip install Pillow"

def _check_images(paths: list[str]) -> str | None:
    if not paths or len(paths) < 2:
        return "至少需要 2 张图进行对比"
    if len(paths) > 4:
        return "最多支持 4 张图对比"
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        return f"图片不存在: {missing}"
    return None

def _safe_output_path(prefix: str, ext: str = ".png") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    i = 0
    while True:
        suffix = f"_{i}" if i else ""
        p = IMAGE_OUT / f"{prefix}_{ts}{suffix}{ext}"
        if not p.exists():
            return str(p)
        i += 1

def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / 1024 / 1024:.2f}MB"

def _parse_paths(image_paths) -> list[str]:
    """接受 JSON 数组字符串或 list"""
    if isinstance(image_paths, str):
        try:
            paths = json.loads(image_paths)
        except json.JSONDecodeError:
            # 兼容空格/逗号分隔
            paths = [p.strip() for p in image_paths.replace(",", " ").split() if p.strip()]
    else:
        paths = list(image_paths)
    return [str(p) for p in paths]

# ============================================================
#  模式1: side_by_side — 并排对比图（统一高度 + 标签）
# ============================================================

def _make_side_by_side(paths: list[str], labels: list[str] | None = None,
                       winner_index: int | None = None,
                       gap: int = 16, label_h: int = 36) -> str:
    """生成并排对比图。winner_index (0-based) 指定时给胜者加金色描边。

    统一到最小高度避免任何一张被拉伸/压缩。
    """
    from PIL import Image, ImageDraw, ImageFont

    imgs = [Image.open(p).convert("RGB") for p in paths]
    n = len(imgs)
    # 统一到最小高度
    min_h = min(im.size[1] for im in imgs)
    imgs = [im.resize((int(im.size[0] * min_h / im.size[1]), min_h), Image.Resampling.LANCZOS)
            for im in imgs]

    total_w = sum(im.size[0] for im in imgs) + gap * (n - 1)
    total_h = min_h + label_h  # 顶部留标签条

    # 深色画布（与 gallery / batch_grid 一致）
    canvas = Image.new("RGB", (total_w, total_h), (24, 24, 28))
    draw = ImageDraw.Draw(canvas)

    # 字体（中文优先）
    font = None
    for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc", "arial.ttf"):
        try:
            font = ImageFont.truetype(name, max(14, label_h // 2))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    if labels is None:
        labels = [chr(ord("A") + i) for i in range(n)]  # A / B / C / D

    x = 0
    for i, im in enumerate(imgs):
        canvas.paste(im, (x, label_h))
        # 标签
        is_winner = winner_index is not None and i == winner_index
        prefix = "★ " if is_winner else ""
        text = f"{prefix}{labels[i]}"
        color = (255, 200, 60) if is_winner else (200, 200, 200)
        # 文本居中
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
        except (AttributeError, ValueError):
            tw = len(text) * 8
        tx = x + (im.size[0] - tw) // 2
        draw.text((tx, 8), text, fill=color, font=font)

        # winner 描边
        if is_winner:
            draw.rectangle([x, label_h, x + im.size[0] - 1, total_h - 1],
                           outline=(255, 200, 60), width=4)
        x += im.size[0] + gap

    out = _safe_output_path("compare_sbs", ".png")
    canvas.save(out, "PNG")
    return out

def execute_compare_side_by_side(image_paths, labels: str = "",
                                  winner_index: int = -1,
                                  project_name: str = "") -> str:
    """并排对比图：把 2~4 张图拼到一张图里（统一高度 + 标签）。

    winner_index (0-based) 为有效索引时给对应图加金色描边和星标。
    """
    err = _check_pillow()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)
    paths = _parse_paths(image_paths)
    err = _check_images(paths)
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    label_list = None
    if labels:
        label_list = [s.strip() for s in labels.split("|") if s.strip()]
        if len(label_list) != len(paths):
            label_list = None  # 数量不匹配就退化为默认 A/B/C/D

    w = winner_index if (isinstance(winner_index, int) and 0 <= winner_index < len(paths)) else None

    try:
        out = _make_side_by_side(paths, labels=label_list, winner_index=w)
        size = Path(out).stat().st_size
        return json.dumps({
            "success": True, "output_path": out, "mode": "side_by_side",
            "image_count": len(paths),
            "winner_index": w if w is not None else -1,
            "file_size": _fmt_size(size),
            "message": f"并排对比图已生成 ({len(paths)} 张)",
        }, ensure_ascii=False)
    except (OSError, ValueError, TypeError) as e:
        return json.dumps({"error": f"生成失败: {e}", "success": False}, ensure_ascii=False)

# ============================================================
#  模式2: diff_heatmap — 像素级差异热力图
# ============================================================

def _make_diff(paths: list[str], amplify: int = 3,
               threshold: int = 0) -> tuple[str, float, tuple[int, int]]:
    """生成像素差异热力图（前两张图对比）。

    算法：
      1. 两图 resize 到同一尺寸（取最小）
      2. RGB 三通道分别求绝对差分
      3. 取三通道最大值（或可选阈值二值化）
      4. 差分 × amplify 放大微弱差异，clip 到 255
      5. 伪彩映射：0→蓝，中→红，255→黄白，让"改了哪里"一眼可见
    """
    from PIL import Image, ImageChops, ImageOps

    a = Image.open(paths[0]).convert("RGB")
    b = Image.open(paths[1]).convert("RGB")
    # 统一尺寸（最小交集，避免单边缩放错位）
    w = min(a.size[0], b.size[0])
    h = min(a.size[1], b.size[1])
    a = a.resize((w, h), Image.Resampling.LANCZOS)
    b = b.resize((w, h), Image.Resampling.LANCZOS)

    # 绝对差分
    diff = ImageChops.difference(a, b)

    # 取三通道 max → 灰度强度
    gray = diff.convert("L")
    px = gray.load()
    assert px is not None  # Pillow PixelAccess always available after convert()
    # 放大 + 阈值
    amplify = max(1, min(amplify, 10))
    for y in range(h):
        for x in range(w):
            v = px[x, y]
            if threshold and v < threshold:  # noqa: SIM108 — 性能敏感像素循环
                v = 0
            else:
                v = min(255, v * amplify)
            px[x, y] = v

    # 伪彩：用内置 thermal colormap 近似（L → P colormap → RGB）
    # 简单可靠：先反转再套 'jet'-like 自建渐变
    palette_img = ImageOps.colorize(gray, black=(0, 0, 80),
                                    white=(255, 255, 100),
                                    mid=(220, 30, 30))

    out = _safe_output_path("compare_diff", ".png")
    palette_img.save(out, "PNG")

    # 统计差异比例（基于放大前的原始差分）
    raw_diff = ImageChops.difference(a, b).convert("L")
    raw_px = raw_diff.load()
    assert raw_px is not None  # Pillow PixelAccess always available after convert()
    diff_pixels = sum(1 for y in range(h) for x in range(w) if raw_px[x, y] > 8)
    diff_ratio = diff_pixels / (w * h)

    return out, diff_ratio, (w, h)

def execute_compare_diff(image_paths, amplify: int = 3,
                         threshold: int = 0,
                         project_name: str = "") -> str:
    """像素级差异热力图：对比两张图，高亮"哪里不一样"。

    用于：图生图前后对比、同一 prompt 不同 seed 差异检测、压缩失真可视化。
    """
    err = _check_pillow()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)
    paths = _parse_paths(image_paths)
    if len(paths) != 2:
        return json.dumps({"error": "diff 模式只能对比 2 张图", "success": False},
                          ensure_ascii=False)
    err = _check_images(paths)
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    try:
        out, ratio, (w, h) = _make_diff(paths, amplify=amplify, threshold=threshold)
        size = Path(out).stat().st_size
        return json.dumps({
            "success": True, "output_path": out, "mode": "diff_heatmap",
            "diff_ratio": round(ratio, 4),
            "diff_ratio_pct": f"{ratio * 100:.1f}%",
            "canvas_size": f"{w}x{h}",
            "amplify": amplify, "threshold": threshold,
            "file_size": _fmt_size(size),
            "message": f"差异热力图已生成，差异像素占比 {ratio * 100:.1f}%",
        }, ensure_ascii=False)
    except (OSError, ValueError, TypeError) as e:
        return json.dumps({"error": f"差异图生成失败: {e}", "success": False}, ensure_ascii=False)

# ============================================================
#  模式3: ai_judge — 多模态大模型裁判
# ============================================================

# 评委 rubric：与 memory.record_prompt_pair 的 5 分制对齐
_JUDGE_SYSTEM = """你是严格的图像评审专家。用户会给你 2~4 张图片（标记为 A/B/C/D）和一个评审目标。
请按 5 个维度对每张图独立打分（1-10 分整数，10 最优）：
  - prompt_match   提示词还原度
  - composition    构图/画面布局
  - lighting       光影/氛围
  - detail         细节清晰度/伪影
  - aesthetic      整体美感

只输出一个 JSON 对象，不要任何额外文字、不要 markdown 代码块。结构如下：
{
  "scores": {"A": {"prompt_match":9,"composition":8,"lighting":8,"detail":9,"aesthetic":9,"total":43},
             "B": {...}},
  "total_scores": {"A": 43, "B": 41},
  "winner": "A",
  "margin": 2,
  "reason": "一句话解释为什么 A 胜出（<=80字）",
  "per_dimension_winner": {"prompt_match":"A","composition":"A","lighting":"B","detail":"A","aesthetic":"A"}
}"""

JUDGE_VISION_MODEL = "agnes-1.5-flash"

def _build_judge_messages(paths: list[str], labels: list[str],
                          goal: str, prompts: list[str] | None) -> list[dict]:
    """构造多模态 messages：text(规则+目标+各图prompt) + N 张图"""
    from utils.image_input import load_image_as_url_or_data

    content: list[dict] = []
    intro = f"评审目标：{goal or '一般图像质量评估'}\n"
    if prompts:
        parts = []
        for lab, p in zip(labels, prompts, strict=False):
            parts.append(f"  图 {lab} 的提示词：{p[:200]}")
        intro += "各图提示词：\n" + "\n".join(parts) + "\n"
    intro += (f"\n下面按顺序给出 {len(paths)} 张图片，分别标记为 "
              f"{', '.join(labels)}。请严格按 rubric 打分并只返回 JSON。")
    content.append({"type": "text", "text": intro})

    for p in paths:
        url = load_image_as_url_or_data(p)
        content.append({"type": "image_url", "image_url": {"url": url}})

    return [{"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": content}]

def _parse_judge_response(raw: str) -> dict:
    """从大模型输出里抠出 JSON（容错：剥 markdown fence / 找首个 {）"""
    if not raw:
        raise ValueError("裁判返回为空")
    s = raw.strip()
    # 去 markdown code fence
    if s.startswith("```"):
        s = s.split("```", 2)
        s = s[1] if len(s) >= 2 else raw
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    # 截取最外层花括号
    lo = s.find("{")
    hi = s.rfind("}")
    if lo >= 0 and hi > lo:
        s = s[lo:hi + 1]
    return json.loads(s)

def execute_compare_ai_judge(image_paths, goal: str = "",
                             prompts: str = "",
                             labels: str = "",
                             vision_client=None,
                             vision_model: str = JUDGE_VISION_MODEL) -> str:
    """AI 裁判：让多模态大模型同时看 N 张图，按 rubric 打分并选出 winner。

    返回结构化 JSON（scores / winner / reason / per_dimension_winner），
    可直接喂给 memory.record_comparison 反哺进化系统。

    vision_client: AgnesClient 实例；为 None 时按 CLI 注入（由调用方传入）。
    """
    paths = _parse_paths(image_paths)
    err = _check_images(paths)
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    n = len(paths)
    if labels:
        label_list = [s.strip() for s in labels.split("|") if s.strip()]
        if len(label_list) != n:
            label_list = None
    else:
        label_list = None
    if label_list is None:
        label_list = [chr(ord("A") + i) for i in range(n)]

    prompt_list = None
    if prompts:
        prompt_list = [s.strip() for s in prompts.split("|")]
        if len(prompt_list) != n:
            prompt_list = None

    if vision_client is None:
        return json.dumps({
            "error": "ai_judge 需要传入 vision_client（AgnesClient 实例）",
            "success": False,
        }, ensure_ascii=False)

    try:
        messages = _build_judge_messages(paths, label_list, goal, prompt_list)
        r = vision_client.chat(
            model=vision_model, messages=messages,
            temperature=0.1, max_tokens=900,
        )
        raw = r["choices"][0]["message"]["content"] or ""
    except KeyError as e:
        return json.dumps({"error": f"裁判 API 返回格式异常: 缺字段 {e}",
                           "success": False}, ensure_ascii=False)
    except (httpx.HTTPError, OSError) as e:
        return json.dumps({"error": f"裁判调用失败: {e}",
                           "success": False}, ensure_ascii=False)

    try:
        verdict = _parse_judge_response(raw)
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        return json.dumps({
            "error": f"裁判输出解析失败: {e}",
            "success": False, "raw": raw[:500],
        }, ensure_ascii=False)

    # 把字母标签映射回实际图片路径，方便上层使用
    verdict["labels"] = label_list
    verdict["image_paths"] = paths
    verdict["goal"] = goal
    verdict["model"] = vision_model
    verdict["success"] = True
    verdict["mode"] = "ai_judge"
    return json.dumps(verdict, ensure_ascii=False)

# ============================================================
#  工具定义（OpenAI function 格式）
# ============================================================

COMPARE_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "compare_images",
            "description": (
                "图像对比 / A-B 测试。三种模式：(1) side_by_side 并排对比图（统一高度+标签+winner高亮）；"
                "(2) diff_heatmap 像素级差异热力图（定位改了哪里，用于图生图前后/压缩失真）；"
                "(3) ai_judge 多模态大模型裁判（同时看 2~4 张图，按 rubric 打分选 winner，返回结构化结果）。"
                "支持 2~4 张图。ai_judge 的结果会自动喂回进化学习系统。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "image_paths": {
                        "type": "string",
                        "description": 'JSON数组: ["A.png","B.png"]（2~4张）',
                    },
                    "mode": {
                        "type": "string",
                        "description": "side_by_side / diff_heatmap / ai_judge，默认 side_by_side",
                    },
                    "labels": {
                        "type": "string",
                        "description": '自定义标签用"|"分隔，如 "原图|修复后"，默认 A/B/C/D',
                    },
                    "goal": {
                        "type": "string",
                        "description": "ai_judge 模式的评审目标，如'哪个更符合提示词'/'哪个更清晰'",
                    },
                    "prompts": {
                        "type": "string",
                        "description": 'ai_judge 模式各图对应提示词，用"|"分隔，辅助裁判',
                    },
                    "winner_index": {
                        "type": "integer",
                        "description": "side_by_side 模式：0-based 高亮某张为 winner（-1=不高亮）",
                    },
                    "amplify": {
                        "type": "integer",
                        "description": "diff_heatmap 模式：差异放大倍数 1-10，默认 3",
                    },
                    "threshold": {
                        "type": "integer",
                        "description": "diff_heatmap 模式：低于此值的差异忽略（0=不阈值），默认 0",
                    },
                },
                "required": ["image_paths"],
            },
        },
    },
]

# ============================================================
#  执行器映射
# ============================================================

def compare_images_dispatch(vision_client=None,
                            vision_model: str = JUDGE_VISION_MODEL,
                            **kw) -> str:
    """统一入口：按 mode 路由到具体实现。

    Agent 调用走这里（vision_client 由 ChatSession 注入）。
    """
    mode = kw.get("mode", "side_by_side").lower()
    if mode in ("sbs", "side-by-side", "side_by_side"):
        mode = "side_by_side"
    elif mode in ("diff", "heatmap", "diff_heatmap"):
        mode = "diff_heatmap"
    elif mode in ("judge", "ai_judge", "ai-judge"):
        mode = "ai_judge"

    if mode == "side_by_side":
        return execute_compare_side_by_side(
            image_paths=kw.get("image_paths", "[]"),
            labels=kw.get("labels", ""),
            winner_index=kw.get("winner_index", -1),
        )
    if mode == "diff_heatmap":
        return execute_compare_diff(
            image_paths=kw.get("image_paths", "[]"),
            amplify=kw.get("amplify", 3),
            threshold=kw.get("threshold", 0),
        )
    # ai_judge
    return execute_compare_ai_judge(
        image_paths=kw.get("image_paths", "[]"),
        goal=kw.get("goal", ""),
        prompts=kw.get("prompts", ""),
        labels=kw.get("labels", ""),
        vision_client=vision_client,
        vision_model=vision_model,
    )

# 供 ToolRegistry 直接挂载（无 vision_client 时只支持 side_by_side / diff）
COMPARE_EXECUTOR_MAP = {
    "compare_images": lambda **kw: compare_images_dispatch(vision_client=None, **kw),
}
