"""Beautify — CRUX 全局美化引擎。

串联所有视觉层: Logo·Badge·面板·分隔线·输入框·启动页·状态条·进度条。
模块接入即可全局生效，不更改业务逻辑。

用法: from ui.beautify import apply_all; apply_all()
"""

from __future__ import annotations

import sys
import time

from rich.panel import Panel

from ui.theme import COLORS, DIVIDER_STYLE, ICONS, INPUT_STYLE, LAYOUT, PANEL_STYLE, console

__all__ = [
    "hr",
    "hr_heavy",
    "hr_dot",
    "section_header",
    "info_panel",
    "success_panel",
    "error_panel",
    "warn_panel",
    "beast_panel",
    "input_prompt_line",
    "styled_input",
    "progress_line",
    "spinner",
    "splash_full",
    "apply_all",
]


# ═══════════════════════════════════════════════════════════════
# 分隔线
# ═══════════════════════════════════════════════════════════════


def hr(char: str | None = None, length: int | None = None, color: str | None = None):
    """标准分隔线。"""
    c = char or DIVIDER_STYLE["char"]
    ln = length or DIVIDER_STYLE["length"]
    cl = color or DIVIDER_STYLE["color"]
    console.print(c * ln, style=cl)


def hr_heavy(label: str = ""):
    """粗重分隔线，可选中间标签。"""
    c = DIVIDER_STYLE["heavy_char"]
    ln = DIVIDER_STYLE["length"]
    if label:
        half = (ln - len(label) - 2) // 2
        console.print(f"[{DIVIDER_STYLE['color']}]{c * half} [{COLORS['accent']}]{label}[/] {c * half}[/]")
    else:
        console.print(c * ln, style=DIVIDER_STYLE["color"])


def hr_dot():
    """带菱形装饰的分隔线。"""
    c = DIVIDER_STYLE["char"]
    d = DIVIDER_STYLE["dot"]
    ln = DIVIDER_STYLE["length"] // 2
    console.print(f"[{DIVIDER_STYLE['color']}]{c * ln} [{COLORS['primary']}]{d}[/] {c * ln}[/]")


def section_header(title: str, icon: str | None = None):
    """段落标题 — 带图标和装饰线。"""
    ic = icon or ICONS["primary"]
    console.print(f"\n[{COLORS['primary']}]{ic} {title}[/]")
    console.print(DIVIDER_STYLE["char"] * DIVIDER_STYLE["length"], style=DIVIDER_STYLE["color"])


# ═══════════════════════════════════════════════════════════════
# 面板
# ═══════════════════════════════════════════════════════════════


def _panel(body: str, title: str, style_key: str, **kw):
    ps = PANEL_STYLE.get(style_key, PANEL_STYLE["info"])
    console.print(Panel(body, title=title, border_style=ps["border"], padding=LAYOUT["panel_padding"], **kw))


def info_panel(body: str, title: str = ""):
    _panel(body, f"[bold {COLORS['primary']}]{ICONS['primary']} {title}[/]" if title else "", "info")


def success_panel(body: str, title: str = ""):
    _panel(body, f"[bold {COLORS['success']}]{ICONS['success']} {title}[/]" if title else "", "success")


def error_panel(body: str, title: str = "Error"):
    _panel(body, f"[bold {COLORS['error']}]{ICONS['error']} {title}[/]", "error")


def warn_panel(body: str, title: str = ""):
    _panel(body, f"[bold {COLORS['warning']}]{ICONS['warning']} {title}[/]" if title else "", "warn")


def beast_panel(body: str, title: str, beast: str):
    """五兽色面板 — beast: baihu/qinglong/zhuque/xuanwu/qilin."""
    ps = PANEL_STYLE.get(beast, PANEL_STYLE["info"])
    console.print(Panel(body, title=title, border_style=ps["border"], padding=LAYOUT["panel_padding"]))


# ═══════════════════════════════════════════════════════════════
# 输入框
# ═══════════════════════════════════════════════════════════════


def input_prompt_line(session=None):
    """生成输入提示行。可从 badges 模块获取会话状态。"""
    from ui.badges import render_badge_plain

    badge_str = render_badge_plain(session) if session else ""
    sym = INPUT_STYLE["prompt_symbol"]
    sym_color = INPUT_STYLE["prompt_color"]

    if badge_str:
        return f"[{COLORS['muted']}]┌─[/] {badge_str}\n[{sym_color}]{sym}[/] "
    return f"[{sym_color}]{sym}[/] "


def styled_input(prompt: str = "", session=None) -> str:
    """带样式的输入获取。返回用户输入字符串。"""
    line = prompt if prompt else input_prompt_line(session)
    return input(line)


# ═══════════════════════════════════════════════════════════════
# 进度与旋转
# ═══════════════════════════════════════════════════════════════


def progress_line(current: int, total: int, label: str = "", width: int = 30):
    """单行进度条 — ASCII 块字符。"""
    pct = current / total if total else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    color = COLORS["success"] if pct >= 1 else COLORS["primary"]
    sys.stdout.write(f"\r  [{color}]{bar}[/] {label} {current}/{total}")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")


def spinner(message: str, duration: float = 1.5):
    """旋转等待动画。"""
    from ui.effects import spin

    spin(message, duration)


# ═══════════════════════════════════════════════════════════════
# 启动全屏
# ═══════════════════════════════════════════════════════════════


def splash_full(v="v5.0", t=None, s=None):
    """启动欢迎页 — v5 现代简约 · 无 CRUX 大字 · 七兽网格。

    直接委托 terminal_logo.render_welcome()。
    """
    from ui.terminal_logo import render_welcome

    render_welcome(v, t, s)


# ═══════════════════════════════════════════════════════════════
# 全局应用
# ═══════════════════════════════════════════════════════════════


def apply_all():
    """一键全局美化启用。打印确认。"""
    console.print(f"[{COLORS['success']}]✓[/] CRUX Beautify v2 已激活", style="dim")
    console.print("  [dim]Logo·Badge·面板·分隔线·输入框·启动页·状态条·进度条[/]")
