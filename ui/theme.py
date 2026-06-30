"""暗夜工坊 Dark Atelier — CRUX Studio v6 现代开发者主题。

基于 GitHub Dark 骨架，融入七兽色作为功能区分色。层次感取代扁平，
信息密度优先，终端原生表现力最大化。

设计原则:
- 七兽色: 降饱和做功能色，非装饰
- 背景: 纯黑→暗灰四层深度（bg=#0D1117, surface=#161B22, panel=#1C2128, elevated=#21262D）
- 文字: 三档亮度（text=#E6EDF3, secondary=#8B949E, tertiary=#6E7681）
- 终端极简: 无圆角·无阴影·无渐变（保留原生终端表现力）
"""

import sys as _sys

from rich.console import Console as _RichConsole

# ── 七兽图腾色 (低饱和功能色) ──────────────────────────────
BEAST_PALETTE = {
    "baihu":   "#E3B341",   # 白虎·金   → 权威 / 警告（质量门）
    "qinglong": "#58A6FF",   # 青龙·青   → 信息 / 链接（知识检索）
    "zhuque":  "#F78166",    # 朱雀·赤   → 创意 / 洞察（深度研究）
    "xuanwu":  "#7B85D6",    # 玄武·靛   → 系统 / 守卫（安全审查）
    "qilin":   "#3FB950",    # 麒麟·翠   → 成功 / 创造（代码生成）
    "tengshe": "#DB8A3A",    # 螣蛇·琥珀  → 记忆 / 历史（上下文管理）
    "yinglong": "#A5C8E4",   # 应龙·银蓝  → 规划 / 调度（多智能体）
}

# ── 暗夜工坊基础色板 ──────────────────────────────────────
BASE_PALETTE = {
    # 背景四层深度
    "bg":           "#0D1117",
    "surface":      "#161B22",
    "panel":        "#1C2128",
    "elevated":     "#21262D",

    # 文字三档
    "text":         "#E6EDF3",
    "text_secondary": "#8B949E",
    "text_tertiary":  "#6E7681",

    # 主色
    "base":         "#0D1117",
    "muted":        "#6E7681",
    "accent":       "#58A6FF",
    "primary":      "#58A6FF",
    "highlight":    "#F78166",

    # 边框
    "border":        "#21262D",
    "border_focus":  "#30363D",
    "border_bright": "#484F58",

    # 输入框
    "input_prompt":    "#58A6FF",
    "input_text":      "#E6EDF3",
    "input_placeholder": "#484F58",
    "input_hint":      "#6E7681",
    "input_border":    "#30363D",
    "input_cursor":    "#F78166",
    "input_frame_top":    "#21262D",
    "input_frame_bottom": "#161B22",

    # 状态
    "status_ok":    "#3FB950",
    "status_warn":  "#E3B341",
    "status_err":   "#F85149",
    "status_idle":  "#6E7681",

    # 消息类型
    "info":         "#58A6FF",
    "success":      "#3FB950",
    "warning":      "#D29922",
    "error":        "#F85149",

    # 徽章
    "badge_think":  "#F78166",
    "badge_code":   "#3FB950",
    "badge_agent":  "#A5C8E4",
    "badge_model":  "#7B85D6",
    "badge_skill":  "#DB8A3A",

    # 卡片
    "card_border":  "#21262D",
    "card_hover":   "#30363D",

    # 分隔符
    "chat_separator":        "#21262D",
    "chat_separator_accent": "#30363D",
    "divider_primary":       "#21262D",

    # 转场 / 覆盖
    "transition": "#30363D",
    "overlay":    "rgba(13,17,23,0.85)",

    # 聊天气泡色
    "user_bubble_bg":       "#1A2332",
    "user_bubble_border":   "#58A6FF",
    "assistant_bubble_bg":  "#161B22",
    "assistant_bubble_border": "#30363D",
    "system_bubble_bg":     "#0D1117",
    "system_bubble_border": "#21262D",
    "tool_bubble_bg":       "#1C1F1A",
    "tool_bubble_border":   "#3FB950",

    # 流式 / 状态栏 / 分隔线
    "stream_cursor":   "#F78166",
    "status_bar_bg":   "#161B22",
    "status_bar_text": "#8B949E",
    "separator_thin":  "#161B22",
}

