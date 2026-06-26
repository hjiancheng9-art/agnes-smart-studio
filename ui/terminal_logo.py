"""CRUX Studio terminal logo — CRT 美学欢迎页 · 五兽归位。
像素级 GLYPHS 字形系统 + Rich 渲染。
编辑 GLYPHS 或 COLORS 后运行 make_logo_svg.py 保持终端与 SVG 同步。
"""

from __future__ import annotations

from typing import Any

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
BL = " "
GLYPHS = {
    "C": ["..####..", ".##..##.", "##....##", "##......", "##......", "##....##", ".##..##.", "..####.."],
    "R": ["######..", "##...##.", "##...##.", "######..", "##.##...", "##..##..", "##...##.", "##...##."],
    "U": ["##...##.", "##...##.", "##...##.", "##...##.", "##...##.", "##...##.", "##...##.", ".#####.."],
    "X": ["##...##.", ".##.##..", "..###...", "...##...", "..###...", ".##.##..", "##...##.", "##...##."],
}
ICON = [".+.#.+.", "#.@.@.#", "..@@@..", "#.@.@.#", ".+.#.+."]
PIXEL_KIND = {"#": "primary", "@": "accent", "+": "highlight", ".": None}
_LETTERS = "CRUX"
_LETTER_W = 8
_LETTER_H = 8
_GAP = 2
_LETTER_SPAN = _LETTER_W + _GAP
_WORD_W = len(_LETTERS) * _LETTER_W + (len(_LETTERS) - 1) * _GAP
_SHADOW_DX = 1
_SHADOW_DY = 1


def render_pixel_grid():
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
                grid[r][c] = {"color": kind, "shadow": False}
                main_pixels.append((r, c))
    for r, c in main_pixels:
        sr, sc = r + _SHADOW_DY, c + _SHADOW_DX
        if 0 <= sr < rows and 0 <= sc < cols and grid[sr][sc] is None:
            grid[sr][sc] = {"color": "muted", "shadow": True}
    return grid


# ── CRUX 大字字符画（每个字母由自身构成）──
_CRUX_ART = [
    ("   CCCCC     ", " RRRRRR      ", "  U     U    ", " X     X     "),
    ("  C     C    ", " R     R     ", "  U     U    ", "  X   X      "),
    (" C           ", " R     R     ", "  U     U    ", "   X X       "),
    (" C           ", " RRRRRR      ", "  U     U    ", "    X        "),
    (" C           ", " R   R       ", "  U     U    ", "   X X       "),
    ("  C     C    ", " R    R      ", "  U     U    ", "  X   X      "),
    ("   CCCCC     ", " R     R     ", "   UUUUU     ", " X     X     "),
]


def build_banner(v="v5.0", t=None, s=None, provider=None):
    from ui.theme import COLORS, ICONS, LAYOUT

    P = COLORS["primary"]
    A = COLORS["accent"]
    M = COLORS["muted"]
    H = COLORS["highlight"]
    _t = t if t is not None else "84"
    _s = s if s is not None else "734"
    sep = LAYOUT["separator_char"] * LAYOUT["separator_len"]
    lines = []
    lines.append("")
    for row in _CRUX_ART:
        c, r, u, x = row[0], row[1], row[2], row[3]
        lines.append(f"        [{P}]{c}[/][{A}]{r}[/][{H}]{u}[/][{P}]{x}[/]")
    lines.append("")
    lines.append(f"        [{M}]{sep}[/]")
    lines.append(f"        [{A}]{ICONS['success']}[/] [{H}]{v}[/]  [{M}]   {_t} tools     {_s} skills    [/]")
    lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  render_welcome() — CRT 美学 · 五兽归位
