"""
CRUX Terminal Splash — Pixel Art Welcome Screen (v2)
=====================================================
升级版终端美学 + 像素艺术 CLI 欢迎界面。
CRT 像素矩阵 + 双线框装饰 + 扫描线效果。
"""

from __future__ import annotations

import shutil

# ══════════════════════════════════════════════════════════════════
#  像素艺术 CRUX — 11 层高 · 宽 65
#  每个字母 12 格宽 × 11 格高，四字母 + 间距 = 65 字符
#  用 █ ▓ ▒ ░ 四级灰度模拟 CRT 像素抗锯齿
# ══════════════════════════════════════════════════════════════════
CRUX_PIXEL = [
    #        CCCC            RRRR             U   U            X   X
    "  ░░████████░░    ░░████████░░    ░░██░░░░██░░    ░░██░░░░██░░  ",
    "  ████████████    ████████████    ████████████    ████████████  ",
    " ████░░░░░░████  ████░░░░████    ████░░░░████    ████░░░░████  ",
    " ████░░░░░░████  ██████████      ████░░░░████    ██░░████░░██  ",
    " ████░░░░░░████  ██████████      ████████████    ██░░░░░░░░██  ",
    " ████░░░░░░████  ████░░████      ████████████    ██░░░░░░░░██  ",
    " ████░░░░░░████  ████░░░████     ████░░░░████    ██░░████░░██  ",
    " ████░░░░░░████  ████░░░░████    ████░░░░████    ██░░░░░░░░██  ",
    "  ████████████    ████████████    ████░░░░████    ██░░░░░░░░██  ",
    "  ░░████████░░    ░░████████░░    ░░██░░░░██░░    ░░██░░░░██░░  ",
    "                                ",
]

# ══════════════════════════════════════════════════════════════════
#  调色板 — CRT 终端风格 v2
# ══════════════════════════════════════════════════════════════════
PALETTE = {
    "logo":        "#ffb347",  # 暖金
    "logo_dim":    "#c08030",  # 金暗
    "bg":          "#0a0a1a",  # 深空底色
    "border":      "#5a5a8a",  # 边框紫灰（提亮）
    "border_dim":  "#3a3a5a",  # 边框暗色
    "accent":      "#00d4aa",  # 青绿 accent
    "accent_dim":  "#008866",  # 青绿暗
    "status_on":   "#00ff88",  # 在线绿
    "status_off":  "#555555",  # 离线灰
    "text":        "#c8c8d8",  # 浅灰文字
    "dim":         "#606080",  # 暗文字
    "highlight":   "#ff6b6b",  # 珊瑚高亮
    "pink":        "#d4708a",  # 粉
    "blue":        "#6b9eff",  # 蓝
    "purple":      "#a070d8",  # 紫
}

# ══════════════════════════════════════════════════════════════════
#  排版常量
# ══════════════════════════════════════════════════════════════════
LOGO_W = max(len(row) for row in CRUX_PIXEL)
LOGO_H = len(CRUX_PIXEL)
_P = PALETTE  # shorthand


# ══════════════════════════════════════════════════════════════════
#  辅助：模式状态行
# ══════════════════════════════════════════════════════════════════
def _mode_tag(label: str, color_key: str, detail: str = "") -> str:
    """单行模式标签，带 icon 和颜色."""
    c = _P.get(color_key, _P["text"])
    icon_map = {
        "tool": "⚙", "mode": "◈", "provider": "▣",
        "model": "◇", "splash": "◆", "agent": "♢", "vision": "◎",
    }
    icon = icon_map.get(label, "◆")
    return f"  [{c}]{icon} {detail or label}[/]"


# ══════════════════════════════════════════════════════════════════
#  渲染引擎
# ══════════════════════════════════════════════════════════════════

def build_logo_lines() -> list[str]:
    """Build pixel-art CRUX logo with Rich markup → list of markup lines."""
    lines_out = []
    for row in CRUX_PIXEL:
        parts = []
        for ch in row:
            if ch == "█":
                parts.append(f"[{_P['logo']}]█[/]")
            elif ch == "▓":
                parts.append(f"[{_P['logo']}]▓[/]")
            elif ch == "▒":
                parts.append(f"[{_P['logo_dim']}]▒[/]")
            elif ch == "░":
                parts.append(f"[{_P['logo_dim']}]░[/]")
            else:
                parts.append(f"[{_P['bg']}]{ch}[/]")
        lines_out.append("".join(parts))
    return lines_out


def build_border_line(char: str = "═", top: bool = True) -> str:
    """Build a full-width box-drawing border line."""
    bdr = _P["border"]
    bdr_d = _P["border_dim"]
    if top:
        inner = f"╔{'═' * (LOGO_W - 2)}╗"
        return f"  [{bdr}]{inner}[/]"
    else:
        inner = f"╚{'═' * (LOGO_W - 2)}╝"
        return f"  [{bdr}]{inner}[/]"


def build_scanline() -> str:
    """扫描线分隔."""
    inner = f"║{'─' * (LOGO_W - 2)}║"
    return f"  [{_P['border_dim']}]{inner}[/]"


# ══════════════════════════════════════════════════════════════════
#  打印入口
# ══════════════════════════════════════════════════════════════════

def _make_status_lamp(label: str, on: bool) -> str:
    dot = "●" if on else "○"
    c = _P["status_on"] if on else _P["status_off"]
    return f"  [{c}]{dot}[/] [{_P['dim']}]{label}[/]"


