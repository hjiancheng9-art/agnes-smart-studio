"""CRUX Studio terminal logo — v5 现代简约设计。
七兽环绕 · 无大字 CRUX · 信息层次分明 · 专业开发者工具风格。

与 v4 的差异:
- 移除像素化 CRUX 大字，改用 ◆ Studio v5.0 极简标识
- 七兽从 emoji 堆叠改为网格卡片布局，更紧凑专业
- 欢迎页用 Rich Panel 做头部容器，信息一目了然
- build_banner 从居中横幅改为左对齐紧凑行

向后兼容:
- render_pixel_grid() / GLYPHS / ICON / PIXEL_KIND 保留，
  供 skin.py / make_logo_svg.py / 测试 使用（SVG/web 像素导出）。
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ui.theme import COLORS, console

__all__ = [
    "GLYPHS",
    "ICON",
    "PIXEL_KIND",
    "render_pixel_grid",
    "build_banner",
    "show",
    "render_rich",
    "render_welcome",
    "render_mini_logo",
]

# ═══════════════════════════════════════════════════════════════
#  像素网格（向后兼容 — skin.py / make_logo_svg.py / 测试）
#  仅用于 SVG/WEB 导出，终端欢迎页不再使用像素 CRUX。
# ═══════════════════════════════════════════════════════════════

BL = " "
GLYPHS = {
    "C": ["..####..", ".##..##.", "##....##", "##......", "##......", "##....##", ".##..##.", "..####.."],
    "R": ["######..", "##...##.", "##...##.", "######..", "##.##...", "##..##..", "##...##.", "##...##."],
    "U": ["##...##.", "##...##.", "##...##.", "##...##.", "##...##.", "##...##.", "##...##.", ".#####.."],
    "X": ["##...##.", ".##.##..", "..###...", "...##...", "..###...", ".##.##..", "##...##.", "##...##."],
}
ICON = [".+.#.+.", "#.@.@.#", "..@@@..", "#.@.@.#", ".+.#.+."]
PIXEL_KIND = {"#": "primary", "@": "accent", "+": "highlight", ".": None}

# 每字母颜色覆写：R 用 accent（青）与其它字母 primary（蓝）区分，
# 避免 R 像素密集时被误认为外框 → "CUX" 无法辨识。
_LETTER_COLOR_MAP = {
    "C": {"primary": "primary"},
    "R": {"primary": "accent"},   # R 用青色，跳脱边框感
    "U": {"primary": "primary"},
    "X": {"primary": "primary"},
}

_LETTERS = "CRUX"
_LETTER_W = 8
_LETTER_H = 8
_GAP = 2
_LETTER_SPAN = _LETTER_W + _GAP
_WORD_W = len(_LETTERS) * _LETTER_W + (len(_LETTERS) - 1) * _GAP
_SHADOW_DX = 1
_SHADOW_DY = 1


def render_pixel_grid():
    """像素网格 — 供 skin.py / make_logo_svg.py SVG 导出。

    终端欢迎页不再使用，保留仅为向后兼容。
    """
    rows = _LETTER_H + _SHADOW_DY
    cols = _WORD_W + _SHADOW_DX
    grid: list[list[Any]] = [[None] * cols for _ in range(rows)]
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
                # 字母级颜色覆写（R 用 accent 跳出边框感）
                color = _LETTER_COLOR_MAP.get(ch, {}).get(kind, kind)
                grid[r][c] = {"color": color, "shadow": False}
                main_pixels.append((r, c))
    for r, c in main_pixels:
        sr, sc = r + _SHADOW_DY, c + _SHADOW_DX
        if 0 <= sr < rows and 0 <= sc < cols and grid[sr][sc] is None:
            grid[sr][sc] = {"color": "muted", "shadow": True}
    return grid


def build_banner(v="v5.0", t=None, s=None, provider=None):
    """现代横幅 — 左对齐紧凑单行，无 CRUX 大字。

    用于对话中的 logo 引用、skin 层的 terminal banner 等。
    """
    P = COLORS["primary"]
    A = COLORS["accent"]
    M = COLORS["muted"]
    S = COLORS["success"]
    _t = t if t is not None else "84"
    _s = s if s is not None else "734"

    return Text.from_markup(
        f" [bold {P}]◆ Studio {v}[/]"
        f"  [{M}]{_t} tools[/]"
        f"  [{M}]· {_s} skills[/]"
        f"  [{S}]●[/]"
    )


def render_welcome(v="v5.0", t=None, s=None):
    """v5 欢迎页 — 现代简约 · 七兽环绕 · 无大字 CRUX。

    布局:
      头部面板 (Studio + 模型/状态)
      内核信息行
      七兽卡片网格 (上4下3)
      命令速查
      光标提示
    """
    P = COLORS["primary"]
    A = COLORS["accent"]
    M = COLORS["muted"]
    S = COLORS["success"]
    H = COLORS["highlight"]
    BAI = COLORS["baihu"]
    QIN = COLORS["qinglong"]
    ZHU = COLORS["zhuque"]
    XUA = COLORS["xuanwu"]
    QIL = COLORS["qilin"]
    TEN = COLORS["tengshe"]
    YIN = COLORS["yinglong"]
    _t = t if t is not None else "84"
    _s = s if s is not None else "734"

    # ── 1. 头部面板 ──
    header = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    header.add_column(style="", ratio=1)
    header.add_column(style="", justify="right")
    header.add_row(
        f"[bold {P}]◆ Studio {v}[/]  [{M}]deepseek-v4-pro[/]",
        f"[{S}]● 就绪[/]  [{M}]{_t} tools · {_s} skills · 1M context[/]",
    )

    console.print()
    console.print(Panel(header, border_style=P, padding=(0, 1)))
    console.print()

    # ── 2. 七兽阵列 ──
    _render_beasts_grid()
    console.print()

    # ── 3. 命令速查 ──
    cmds = [
        ("/model", "模型"), ("/code", "编码"), ("/img", "生图"),
        ("/video", "视频"), ("/skill", "技能"), ("/plan", "规划"),
        ("/help", "帮助"),
    ]
    cmd_parts = []
    for name, desc in cmds:
        cmd_parts.append(f"[bold {P}]{name}[/] [{M}]{desc}[/]")
    console.print(f"  {'  '.join(cmd_parts)}")
    console.print()

    # ── 4. 光标提示 ──
    cursor = Text()
    cursor.append("> ", style=f"bold {S}")
    cursor.append("输入指令开始", style=f"bold {P}")
    cursor.append(" · ", style=M)
    cursor.append("Alt+Enter 换行", style=M)
    cursor.append(" · ", style=M)
    cursor.append("粘贴图片即识别", style=M)
    console.print(f"  {cursor}")
    console.print()


def _render_beasts_grid():
    """七兽卡片网格 — 上排4 + 下排3。"""
    M = COLORS["muted"]

    beasts = [
        ("白虎", COLORS["baihu"],    "自愈·锻造", "金·西"),
        ("青龙", COLORS["qinglong"],  "并行·开拓", "木·东"),
        ("朱雀", COLORS["zhuque"],    "验证·洞察", "火·南"),
        ("玄武", COLORS["xuanwu"],    "守卫·容灾", "水·北"),
        ("麒麟", COLORS["qilin"],     "创造·万类", "土·中"),
        ("螣蛇", COLORS["tengshe"],   "记忆·沉淀", "忆·传承"),
        ("应龙", COLORS["yinglong"],  "规划·调度", "令·协同"),
    ]

    console.print(f"  [{M}]── 七兽归位 · 魂盏交汇 ──────────────────────────────────[/]")
    console.print()

    # 上排4
    row1 = beasts[:4]
    _print_beast_cards(row1)
    console.print()
    # 下排3（居中偏左）
    row2 = beasts[4:]
    _print_beast_cards(row2, indent=8)


def _print_beast_cards(beasts: list, indent: int = 4):
    """打印一行兽卡 — 无边框，简洁紧凑。

    每张卡:
      兽名·元素
      职责

    卡片间用足够的空格分隔。
    """
    M = COLORS["muted"]
    prefix = " " * indent

    # Line 1: 兽名 + 元素方向
    names = []
    for name, color, _role, elem in beasts:
        names.append(f"[bold {color}]{name}[/] [{M}]{elem}[/]")
    console.print(f"{prefix}{'    '.join(names)}")

    # Line 2: 职责描述
    roles = []
    for name, color, role, _elem in beasts:
        roles.append(f"[{color}]{role}[/]")
    console.print(f"{prefix}{'    '.join(roles)}")


def render_mini_logo():
    """微型标识 — 用于对话内嵌引用。"""
    return f"[bold {COLORS['primary']}]◆[/]"


def show(v=None, t=None, s=None, provider=None):
    """打印横幅（用于 --menu 等场景）。"""
    console.print()
    console.print(build_banner(v or "v5.0", t=t, s=s, provider=provider))


def render_rich(v=None, t=None, s=None, provider=None):
    """返回 Rich Text 横幅（供 skin/crux_studio.py 引用）。"""
    return build_banner(v or "v5.0", t=t, s=s, provider=provider)


if __name__ == "__main__":
    render_welcome()