# ── 完整色表 ───────────────────────────────────────────────
COLORS = {}
COLORS.update(BASE_PALETTE)
COLORS.update(BEAST_PALETTE)
COLORS.update({
    "BAIHU":    "#E3B341",
    "QINGLONG": "#58A6FF",
    "ZHUQUE":   "#F78166",
    "XUANWU":   "#7B85D6",
    "QILIN":    "#3FB950",
    "TENGSHE":  "#DB8A3A",
    "YINGLONG": "#A5C8E4",
})

# ── 符号表 ─────────────────────────────────────────────────
GLYPHS = {
    "logo":     "◈",
    "cursor":   "▸",
    "pointer":  "▹",
    "check":    "✓",
    "cross":    "✗",
    "bullet":   "·",
    "arrow":    "→",
    "dot":      "·",
    "block":    "█",
    "hbar":     "─",
    "vbar":     "│",
    "corner_tl":"╭",
    "corner_tr":"╮",
    "corner_bl":"╰",
    "corner_br":"╯",
    "send":     "⯈",
    "fire":     "🔥",
    "hammer":   "🔨",
    "brain":    "🧠",
    "search":   "🔍",
    "key":      "🔑",
    "package":  "📦",
    "test":     "🧪",
    "deploy":   "🚀",
    "star":     "★",
    "diamond":  "◆",
    "triangle": "▲",
}

# ── Rich 主题 ──────────────────────────────────────────────
def theme_rich():
    from pygments.token import (
        Comment, Error, Generic, Keyword, Literal, Name, Number,
        Operator, Punctuation, String, Text, Token,
    )
    return {
        Token:              COLORS["text"],
        Text:               COLORS["text"],
        Comment:            f"italic {COLORS['text_tertiary']}",
        Keyword:            COLORS["qinglong"],
        Name:               COLORS["text"],
        Name.Function:      COLORS["zhuque"],
        Name.Class:         COLORS["qilin"],
        Name.Builtin:       COLORS["xuanwu"],
        String:             COLORS["qilin"],
        Number:             COLORS["tengshe"],
        Operator:           COLORS["text_secondary"],
        Punctuation:        COLORS["text_secondary"],
        Literal:            COLORS["yinglong"],
        Error:              COLORS["error"],
        Generic.Error:      COLORS["error"],
        Generic.Traceback:  COLORS["error"],
        Generic.Heading:    f"bold {COLORS['qinglong']}",
        Generic.Subheading: f"bold {COLORS['text']}",
        Generic.Inserted:   f"bg:{COLORS['surface']} {COLORS['qilin']}",
        Generic.Deleted:    f"bg:{COLORS['surface']} {COLORS['error']}",
        Generic.Emph:       "italic",
        Generic.Strong:     "bold",
    }


def dark_atelier_styles(style_type="pygments"):
    if style_type == "pygments" or style_type is None:
        return theme_rich()
    return theme_rich()


def dark_atelier_css():
    return f"""
    .crux-dark {{
        background: {COLORS['bg']};
        color: {COLORS['text']};
        font-family: 'Cascadia Code', 'JetBrains Mono', 'Consolas', monospace;
    }}
    .crux-dark .user-bubble {{
        background: {COLORS['user_bubble_bg']};
        border-left: 2px solid {COLORS['user_bubble_border']};
        padding: 8px 12px;
        margin: 4px 0 4px 40px;
    }}
    .crux-dark .assistant-bubble {{
        background: {COLORS['assistant_bubble_bg']};
        border-left: 2px solid {COLORS['assistant_bubble_border']};
        padding: 8px 12px;
        margin: 4px 40px 4px 0;
    }}
    .crux-dark .system-bubble {{
        background: {COLORS['system_bubble_bg']};
        border-left: 1px solid {COLORS['system_bubble_border']};
        padding: 4px 8px;
        margin: 2px auto;
        font-size: 0.85em;
        color: {COLORS['text_tertiary']};
    }}
    .crux-dark .status-bar {{
        background: {COLORS['status_bar_bg']};
        color: {COLORS['status_bar_text']};
        padding: 2px 8px;
        font-size: 0.8em;
    }}
    """