# ═══════════════════════════════════════════════════════════════
def render_welcome(v="v5.0", t=None, s=None):
    """五兽归位欢迎页 — 终端原生 CRT 美学版。
    布局：
      1. CRT 显示器顶框 — GLYPHS 标识 + 版本铭牌
      2. CRUX 大字 — 每字母自带色彩
      3. 五兽卡牌阵列 — 五行·五色·五引擎
      4. 内核仪表盘 — 模型/上下文/法宝/健康
      5. 命令速查 + 闪烁光标
    """
    from rich.table import Table
    from rich.text import Text

    from ui.theme import COLORS, console

    P = COLORS["primary"]
    COLORS["accent"]
    M = COLORS["muted"]
    S = COLORS["success"]
    COLORS["warning"]
    BAI = COLORS["baihu"]
    QIN = COLORS["qinglong"]
    ZHU = COLORS["zhuque"]
    XUA = COLORS["xuanwu"]
    QIL = COLORS["qilin"]
    _t = t if t is not None else "84"
    _s = s if s is not None else "734"
    # ── 1. 顶栏：CRT 显示器风格 ──
    console.print()
    top_bar = f"[{M}]╔══[/][{P}] ◆ GLYPHS · v5 ◆ [/][{M}]══════════════════════════════════════════╗[/]"
    console.print(f"  {top_bar}")
    console.print(
        f"  [{M}]║[/]  "
        f"[{BAI}]白[/][{QIN}]青[/][{ZHU}]朱[/][{XUA}]玄[/][{QIL}]麒[/] "
        f"[{M}]五兽归位 · AI-Native Creative Studio[/]"
        f"        [{M}]║[/]"
    )
    console.print(f"  [{M}]╚══════════════════════════════════════════════════════╝[/]")
    console.print()
    # ── 2. CRUX 大字 ──
    logo = build_banner(v, t, s)
    console.print(logo)
    # ── 3. 五兽卡牌阵列 ──
    console.print(f"    [{M}]┌────────────┬────────────┬────────────┬────────────┬────────────┐[/]")
    # 名称行
    console.print(
        f"    [{M}]│[/]"
        f"  [{BAI}]🐅 白虎[/]    [{M}]│[/]"
        f"  [{QIN}]🐉 青龙[/]    [{M}]│[/]"
        f"  [{ZHU}]🦅 朱雀[/]    [{M}]│[/]"
        f"  [{XUA}]🐢 玄武[/]    [{M}]│[/]"
        f"  [{QIL}]🦄 麒麟[/]    [{M}]│[/]"
    )
    # 元素行
    console.print(
        f"    [{M}]│[/]"
        f"  [{BAI}]金·刑·西[/]  [{M}]│[/]"
        f"  [{QIN}]木·生·东[/]  [{M}]│[/]"
        f"  [{ZHU}]火·明·南[/]  [{M}]│[/]"
        f"  [{XUA}]水·藏·北[/]  [{M}]│[/]"
        f"  [{QIL}]土·和·中[/]  [{M}]│[/]"
    )
    # 引擎行
    console.print(
        f"    [{M}]│[/]"
        f"  [{S}]● CRUX[/]   [{M}]│[/]"
        f"  [{S}]● Codex[/]  [{M}]│[/]"
        f"  [{S}]● Claude[/] [{M}]│[/]"
        f"  [{S}]● ZCode[/]  [{M}]│[/]"
        f"  [{S}]● Buddy[/]  [{M}]│[/]"
    )
    console.print(f"    [{M}]└────────────┴────────────┴────────────┴────────────┴────────────┘[/]")
    console.print()
    # ── 4. 内核仪表盘 ──
    dash = Table(show_header=False, box=None, padding=(0, 3), expand=False)
    dash.add_column(justify="center", width=24)
    dash.add_column(justify="center", width=22)
    dash.add_column(justify="center", width=24)
    dash.add_column(justify="center", width=16)
    dash.add_row(
        f"[dim {M}]◈ 内核引擎[/]\n[bold {P}]deepseek-v4-pro[/]",
        f"[dim {M}]◈ 上下文窗口[/]\n[bold #E0E0E0]1,000,000 tokens[/]",
        f"[dim {M}]◈ 法宝谱[/]\n[bold #E0E0E0]{_t} 工具 · {_s} 技能[/]",
        f"[dim {M}]◈ 系统状态[/]\n[bold {S}]● 全系统就绪[/]",
    )
    console.print(dash)
    console.print()
    # ── 5. 七层结界 健康条 ──
    shields = [
        (S, "沙箱"),
        (S, "熔断"),
        (S, "加密"),
        (S, "隐私"),
        (S, "快照"),
        (S, "校验"),
        (S, "自愈"),
    ]
    shield_bar = "  " + "  ".join(f"[{color}]●[/] [{M}]{name}[/]" for color, name in shields)
    console.print(f"  [{M}]七层结界:[/] {shield_bar}")
    console.print()
    # ── 6. 命令速查 ──
    cmd_line = (
        f"  [{M}]/"
        f"[{M}]model[/]  [{M}]/"
        f"[{M}]code[/]   [{M}]/"
        f"[{M}]img[/]    [{M}]/"
        f"[{M}]video[/]  [{M}]/"
        f"[{M}]skill[/]  [{M}]/"
        f"[{M}]plan[/]   [{M}]/"
        f"[{M}]team[/]   [{M}]/"
        f"[{M}]help[/]"
    )
    console.print(f"  [{M}]快捷命令[/]")
    console.print(cmd_line)
    console.print()
    # ── 7. 光标提示 ──
    cursor_line = Text()
    cursor_line.append("▮ ", style=f"bold {S}")
    cursor_line.append("键入指令开始", style=f"bold {P}")
    cursor_line.append(" · ", style=M)
    cursor_line.append("Alt+Enter 换行", style=M)
    cursor_line.append(" · ", style=M)
    cursor_line.append("直接粘贴图片路径", style=M)
    console.print(f"  {cursor_line}")
    console.print()


def render_mini_logo():
    from ui.theme import COLORS

    return f"[{COLORS['primary']}]C[/][{COLORS['accent']}]R[/][{COLORS['highlight']}]U[/][{COLORS['primary']}]X[/]"


def show(v=None, t=None, s=None, provider=None):
    from ui.theme import console

    console.print()
    console.print(build_banner(v or "v5.0", t=t, s=s, provider=provider))


def render_rich(v=None, t=None, s=None, provider=None):
    return build_banner(v or "v5.0", t=t, s=s, provider=provider)


if __name__ == "__main__":
    show()
