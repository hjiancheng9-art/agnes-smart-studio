"""Retro 8-bit theme engine — single source of truth for CRUX Studio terminal aesthetics.

v2 升级: 扩展色板(五兽色+功能色+) · Badge样式槽 · 输入框样式 · 分隔线样式 · 面板样式

All colors, icons, layout parameters, and the Rich Theme are defined here.
Every UI module must import from this file (never define colors/logos locally).
"""

from rich.console import Console
from rich.theme import Theme

__all__ = [
    "COLORS",
    "RETRO_THEME",
    "ICONS",
    "BADGE_ICONS",
    "BADGE_STYLES",
    "LAYOUT",
    "INPUT_STYLE",
    "DIVIDER_STYLE",
    "PANEL_STYLE",
    "create_console",
    "console",
]

# ── Color palette v2 (Retro 8-bit + 五兽色) ───────────────────
COLORS = {
    "primary": "#00E5FF",
    "accent": "#FFD700",
    "success": "#00FF88",
    "warning": "#FFD700",
    "error": "#FF4444",
    "muted": "#556677",
    "surface": "#0F0F2D",
    "highlight": "#C084FC",
    "transition": "#66BBFF",
    # v2 新增
    "baihu": "#FFD700",  # 白虎·金
    "qinglong": "#00E5FF",  # 青龙·青
    "zhuque": "#C084FC",  # 朱雀·紫
    "xuanwu": "#5566AA",  # 玄武·蓝
    "qilin": "#00FF88",  # 麒麟·绿
    "badge_code": "#00E5FF",
    "badge_agent": "#FFD700",
    "badge_think": "#C084FC",
    "badge_skill": "#00FF88",
    "badge_model": "#26A69A",
    "input_prompt": "#00E5FF",
    "input_border": "#334455",
    "input_text": "#CCDDEE",
    "divider_primary": "#1A2A44",
    "card_border": "#1A2A44",
    "card_hover": "#00E5FF",
    "status_ok": "#00FF88",
    "status_warn": "#FFD700",
    "status_err": "#FF4444",
}

# ── Rich Theme v2 ────────────────────────────────────────────
RETRO_THEME = Theme(
    {
        "primary": "bold #00E5FF",
        "accent": "bold #FFD700",
        "success": "#00FF88",
        "warning": "#FFD700",
        "error": "bold #FF4444",
        "muted": "#556677",
        "surface": "on #0F0F2D",
        "highlight": "bold #C084FC",
        "transition": "#66BBFF",
        "panel.title": "bold #FFD700",
        "panel.border": "#00E5FF",
        "table.header": "bold #00E5FF",
        "table.border": "#556677",
        "bar.fill": "#00E5FF",
        "bar.background": "#556677",
        "baihu": "#FFD700",
        "qinglong": "#00E5FF",
        "zhuque": "#C084FC",
        "xuanwu": "#5566AA",
        "qilin": "#00FF88",
        "badge.code": "bold #00E5FF",
        "badge.agent": "bold #FFD700",
        "badge.think": "bold #C084FC",
        "badge.skill": "#00FF88",
        "badge.model": "#26A69A",
        "input.prompt": "#00E5FF",
        "input.border": "#1A2A44",
        "divider": "#1A2A44",
    }
)

# ── Icons ─────────────────────────────────────────────────────
ICONS = {
    "primary": "◆",
    "info": "▸",
    "success": "★",
    "warning": "▼",
    "error": "✕",
    "video": "▶",
    "route": "►",
    "on": "■",
    "off": "□",
    "enabled": "✓",
    "disabled": "✗",
    "star": "★",
    "empty": "○",
    "pipeline": "⇌",
    "history": "≡",
    "template": "◈",
    "separator": " · ",
    # v2 新符号
    "baihu": "◇",
    "qinglong": "◆",
    "zhuque": "❖",
    "xuanwu": "◎",
    "qilin": "◉",
    "crown": "♛",
    "shield": "🛡",
    "bolt": "⚡",
    "spark": "✦",
    "ring": "◎",
    "input": "▸",
    "divider_dot": "◆",
}

BADGE_ICONS = {
    "code": "⚡",
    "agent": "🧬",
    "think": "✨",
    "model": "🧩",
    "skill": "🎬",
}

# ── Badge 样式槽 v2 ─────────────────────────────────────────
BADGE_STYLES = {
    "code": {"icon": "⚡", "color": "badge.code", "bg": "#0A1A2E", "label": "CODE"},
    "agent": {"icon": "🧬", "color": "badge.agent", "bg": "#1A1A0A", "label": "AGENT"},
    "think": {"icon": "✨", "color": "badge.think", "bg": "#1A0A2A", "label": "THINK"},
    "skill": {"icon": "🎬", "color": "badge.skill", "bg": "#0A1A0A", "label": "SKILL"},
    "model": {"icon": "🧩", "color": "badge.model", "bg": "#0A1A1A", "label": "MODEL"},
    "provider": {"icon": "◉", "color": "muted", "bg": "#111122", "label": "PROV"},
}

# ── Layout ────────────────────────────────────────────────────
LAYOUT = {
    "panel_padding": (1, 2),
    "panel_border_style": "round",
    "table_show_lines": False,
    "table_box": "ROUNDED",
    "indent": "  ",
    "separator_len": 42,
    "separator_char": "─",
    "badge_separator": "  ◆  ",
    "bar_style": "#00E5FF",
    "bar_complete_style": "#00FF88",
    "input_indent": "  ",
    "welcome_width": 64,
    "card_min_width": 22,
}

# ── 输入框样式 ───────────────────────────────────────────────
INPUT_STYLE = {
    "prompt_symbol": "▸",
    "prompt_color": "primary",
    "border_char": "─",
    "border_color": "muted",
    "hint_color": "muted",
    "width": 60,
}

# ── 分隔线样式 ───────────────────────────────────────────────
DIVIDER_STYLE = {
    "char": "─",
    "dot": "◆",
    "length": 50,
    "color": "muted",
    "heavy_char": "━",
    "double_char": "═",
}

# ── 面板预设 ──────────────────────────────────────────────────
PANEL_STYLE = {
    "success": {"border": "success", "title_color": "success"},
    "error": {"border": "error", "title_color": "error"},
    "info": {"border": "primary", "title_color": "primary"},
    "warn": {"border": "warning", "title_color": "warning"},
    "baihu": {"border": "#FFD700", "title_color": "#FFD700"},
    "qinglong": {"border": "#00E5FF", "title_color": "#00E5FF"},
    "zhuque": {"border": "#C084FC", "title_color": "#C084FC"},
    "xuanwu": {"border": "#5566AA", "title_color": "#5566AA"},
    "qilin": {"border": "#00FF88", "title_color": "#00FF88"},
}


def create_console() -> Console:
    return Console(theme=RETRO_THEME, force_terminal=True)


console = create_console()
