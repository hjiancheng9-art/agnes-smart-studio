"""CRUX Studio terminal logo — v6 暗夜工坊设计。
紧凑专业 · 七兽色光谱 · 信息密度优先 · 无冗余装饰。

设计原则:
- 单面板承载全部启动信息，不超过 8 行
- 七兽从卡片网格改为单行色带（功能色区分，非装饰）
- 命令用标签式呈现，留白充足
- 无像素字、无 emoji 堆砌

向后兼容:
- render_pixel_grid() / GLYPHS / ICON / PIXEL_KIND 保留，
  供 skin.py / make_logo_svg.py / 测试 使用（SVG/web 像素导出）。
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
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

_LETTER_COLOR_MAP = {
    "C": {"primary": "primary"},
    "R": {"primary": "accent"},
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


def render_pixel_grid() -> list[list[Any]]:
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
                color = _LETTER_COLOR_MAP.get(ch, {}).get(kind, kind)
                grid[r][c] = {"color": color, "shadow": False}
                main_pixels.append((r, c))
    for r, c in main_pixels:
        sr, sc = r + _SHADOW_DY, c + _SHADOW_DX
        if 0 <= sr < rows and 0 <= sc < cols and grid[sr][sc] is None:
            grid[sr][sc] = {"color": "muted", "shadow": True}
    return grid


# ═══════════════════════════════════════════════════════════════
#  v6 欢迎页 — 暗夜工坊
# ═══════════════════════════════════════════════════════════════


def build_banner(v: str = "v6.0", t=None, s=None, provider=None) -> Text:
    """紧凑单行横幅 — 用于对话头部 / skin 层引用。

    格式: ◆ Studio v6.0 · 84 tools · 734 skills · ●
    """
    P = COLORS["primary"]
    M = COLORS["muted"]
    G = COLORS["success"]
    _t = t if t is not None else "84"
    _s = s if s is not None else "734"

    return Text.from_markup(
        f"[bold {P}]◆[/] Studio {v}"
        f"  [{M}]· {_t} tools[/]"
        f"  [{M}]· {_s} skills[/]"
        f"  [{G}]●[/]"
    )


def render_welcome(
    v: str = "v6.0",
    t: str | None = None,
    s: str | None = None,
    model: str = "deepseek-v4-pro",
) -> None:
    """v6 欢迎页 — 暗夜工坊 · 单面板 · 紧凑专业。

    布局 (7 行含边框):
      ┌─ 头部: Studio + 模型 + 状态 ──────────────────────────┐
      │  七兽色带 (单行)                                        │
      │  统计行                                                  │
      │  命令标签                                                │
      │  提示行                                                  │
      └─────────────────────────────────────────────────────────┘
    """
    P = COLORS["primary"]
    M = COLORS["text_secondary"]
    T = COLORS["text_tertiary"]
    G = COLORS["success"]
    border = COLORS["border_focus"]

    # ── 动态统计 ──
    _t = str(_count_tools()) if t is None else t
    _s = str(_count_skills()) if s is None else s
    _c = str(_count_commands())

    # ── 组装面板内容 ──
    body = Text()
    # 行1: 头部信息
    body.append(f"◆ Studio {v}", style=f"bold {P}")
    body.append(f"    {model}", style=M)
    # 动态上下文
    ctx = _get_model_context(model)
    body.append(f"    {ctx}", style=M)
    body.append(f"    ● online", style=G)
    body.append("\n\n")
    # 行2: 七兽色带
    body.append(_build_beasts_spectrum())
    body.append("\n\n")
    # 行3: 统计
    body.append(f"{_t} tools  ·  {_s} skills  ·  {_c} commands  ·  7 beasts", style=T)
    body.append("\n\n")
    # 行4: 命令
    body.append(_build_cmd_tags())
    body.append("\n\n")
    # 行5: 提示
    body.append("› 输入指令开始", style=f"bold {P}")
    body.append("    ")
    body.append("粘贴图片即识别  ·  /help 查看命令  ·  Ctrl+C 退出", style=T)

    console.print()
    console.print(Panel(body, border_style=border, padding=(1, 2)))
    console.print()


def _count_tools() -> int:
    """动态获取工具数量。"""
    try:
        from core.tools import TOOLS_CONFIG
        import json
        if TOOLS_CONFIG.exists():
            data = json.loads(TOOLS_CONFIG.read_text(encoding="utf-8"))
            return len(data.get("tools", []))
    except Exception:
        pass
    return 0


def _count_skills() -> int:
    """动态获取技能数量。"""
    try:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        skills_dir = root / "skills"
        if skills_dir.is_dir():
            return len(list(skills_dir.glob("*.skill.json")))
    except Exception:
        pass
    return 0


def _count_commands() -> int:
    """动态获取命令数量。"""
    try:
        from core.commands import COMMANDS
        return len(COMMANDS)
    except Exception:
        return 0


def _get_model_context(model: str) -> str:
    """获取模型上下文窗口大小。"""
    try:
        from core.provider import get_model_info
        info = get_model_info(model)
        if info:
            ctx = getattr(info, "context_window", 0) or 0
            if ctx >= 1_000_000:
                return "1M context"
            elif ctx >= 128_000:
                return f"{ctx // 1000}K context"
    except Exception:
        pass
    return "1M context"


def _build_beasts_spectrum() -> Text:
    """七兽色带 — 单行紧凑，每个兽名用自身颜色渲染 + 职责标注。"""
    S = COLORS["text_tertiary"]

    beasts = [
        (COLORS["baihu"], "白虎", "自愈"),
        (COLORS["qinglong"], "青龙", "并行"),
        (COLORS["zhuque"], "朱雀", "洞察"),
        (COLORS["xuanwu"], "玄武", "守卫"),
        (COLORS["qilin"], "麒麟", "创造"),
        (COLORS["tengshe"], "螣蛇", "记忆"),
        (COLORS["yinglong"], "应龙", "调度"),
    ]
    result = Text()
    for i, (color, name, role) in enumerate(beasts):
        result.append(name, style=f"bold {color}")
        result.append(f"·{role}", style=S)
        if i < len(beasts) - 1:
            result.append("  ", style=S)
    return result


def _build_cmd_tags() -> Text:
    """命令标签行 — 斜杠命令用主色加亮。"""
    P = COLORS["primary"]
    T = COLORS["text_tertiary"]
    cmds = ["/chat", "/img", "/video", "/code", "/skill", "/plan", "/model", "/help"]

    result = Text()
    result.append("命令  ", style=T)
    for i, c in enumerate(cmds):
        result.append(c, style=f"bold {P}")
        if i < len(cmds) - 1:
            result.append("  ", style=T)
    return result


def render_mini_logo() -> str:
    """微型标识 — 用于对话内嵌引用。"""
    return f"[bold {COLORS['primary']}]◆[/]"


def show(v=None, t=None, s=None, provider=None) -> None:
    """打印横幅（用于 --menu 等场景）。"""
    console.print()
    console.print(build_banner(v or "v6.0", t=t, s=s, provider=provider))


def render_rich(v=None, t=None, s=None, provider=None) -> Text:
    """返回 Rich Text 横幅（供 skin/crux_studio.py 引用）。"""
    return build_banner(v or "v6.0", t=t, s=s, provider=provider)


if __name__ == "__main__":
    render_welcome()