def _build_info_panel(console) -> Text:
    """Build right-side info panel: git status, quick tips, session stats."""
    from rich.style import Style
    from rich.text import Text

    bdr_d = _P["border_dim"]
    dim = _P["dim"]
    accent = _P["accent"]
    text_c = _P["text"]

    lines = []

    # ── Git 分支 ──
    try:
        import subprocess
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=2
        ).stdout.strip()
        if branch:
            lines.append(("  ◈ branch", Style(color=accent, bold=True)))
            lines.append((f"  {branch}", Style(color=_P["green"])))
        else:
            lines.append(("  ◈ (detached)", Style(color=dim)))
    except Exception:
        pass

    lines.append(("", Style()))

    # ── 最近提交 ──
    try:
        import subprocess
        last_commit = subprocess.run(
            ["git", "log", "-1", "--format=%s", "--no-color"],
            capture_output=True, text=True, timeout=2
        ).stdout.strip()
        if last_commit:
            lines.append(("  ◆ last commit", Style(color=accent, bold=True)))
            msg = last_commit[:45] + "…" if len(last_commit) > 45 else last_commit
            lines.append((f"  {msg}", Style(color=dim, italic=True)))
    except Exception:
        pass

    lines.append(("", Style()))

    # ── 快速指南 ──
    lines.append(("  ⚡ quick start", Style(color=accent, bold=True)))
    tips = [
        ("  /help", "  show all commands"),
        ("  @model", "  switch AI model"),
        ("  /image", "  generate image"),
        ("  /video", "  generate video"),
        ("  Ctrl+C", "  new session"),
    ]
    for cmd, desc in tips:
        lines.append((
            f"  {cmd}",
            Style(color=_P["cyan"]),
        ))
        lines.append((
            f"{desc}",
            Style(color=dim, italic=True),
        ))

    lines.append(("", Style()))

    # ── 边栏分隔线 ──
    lines.append(("  ───────", Style(color=bdr_d)))

    info = Text.assemble(*lines)
    return info


def print_splash(extra_lines: list[tuple] | None = None) -> None:
    """Print full splash screen: logo + info panel side by side."""
    from rich.console import Console
    from rich.style import Style
    from rich.text import Text
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.panel import Panel

    console = Console(color_system="truecolor")
    tw = console.width or shutil.get_terminal_size().columns

    # ── Logo 区域 ──
    logo_lines = build_logo_lines()
    # 增加上下各一行呼吸空间
    logo_text = Text.from_markup("\n" + "\n".join(logo_lines) + "\n")

    # ── 边框 ──
    bdr = _P["border"]
    bdr_d = _P["border_dim"]

    border_top = Text(
        f"  ╔{'═' * (LOGO_W - 2)}╗",
        style=Style(color=bdr),
    )

    # 框内上边
    border_inner_top = Text(
        f"  ║{' ' * (LOGO_W - 2)}║",
        style=Style(color=bdr_d),
    )

    border_bot = Text(
        f"  ╚{'═' * (LOGO_W - 2)}╝",
        style=Style(color=bdr),
    )

    scanline = Text(
        f"  ║{'─' * (LOGO_W - 2)}║",
        style=Style(color=bdr_d),
    )

    # ── 版本 / 标语 ──
    from core.version import __version__
    version_tag = f"  v{__version__}  "
    tag_line = Text.assemble(
        ("  ═══  ", Style(color=bdr_d)),
        (f" {version_tag} ", Style(color=_P["accent"], bold=True)),
        ("  ═══  ", Style(color=bdr_d)),
        ("\n", Style()),
        ("      ⚡ AI · Code · Create  ⚡", Style(color=_P["dim"], italic=True)),
    )

    # ── 状态行 ──
    status_items = []

    if extra_lines:
        for kind, label, color_key, detail in extra_lines:
            icon_map = {
                "tool": "⚙", "mode": "◈", "provider": "▣",
                "model": "◇", "splash": "◆",
            }
            icon = icon_map.get(kind, "◆")
            c = _P.get(color_key, _P["text"])
            status_items.append(
                Text.assemble(
                    (f" {icon} ", Style(color=c)),
                    (f"{detail or label}", Style(color=_P["text"], italic=True)),
                )
            )

    # ── 左面板 ──
    from rich.console import Group as RenderGroup
    left_body = [border_top, border_inner_top, logo_text, scanline, tag_line, scanline]
    if status_items:
        left_body.append(Text("\n", Style()))
        cols = Columns(status_items, padding=(0, 2), equal=True, expand=False)
        left_body.append(cols)
    left_body.append(Text("\n"))
    left_body.append(border_bot)
    left_content = RenderGroup(*left_body)

    # ── 右面板: 系统信息 ──
    right_content = _build_info_panel(console)
    right_panel = Panel(
        right_content,
        border_style=Style(color=_P["border_dim"]),
        padding=(1, 2),
        title="[bold]info",
        title_align="left",
    )

    # ── 两列布局 ──
    if tw >= 110:
        layout = Layout()
        layout.split_row(
            Layout(left_content, ratio=2),
            Layout(right_panel, ratio=3),
        )
        console.print(layout)
    else:
        # 窄屏回退: 单列
        console.print(left_content)
        console.print(right_panel)

    console.print("", highlight=False)
