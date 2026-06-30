"""CRUX Studio terminal logo — v6 暗夜工坊 · 七兽色带紧凑版。

3 行欢迎屏：七兽色带 → 版本/模型 → 快捷命令。
保留所有公开 API 不变 (build_banner, render_welcome, render_rich, render_pixel_grid)。

设计原则:
- 七兽从卡片网格改为单行色带（功能色区分，非装饰）
- 去掉大型 ASCII art，改为纯色带 + 文字
- 信息密度优先，启动即展示关键数据
"""

from typing import Optional

from rich.text import Text

from ui.theme import COLORS, BEAST_PALETTE, GLYPHS as THEME_GLYPHS

# ── 公开 API ──────────────────────────────────────────────
__all__ = [
    "build_banner", "render_welcome", "render_rich",
    "render_pixel_grid", "render_mini_logo", "show",
    "ICON", "PIXEL_KIND", "GLYPHS",
    "_GAP", "_LETTER_W", "_LETTER_H",
]

# ── 保留兼容常量 (用于 make_logo_svg.py / test_logo_svg.py) ──
ICON = [".+.#.+.", "#.@.@.#", "..@@@..", "#.@.@.#", ".+.#.+."]
PIXEL_KIND = {"#": "primary", "@": "accent", "+": "highlight", ".": None}
GLYPHS = THEME_GLYPHS.copy()
# ── 兼容旧版字母像素图（test_terminal_logo.py 依赖）───────
_LETTER_GLYPHS = {
    "C": ["..####..", ".##..##.", "##....##", "##......", "##......", "##....##", ".##..##.", "..####.."],
    "R": ["######..", "##...##.", "##...##.", "######..", "##.##...", "##..##..", "##...##.", "##...##."],
    "U": ["##...##.", "##...##.", "##...##.", "##...##.", "##...##.", "##...##.", "##...##.", ".#####.."],
    "X": ["##...##.", ".##.##..", "..###...", "...##...", "..###...", ".##.##..", "##...##.", "##...##."],
}
GLYPHS.update(_LETTER_GLYPHS)
_GAP = 2
_LETTER_W = 8
_LETTER_H = 8


_LETTER_COLOR_MAP = {
    "C": {"primary": "primary"},
    "R": {"primary": "accent"},
    "U": {"primary": "primary"},
    "X": {"primary": "primary"},
}
_LETTERS = "CRUX"
_LETTER_SPAN = _LETTER_W + _GAP
_WORD_W = len(_LETTERS) * _LETTER_W + (len(_LETTERS) - 1) * _GAP
_SHADOW_DX = 1
_SHADOW_DY = 1

# ── render_pixel_grid (保留，供 SVG 生成使用) ────────────────
def render_pixel_grid() -> list[list]:
    """像素网格 — 供 skin.py / make_logo_svg.py SVG 导出。

    返回 cells 为 {"color": str, "shadow": bool} 字典，与旧版完全兼容。
    """
    rows = _LETTER_H + _SHADOW_DY
    cols = _WORD_W + _SHADOW_DX
    grid: list[list] = [[None] * cols for _ in range(rows)]
    main_pixels = []
    for r in range(_LETTER_H):
        for li, ch in enumerate(_LETTERS):
            glyph = GLYPHS.get(ch)
            if not glyph:
                continue
            row_str = glyph[r]
            base_col = li * _LETTER_SPAN
            for ci, px in enumerate(row_str):
                kind = PIXEL_KIND.get(px)
                if kind is None:
                    continue
                c = base_col + ci
                color = _LETTER_COLOR_MAP.get(ch, {}).get(kind, kind)
                grid[r][c] = {"color": color, "shadow": False}
                main_pixels.append((r, c))
    for r, c in main_pixels:
        sr, sc = r + _SHADOW_DY, c + _SHADOW_DX
        if 0 <= sr < rows and 0 <= sc < cols and grid[sr][sc] is None:
            grid[sr][sc] = {"color": "muted", "shadow": True}
    return grid