# ── 兼容旧导出名 ───────────────────────────────────────────
ICONS = GLYPHS.copy()
ICONS.update({
    "primary":   "●",
    "secondary": "○",
    "success":   "✓",
    "warning":   "⚠",
    "error":     "✗",
    "info":      "ℹ",
    "arrow":     "→",
    "cpu":       "⚙",
    "memory":    "□",
    "network":   "⇢",
    "source":    "📄",
    "git":       "⑂",
    "python":    "🐍",
    "json":      "❴❵",
    "image":     "🖼",
    "video":     "▶",
    "audio":     "♫",
    "download":  "↓",
    "tool":      "🔧",
    "chat":      "💬",
    "baihu":     "🐅",
    "qinglong":  "🐉",
    "zhuque":    "🕊",
    "xuanwu":    "🐢",
    "qilin":     "🦄",
    "tengshe":   "🐍",
    "yinglong":  "🪽",
})

BADGE_ICONS = {
    "think":  GLYPHS.get("brain", "🧠"),
    "code":   GLYPHS.get("hammer", "🔨"),
    "agent":  GLYPHS.get("search", "🔍"),
    "model":  GLYPHS.get("brain", "🧠"),
    "skill":  GLYPHS.get("package", "📦"),
    "test":   GLYPHS.get("test", "🧪"),
    "deploy": GLYPHS.get("deploy", "🚀"),
}

BADGE_STYLES = {
    "think":  {"style": f"bold {COLORS['zhuque']}", "label": "THINK"},
    "code":   {"style": f"bold {COLORS['qilin']}", "label": "CODE"},
    "agent":  {"style": f"bold {COLORS['yinglong']}", "label": "AGENT"},
    "model":  {"style": f"bold {COLORS['xuanwu']}", "label": "MODEL"},
    "skill":  {"style": f"bold {COLORS['tengshe']}", "label": "SKILL"},
}

DIVIDER_STYLE = f"{COLORS['separator_thin']}"
INPUT_STYLE = f"bg:{COLORS['surface']} {COLORS['text']}"

LAYOUT = {
    "padding": (1, 2),
    "panel_padding": (1, 2),
    "panel": {"padding": (1, 2), "border_style": COLORS["border"]},
    "input": {"padding": (0, 1)},
}

PANEL_STYLE = {
    "baihu":    {"style": f"on {COLORS['user_bubble_bg']}", "border": COLORS["baihu"]},
    "qinglong": {"style": f"on {COLORS['user_bubble_bg']}", "border": COLORS["qinglong"]},
    "zhuque":   {"style": f"on {COLORS['assistant_bubble_bg']}", "border": COLORS["zhuque"]},
    "xuanwu":   {"style": f"on {COLORS['system_bubble_bg']}", "border": COLORS["xuanwu"]},
    "qilin":    {"style": f"on {COLORS['tool_bubble_bg']}", "border": COLORS["qilin"]},
    "tengshe":  {"style": f"on {COLORS['user_bubble_bg']}", "border": COLORS["tengshe"]},
    "yinglong": {"style": f"on {COLORS['assistant_bubble_bg']}", "border": COLORS["yinglong"]},
}

RETRO_THEME = {
    "bg": COLORS["bg"],
    "text": COLORS["text"],
    "accent": COLORS["accent"],
    "primary": {"style": f"bold {COLORS['primary']}"},
}

console = _RichConsole()

# ── 模块级导出 ─────────────────────────────────────────────
S = dark_atelier_styles("pygments")
C = dark_atelier_css()