# ── 七兽色带 (核心视觉) ────────────────────────────────────
_BEASTS = [
    ("baihu",   "白虎",   "权威"),
    ("qinglong","青龙",   "检索"),
    ("zhuque",  "朱雀",   "创意"),
    ("xuanwu",  "玄武",   "守卫"),
    ("qilin",   "麒麟",   "创造"),
    ("tengshe", "螣蛇",   "记忆"),
    ("yinglong","应龙",   "调度"),
]


def _build_beasts_spectrum() -> Text:
    """单行七兽色带 — 极简紧凑。"""
    t = Text()
    for i, (key, name, _role) in enumerate(_BEASTS):
        color = BEAST_PALETTE[key]
        t.append(f" {name} ", style=f"bold {color}")
        if i < len(_BEASTS) - 1:
            t.append("·", style=COLORS["text_tertiary"])
    return t


# ── build_banner (保留旧签名) ───────────────────────────────
def build_banner(
    v: str = "v6.0",
    t: Optional[int] = None,
    s: Optional[int] = None,
    provider: Optional[str] = None,
) -> Text:
    """构建欢迎横幅 — 3 行紧凑版。"""
    # 行 0: 七兽色带
    out = Text()
    out.append(_build_beasts_spectrum())
    out.append("\n")

    # 行 1: 版本 + 模型
    provider_str = provider or "deepseek-v4-pro"
    out.append(f" {THEME_GLYPHS['logo']} CRUX Studio {v}  ·  {provider_str}  "
               f"·  {t or 78} 能力  ·  {s or 734} 技能",
               style=f"bold {COLORS['text']}")
    out.append("\n")

    # 行 2: 快捷命令
    out.append("    /chat 对话  ·  /skill 技能  ·  /tool 工具  ·  /help 帮助  ·  Ctrl+C 退出",
               style=COLORS["text_tertiary"])
    return out


# ── render_welcome (保留旧签名) ─────────────────────────────
def render_welcome(
    version: str = "v6.0",
    tools: Optional[int] = None,
    skills: Optional[int] = None,
    provider: Optional[str] = None,
    model: str = "deepseek-v4-pro",
    agent: Optional[str] = None,
    show_mini: bool = False,
) -> Text:
    """返回欢迎文本 — 3 行紧凑版 + 可选 mini logo。"""
    t_count = tools or _count_tools()
    s_count = skills or _count_skills()

    banner = build_banner(v=version, t=t_count, s=s_count, provider=provider or model)

    if show_mini:
        mini = render_mini_logo()
        return Text.assemble(mini, "\n", banner)
    return banner


# ── render_rich (保留旧签名) ────────────────────────────────
def render_rich(
    v: Optional[str] = None,
    t: Optional[int] = None,
    s: Optional[int] = None,
    provider: Optional[str] = None,
) -> Text:
    """Rich 渲染入口 — 等价于 build_banner + 自动统计。"""
    return render_welcome(
        version=v or "v6.0",
        tools=t,
        skills=s,
        provider=provider,
    )


# ── render_mini_logo ───────────────────────────────────────
def render_mini_logo() -> str:
    """单行迷你 logo。"""
    return f" {THEME_GLYPHS['logo']} CRUX"


# ── show (保留旧签名，cli.py 使用) ─────────────────────────
def show(
    v: Optional[str] = None,
    t: Optional[int] = None,
    s: Optional[int] = None,
    provider: Optional[str] = None,
) -> None:
    """直接 print 欢迎屏到终端。"""
    from rich.console import Console
    console = Console()
    text = render_welcome(version=v or "v6.0", tools=t, skills=s, provider=provider)
    console.print(text)


# ── 内部统计辅助 ───────────────────────────────────────────
def _count_tools() -> int:
    try:
        from core.tools import TOOLS_CONFIG
        import json
        if TOOLS_CONFIG.exists():
            data = json.loads(TOOLS_CONFIG.read_text(encoding="utf-8"))
            return len(data) if isinstance(data, dict) else 0
    except Exception:
        pass
    return 84


def _count_skills() -> int:
    try:
        from core.skills import SKILLS_CONFIG
        import json
        if SKILLS_CONFIG.exists():
            data = json.loads(SKILLS_CONFIG.read_text(encoding="utf-8"))
            return len(data) if isinstance(data, dict) else 0
    except Exception:
        pass
    return 734
